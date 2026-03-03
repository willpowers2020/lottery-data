#!/usr/bin/env python3
"""
SQLite to MongoDB Migration Script with Optimized Schema
=========================================================

This script migrates your local Pick 4 and Pick 5 SQLite databases to MongoDB
with an optimized schema designed for faster queries.

SCHEMA COMPARISON:
==================

CURRENT MONGODB SCHEMA (from LotteryPost):
{
    "country": "United States",
    "state_name": "California", 
    "game_name": "Daily 4 Midday",
    "date": ISODate("2026-01-20"),
    "numbers": "[\"3\", \"1\", \"8\", \"0\"]",  # JSON string - requires parsing!
    "tod": "Midday"
}

OPTIMIZED SCHEMA:
{
    # Core identifiers
    "country": "United States",
    "state": "ca",                    # State code (indexed)
    "state_name": "California",       # Full name for display
    "game": "daily-4-midday",         # Game code (indexed)
    "game_name": "Daily 4 Midday",    # Full name for display
    "game_type": "pick4",             # pick3, pick4, pick5, cash5 (indexed)
    
    # Date/Time
    "date": ISODate("2026-01-20"),    # Indexed
    "tod": "Midday",                  # Time of day
    
    # Numbers - MULTIPLE FORMATS for fast queries
    "numbers": ["3", "1", "8", "0"],  # Array (not JSON string!)
    "number_str": "3180",             # Raw string for exact match
    "normalized": "0138",             # Sorted for box match (indexed)
    "digits_sum": 12,                 # Pre-calculated sum (indexed)
    
    # 2DP pairs for Pick 4 (pre-calculated for prediction algorithm)
    "pairs_2dp": ["01", "03", "08", "13", "18", "38"],
    
    # 3DP triples for Pick 5
    "triples_3dp": ["012", "013", ...],  # Only for pick5
    
    # Metadata
    "num_digits": 4,
    "created_at": ISODate("2026-01-21")
}

INDEXES TO CREATE:
==================
- { state: 1, game_type: 1, date: -1 }     # Primary query pattern
- { state: 1, game: 1, date: -1 }          # Specific game queries
- { game_type: 1, date: -1 }               # Cross-state queries
- { normalized: 1, state: 1, game_type: 1 } # Pattern lookups
- { digits_sum: 1, state: 1, game_type: 1 } # Sum-based queries
- { "pairs_2dp": 1 }                        # 2DP prediction queries
- { date: -1 }                              # Recent draws

USAGE:
======
1. Test migration (dry run):
   python3 migrate_to_mongo.py --dry-run

2. Migrate to new collection (safe):
   python3 migrate_to_mongo.py --collection lottery_optimized

3. Migrate and replace existing:
   python3 migrate_to_mongo.py --collection lotterypost --replace

4. Migrate specific state only:
   python3 migrate_to_mongo.py --state ca --collection lottery_optimized
"""

import sqlite3
import json
import argparse
from datetime import datetime
from pathlib import Path
from itertools import combinations
from collections import defaultdict

# =============================================================================
# CONFIGURATION
# =============================================================================

# SQLite paths - UPDATE THESE
PICK4_DB_PATH = Path('/Users/british.williams/lottery_scraper/pick4/data/pick4_master.db')
PICK5_DB_PATH = Path('/Users/british.williams/lottery_scraper/pick5/data/pick5_data.db')

# MongoDB connection
MONGO_URL = 'mongodb+srv://willpowers2026:dFUATeYtHrP87gPk@cluster0.nmujtyo.mongodb.net/'
MONGO_DB = 'mylottodata'
DEFAULT_COLLECTION = 'lottery_optimized'  # New collection, won't touch existing

# State mappings
STATE_CODE_TO_NAME = {
    'al': 'Alabama', 'ak': 'Alaska', 'az': 'Arizona', 'ar': 'Arkansas',
    'ca': 'California', 'co': 'Colorado', 'ct': 'Connecticut', 'de': 'Delaware',
    'dc': 'Washington DC', 'fl': 'Florida', 'ga': 'Georgia', 'hi': 'Hawaii',
    'id': 'Idaho', 'il': 'Illinois', 'in': 'Indiana', 'ia': 'Iowa',
    'ks': 'Kansas', 'ky': 'Kentucky', 'la': 'Louisiana', 'me': 'Maine',
    'md': 'Maryland', 'ma': 'Massachusetts', 'mi': 'Michigan', 'mn': 'Minnesota',
    'ms': 'Mississippi', 'mo': 'Missouri', 'mt': 'Montana', 'ne': 'Nebraska',
    'nv': 'Nevada', 'nh': 'New Hampshire', 'nj': 'New Jersey', 'nm': 'New Mexico',
    'ny': 'New York', 'nc': 'North Carolina', 'nd': 'North Dakota', 'oh': 'Ohio',
    'ok': 'Oklahoma', 'or': 'Oregon', 'pa': 'Pennsylvania', 'ri': 'Rhode Island',
    'sc': 'South Carolina', 'sd': 'South Dakota', 'tn': 'Tennessee', 'tx': 'Texas',
    'ut': 'Utah', 'vt': 'Vermont', 'va': 'Virginia', 'wa': 'Washington',
    'wv': 'West Virginia', 'wi': 'Wisconsin', 'wy': 'Wyoming'
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_2dp_pairs(digits):
    """Get unique 2-digit pair combinations."""
    pairs = set()
    for combo in combinations(digits, 2):
        pair = ''.join(sorted(combo))
        pairs.add(pair)
    return sorted(list(pairs))

def get_3dp_triples(digits):
    """Get unique 3-digit triple combinations."""
    triples = set()
    for combo in combinations(digits, 3):
        triple = ''.join(sorted(combo))
        triples.add(triple)
    return sorted(list(triples))

def get_tod_from_game(game_name):
    """Extract time of day from game name."""
    game_lower = game_name.lower()
    if any(x in game_lower for x in ['evening', 'night', 'eve', '10pm', '7pm']):
        return 'Evening'
    if any(x in game_lower for x in ['midday', 'mid-day', '1pm', '4pm']):
        return 'Midday'
    if 'morning' in game_lower:
        return 'Morning'
    if 'day' in game_lower and 'mid' not in game_lower:
        return 'Day'
    return ''

def get_game_type(game_name):
    """Determine game type from game name."""
    name = game_name.lower()
    if any(x in name for x in ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4', 
                                'dc-4', 'dc 4', 'cash 4', 'cash4', 'cash-4', 'win 4', 'win4',
                                'play 4', 'play4', 'play-4']):
        return 'pick4'
    if any(x in name for x in ['pick 3', 'pick3', 'pick-3', 'daily 3', 'daily3', 'daily-3',
                                'dc-3', 'dc 3', 'cash 3', 'cash3', 'cash-3', 'play 3']):
        return 'pick3'
    if any(x in name for x in ['pick 5', 'pick5', 'pick-5', 'daily 5', 'daily5', 'daily-5']):
        return 'pick5'
    if any(x in name for x in ['cash 5', 'cash5', 'fantasy 5', 'fantasy5', 'take 5']):
        return 'cash5'
    return 'unknown'

def normalize_game_name(game_code):
    """Convert game code to display name."""
    return game_code.replace('-', ' ').title()


# =============================================================================
# MIGRATION FUNCTIONS
# =============================================================================

def read_sqlite_data(db_path, table_name, state_filter=None):
    """Read data from SQLite database."""
    if not db_path.exists():
        print(f"⚠️  Database not found: {db_path}")
        return []
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    sql = f'SELECT state, game, draw_date, number FROM {table_name}'
    params = []
    
    if state_filter:
        sql += ' WHERE state = ?'
        params.append(state_filter.lower())
    
    sql += ' ORDER BY draw_date ASC'
    
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        print(f"📊 Read {len(rows):,} rows from {table_name}")
        return rows
    except Exception as e:
        print(f"❌ Error reading {table_name}: {e}")
        return []
    finally:
        conn.close()

def transform_row(row, game_type_hint):
    """Transform a SQLite row to optimized MongoDB document."""
    state_code, game_code, draw_date, number = row
    
    # Parse number
    num_str = str(number).replace('-', '')
    num_digits = 4 if game_type_hint == 'pick4' else 5 if game_type_hint == 'pick5' else len(num_str)
    num_str = num_str.zfill(num_digits)
    digits = list(num_str[:num_digits])
    
    # Calculate derived fields
    normalized = ''.join(sorted(digits))
    digits_sum = sum(int(d) for d in digits)
    
    # Get game type
    game_type = get_game_type(game_code)
    if game_type == 'unknown':
        game_type = game_type_hint
    
    # Build document
    doc = {
        'country': 'United States',
        'state': state_code.lower(),
        'state_name': STATE_CODE_TO_NAME.get(state_code.lower(), state_code.upper()),
        'game': game_code.lower(),
        'game_name': normalize_game_name(game_code),
        'game_type': game_type,
        'date': datetime.strptime(draw_date, '%Y-%m-%d'),
        'tod': get_tod_from_game(game_code),
        'numbers': digits,
        'number_str': num_str,
        'normalized': normalized,
        'digits_sum': digits_sum,
        'num_digits': num_digits,
        'created_at': datetime.utcnow()
    }
    
    # Add 2DP pairs for pick4
    if num_digits == 4:
        doc['pairs_2dp'] = get_2dp_pairs(digits)
    
    # Add 3DP triples for pick5
    if num_digits == 5:
        doc['triples_3dp'] = get_3dp_triples(digits)
    
    return doc

def create_indexes(collection):
    """Create optimized indexes."""
    indexes = [
        # Primary query patterns
        [('state', 1), ('game_type', 1), ('date', -1)],
        [('state', 1), ('game', 1), ('date', -1)],
        [('game_type', 1), ('date', -1)],
        
        # Pattern lookups (critical for predictions)
        [('normalized', 1), ('state', 1), ('game_type', 1)],
        [('normalized', 1), ('date', 1)],
        
        # Sum-based queries
        [('digits_sum', 1), ('state', 1), ('game_type', 1)],
        
        # 2DP prediction queries
        [('pairs_2dp', 1)],
        
        # Recent draws
        [('date', -1)],
        
        # Unique constraint
        [('state', 1), ('game', 1), ('date', 1), ('number_str', 1)],
    ]
    
    print("\n📑 Creating indexes...")
    for idx_spec in indexes:
        try:
            idx_name = '_'.join([f"{k}_{v}" for k, v in idx_spec])
            collection.create_index(idx_spec, name=idx_name, background=True)
            print(f"   ✓ {idx_name}")
        except Exception as e:
            print(f"   ⚠️  Index error: {e}")

def migrate_to_mongodb(docs, collection_name, dry_run=False, replace=False):
    """Migrate documents to MongoDB."""
    if dry_run:
        print(f"\n🔍 DRY RUN - Would insert {len(docs):,} documents into '{collection_name}'")
        print("\nSample documents:")
        for doc in docs[:3]:
            # Remove datetime for display
            display_doc = {k: str(v) if isinstance(v, datetime) else v for k, v in doc.items()}
            print(f"  {json.dumps(display_doc, indent=2)[:500]}...")
        return True
    
    try:
        from pymongo import MongoClient
        
        print(f"\n🔌 Connecting to MongoDB...")
        client = MongoClient(MONGO_URL)
        db = client[MONGO_DB]
        collection = db[collection_name]
        
        if replace:
            print(f"⚠️  Dropping existing collection '{collection_name}'...")
            collection.drop()
        
        # Insert in batches
        batch_size = 5000
        total_inserted = 0
        
        print(f"📤 Inserting {len(docs):,} documents...")
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i+batch_size]
            try:
                result = collection.insert_many(batch, ordered=False)
                total_inserted += len(result.inserted_ids)
                print(f"   Inserted batch {i//batch_size + 1}: {len(result.inserted_ids):,} docs")
            except Exception as e:
                # Handle duplicate key errors gracefully
                if 'duplicate' in str(e).lower():
                    print(f"   ⚠️  Batch {i//batch_size + 1}: Some duplicates skipped")
                else:
                    print(f"   ❌ Batch {i//batch_size + 1} error: {e}")
        
        print(f"\n✅ Total inserted: {total_inserted:,} documents")
        
        # Create indexes
        create_indexes(collection)
        
        # Print stats
        print(f"\n📊 Collection stats:")
        print(f"   Total documents: {collection.count_documents({}):,}")
        print(f"   Unique states: {len(collection.distinct('state'))}")
        print(f"   Unique games: {len(collection.distinct('game'))}")
        
        # Date range
        pipeline = [
            {'$group': {
                '_id': None,
                'min_date': {'$min': '$date'},
                'max_date': {'$max': '$date'}
            }}
        ]
        result = list(collection.aggregate(pipeline))
        if result:
            print(f"   Date range: {result[0]['min_date'].strftime('%Y-%m-%d')} to {result[0]['max_date'].strftime('%Y-%m-%d')}")
        
        client.close()
        return True
        
    except ImportError:
        print("❌ pymongo not installed. Run: pip install pymongo")
        return False
    except Exception as e:
        print(f"❌ MongoDB error: {e}")
        return False


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Migrate SQLite lottery data to MongoDB with optimized schema',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview migration without inserting')
    parser.add_argument('--collection', type=str, default=DEFAULT_COLLECTION,
                       help=f'MongoDB collection name (default: {DEFAULT_COLLECTION})')
    parser.add_argument('--replace', action='store_true',
                       help='Drop existing collection before inserting')
    parser.add_argument('--state', type=str,
                       help='Migrate only specific state (e.g., ca, fl)')
    parser.add_argument('--pick4-only', action='store_true',
                       help='Migrate only Pick 4 data')
    parser.add_argument('--pick5-only', action='store_true',
                       help='Migrate only Pick 5 data')
    
    args = parser.parse_args()
    
    print("="*60)
    print("SQLite to MongoDB Migration")
    print("="*60)
    print(f"Pick 4 DB: {PICK4_DB_PATH} ({'✓' if PICK4_DB_PATH.exists() else '✗'})")
    print(f"Pick 5 DB: {PICK5_DB_PATH} ({'✓' if PICK5_DB_PATH.exists() else '✗'})")
    print(f"Target collection: {args.collection}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.state:
        print(f"State filter: {args.state}")
    print("="*60)
    
    all_docs = []
    
    # Read Pick 4 data
    if not args.pick5_only:
        print("\n📖 Reading Pick 4 data...")
        pick4_rows = read_sqlite_data(PICK4_DB_PATH, 'pick4_results', args.state)
        for row in pick4_rows:
            doc = transform_row(row, 'pick4')
            all_docs.append(doc)
    
    # Read Pick 5 data
    if not args.pick4_only:
        print("\n📖 Reading Pick 5 data...")
        pick5_rows = read_sqlite_data(PICK5_DB_PATH, 'pick5_results', args.state)
        for row in pick5_rows:
            doc = transform_row(row, 'pick5')
            all_docs.append(doc)
    
    if not all_docs:
        print("\n❌ No data to migrate!")
        return
    
    print(f"\n📦 Total documents to migrate: {len(all_docs):,}")
    
    # Show breakdown by state/game
    by_state = defaultdict(int)
    by_game_type = defaultdict(int)
    for doc in all_docs:
        by_state[doc['state']] += 1
        by_game_type[doc['game_type']] += 1
    
    print("\nBy state:")
    for state, count in sorted(by_state.items(), key=lambda x: -x[1])[:10]:
        print(f"   {state.upper()}: {count:,}")
    if len(by_state) > 10:
        print(f"   ... and {len(by_state) - 10} more states")
    
    print("\nBy game type:")
    for gt, count in sorted(by_game_type.items()):
        print(f"   {gt}: {count:,}")
    
    # Migrate
    migrate_to_mongodb(all_docs, args.collection, args.dry_run, args.replace)
    
    print("\n" + "="*60)
    print("Migration complete!")
    print("="*60)


if __name__ == '__main__':
    main()
