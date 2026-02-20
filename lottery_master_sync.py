#!/usr/bin/env python3
"""
lottery_master_sync.py - Complete lottery data management
=========================================================

Merges SQLite (clean) + Supabase (fills gaps) → MongoDB

Usage:
    python3 lottery_master_sync.py --status            # Show all DB stats
    python3 lottery_master_sync.py --compare           # Compare all DBs
    python3 lottery_master_sync.py --full-setup        # Full merge to MongoDB
    python3 lottery_master_sync.py --sync              # Daily sync new data

Requirements:
    pip install psycopg2-binary pymongo requests beautifulsoup4
"""

import os
import sys
import json
import argparse
import sqlite3
from datetime import datetime, timedelta
from itertools import combinations
import time
import re

# =============================================================================
# CONFIGURATION
# =============================================================================

# SQLite paths
PICK4_DB = os.path.expanduser('~/lottery_scraper/pick4/data/pick4_master.db')
PICK5_DB = os.path.expanduser('~/lottery_scraper/pick5/data/pick5_data.db')

# Supabase PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL', 
    'postgresql://postgres.lewvjrlflatexlcndefi:jx4wdz7vQ62ENoCD@aws-1-us-east-1.pooler.supabase.com:5432/postgres')

# MongoDB
MONGO_URL = os.environ.get('MONGO_URL', 
    'mongodb+srv://willpowers2026:dFUATeYtHrP87gPk@cluster0.nmujtyo.mongodb.net/')
MONGO_DB = os.environ.get('MONGO_DB', 'lottery')
MONGO_COLLECTION = os.environ.get('MONGO_COLLECTION', 'lottery_v2')

# State code <-> name mappings
STATE_CODES = {
    'Arkansas': 'ar', 'Arizona': 'az', 'California': 'ca', 'Colorado': 'co',
    'Connecticut': 'ct', 'Washington, D.C.': 'dc', 'Washington DC': 'dc',
    'Delaware': 'de', 'Florida': 'fl', 'Georgia': 'ga', 'Iowa': 'ia',
    'Illinois': 'il', 'Indiana': 'in', 'Kansas': 'ks', 'Kentucky': 'ky',
    'Louisiana': 'la', 'Massachusetts': 'ma', 'Maryland': 'md', 'Maine': 'me',
    'Michigan': 'mi', 'Minnesota': 'mn', 'Missouri': 'mo', 'North Carolina': 'nc',
    'Nebraska': 'ne', 'New Hampshire': 'nh', 'New Jersey': 'nj', 'New Mexico': 'nm',
    'New York': 'ny', 'Ohio': 'oh', 'Oklahoma': 'ok', 'Oregon': 'or',
    'Pennsylvania': 'pa', 'Rhode Island': 'ri', 'South Carolina': 'sc',
    'Tennessee': 'tn', 'Texas': 'tx', 'Virginia': 'va', 'Vermont': 'vt',
    'Wisconsin': 'wi', 'West Virginia': 'wv',
}

STATE_NAMES = {v: k for k, v in STATE_CODES.items()}


def get_supabase_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def get_mongo_client():
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    client.admin.command('ping')
    return client


def normalize_game_name(game):
    """Normalize game name for comparison."""
    # 'pick-4-evening' -> 'pick4evening'
    # 'Pick 4 Evening' -> 'pick4evening'
    return re.sub(r'[^a-z0-9]', '', game.lower())


def get_tod(game_name):
    """Extract time of day from game name."""
    g = game_name.lower()
    if 'morning' in g:
        return 'Morning'
    if any(x in g for x in ['midday', 'mid-day', 'day', '1pm', '4pm', '1:50']):
        return 'Midday'
    if any(x in g for x in ['evening', 'night', '7pm', '10pm', '7:50']):
        return 'Evening'
    return ''


def create_unique_key(state_code, game_name, draw_date, numbers):
    """Create unique key for deduplication."""
    # Normalize: fl + pick4evening + 2026-01-15 + 4806
    norm_game = normalize_game_name(game_name)
    norm_numbers = ''.join(str(n) for n in numbers)
    date_str = draw_date if isinstance(draw_date, str) else draw_date.strftime('%Y-%m-%d')
    return f"{state_code.lower()}|{norm_game}|{date_str}|{norm_numbers}"


# =============================================================================
# STATUS
# =============================================================================

def show_status():
    print(f"\n{'='*70}")
    print("DATABASE STATUS")
    print(f"{'='*70}")
    
    # SQLite Pick 4
    print("\n📊 SQLite Pick 4")
    if os.path.exists(PICK4_DB):
        conn = sqlite3.connect(PICK4_DB)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), MIN(draw_date), MAX(draw_date) FROM pick4_results")
        total, min_d, max_d = c.fetchone()
        c.execute("SELECT COUNT(DISTINCT state) FROM pick4_results")
        states = c.fetchone()[0]
        print(f"   Records: {total:,}")
        print(f"   States: {states}")
        print(f"   Range: {min_d} to {max_d}")
        conn.close()
    else:
        print(f"   ❌ Not found: {PICK4_DB}")
    
    # SQLite Pick 5
    print("\n📊 SQLite Pick 5")
    if os.path.exists(PICK5_DB):
        conn = sqlite3.connect(PICK5_DB)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), MIN(draw_date), MAX(draw_date) FROM pick5_results")
        total, min_d, max_d = c.fetchone()
        c.execute("SELECT COUNT(DISTINCT state) FROM pick5_results")
        states = c.fetchone()[0]
        print(f"   Records: {total:,}")
        print(f"   States: {states}")
        print(f"   Range: {min_d} to {max_d}")
        conn.close()
    else:
        print(f"   ❌ Not found: {PICK5_DB}")
    
    # Supabase
    print("\n📊 Supabase")
    try:
        conn = get_supabase_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM draws")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT (game_id, draw_date, value)) FROM draws")
        unique = cur.fetchone()[0]
        cur.execute("SELECT MIN(draw_date), MAX(draw_date) FROM draws")
        min_d, max_d = cur.fetchone()
        print(f"   Total: {total:,}")
        print(f"   Unique: {unique:,}")
        print(f"   Duplicates: {total - unique:,}")
        print(f"   Range: {min_d} to {max_d}")
        conn.close()
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # MongoDB
    print(f"\n📊 MongoDB ({MONGO_COLLECTION})")
    try:
        client = get_mongo_client()
        coll = client[MONGO_DB][MONGO_COLLECTION]
        total = coll.count_documents({})
        print(f"   Total: {total:,}")
        if total > 0:
            for gt in ['pick2', 'pick3', 'pick4', 'pick5']:
                count = coll.count_documents({'game_type': gt})
                if count > 0:
                    print(f"   {gt}: {count:,}")
            oldest = coll.find_one(sort=[('date', 1)])
            newest = coll.find_one(sort=[('date', -1)])
            if oldest and newest:
                print(f"   Range: {oldest['date'].strftime('%Y-%m-%d')} to {newest['date'].strftime('%Y-%m-%d')}")
        client.close()
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print()


# =============================================================================
# FULL SETUP - Merge SQLite + Supabase -> MongoDB
# =============================================================================

def full_setup():
    """
    Merge all data into MongoDB:
    1. SQLite Pick 4 (clean, primary source)
    2. SQLite Pick 5 (clean, primary source)
    3. Supabase Pick 2-5 (fills gaps, older data)
    """
    print(f"\n{'='*70}")
    print("FULL SETUP: Merging SQLite + Supabase → MongoDB")
    print(f"{'='*70}")
    
    client = get_mongo_client()
    db = client[MONGO_DB]
    coll = db[MONGO_COLLECTION]
    
    # Clear existing collection (delete all docs instead of dropping)
    print(f"\nClearing existing collection: {MONGO_COLLECTION}")
    result = coll.delete_many({})
    print(f"   Deleted {result.deleted_count:,} existing documents")
    
    seen_keys = set()  # Track unique records
    total_inserted = 0
    
    # ===================
    # PHASE 1: SQLite Pick 4
    # ===================
    print(f"\n📥 Phase 1: SQLite Pick 4...")
    if os.path.exists(PICK4_DB):
        conn = sqlite3.connect(PICK4_DB)
        c = conn.cursor()
        c.execute("SELECT state, game, draw_date, num1, num2, num3, num4 FROM pick4_results ORDER BY draw_date")
        rows = c.fetchall()
        conn.close()
        
        batch = []
        for state, game, draw_date, n1, n2, n3, n4 in rows:
            nums = [str(n1), str(n2), str(n3), str(n4)]
            
            # Create unique key
            key = create_unique_key(state, game, draw_date, nums)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            # Build document
            state_name = STATE_NAMES.get(state.lower(), state)
            doc = {
                'country': 'United States',
                'state': state.lower(),
                'state_name': state_name,
                'game': game,
                'game_name': game.replace('-', ' ').title(),
                'game_type': 'pick4',
                'date': datetime.strptime(draw_date, '%Y-%m-%d'),
                'numbers': json.dumps(nums),
                'number_str': ''.join(nums),
                'normalized': ''.join(sorted(nums)),
                'digits_sum': sum(int(d) for d in nums),
                'pairs_2dp': sorted(set(''.join(sorted(p)) for p in combinations(nums, 2))),
                'triples_3dp': [],
                'tod': get_tod(game),
                'num_digits': 4,
                'source': 'sqlite',
            }
            batch.append(doc)
            
            if len(batch) >= 5000:
                coll.insert_many(batch)
                total_inserted += len(batch)
                print(f"   Inserted {total_inserted:,}...")
                batch = []
        
        if batch:
            coll.insert_many(batch)
            total_inserted += len(batch)
        
        print(f"   ✅ SQLite Pick 4: {total_inserted:,} records")
    
    # ===================
    # PHASE 2: SQLite Pick 5
    # ===================
    print(f"\n📥 Phase 2: SQLite Pick 5...")
    phase2_count = 0
    if os.path.exists(PICK5_DB):
        conn = sqlite3.connect(PICK5_DB)
        c = conn.cursor()
        c.execute("SELECT state, game, draw_date, numbers FROM pick5_results ORDER BY draw_date")
        rows = c.fetchall()
        conn.close()
        
        batch = []
        for state, game, draw_date, numbers_str in rows:
            if not numbers_str:
                continue
            # Parse numbers
            if '-' in numbers_str:
                nums = numbers_str.split('-')
            else:
                nums = list(numbers_str)
            if len(nums) != 5:
                continue
            
            key = create_unique_key(state, game, draw_date, nums)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            state_name = STATE_NAMES.get(state.lower(), state)
            doc = {
                'country': 'United States',
                'state': state.lower(),
                'state_name': state_name,
                'game': game,
                'game_name': game.replace('-', ' ').title(),
                'game_type': 'pick5',
                'date': datetime.strptime(draw_date, '%Y-%m-%d'),
                'numbers': json.dumps(nums),
                'number_str': ''.join(nums),
                'normalized': ''.join(sorted(nums)),
                'digits_sum': sum(int(d) for d in nums),
                'pairs_2dp': sorted(set(''.join(sorted(p)) for p in combinations(nums, 2))),
                'triples_3dp': sorted(set(''.join(sorted(t)) for t in combinations(nums, 3))),
                'tod': get_tod(game),
                'num_digits': 5,
                'source': 'sqlite',
            }
            batch.append(doc)
            
            if len(batch) >= 5000:
                coll.insert_many(batch)
                phase2_count += len(batch)
                total_inserted += len(batch)
                print(f"   Inserted {phase2_count:,}...")
                batch = []
        
        if batch:
            coll.insert_many(batch)
            phase2_count += len(batch)
            total_inserted += len(batch)
        
        print(f"   ✅ SQLite Pick 5: {phase2_count:,} records")
    
    # ===================
    # PHASE 3: Supabase (Pick 2-5, fills gaps)
    # ===================
    print(f"\n📥 Phase 3: Supabase (filling gaps)...")
    phase3_count = 0
    try:
        pg_conn = get_supabase_conn()
        pg_cur = pg_conn.cursor()
        
        # Get distinct records for Pick 2-5 only
        pg_cur.execute("""
            SELECT DISTINCT ON (s.name, g.name, d.draw_date, d.value)
                s.name as state_name,
                g.name as game_name,
                d.draw_date,
                d.value,
                d.sorted_value,
                d.sums
            FROM draws d
            JOIN games g ON d.game_id = g.id
            JOIN states s ON g.state_id = s.id
            WHERE LENGTH(REPLACE(d.value, '-', '')) BETWEEN 2 AND 5
            ORDER BY s.name, g.name, d.draw_date, d.value
        """)
        
        batch = []
        for state_name, game_name, draw_date, value, sorted_value, sums in pg_cur:
            if not value:
                continue
            
            # Parse numbers
            nums = value.split('-') if '-' in value else list(value)
            num_digits = len(nums)
            
            # Get state code
            state_code = STATE_CODES.get(state_name, state_name[:2].lower() if state_name else 'xx')
            
            # Check if already seen
            key = create_unique_key(state_code, game_name, draw_date, nums)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            doc = {
                'country': 'United States',
                'state': state_code,
                'state_name': state_name,
                'game': game_name.lower().replace(' ', '-'),
                'game_name': game_name,
                'game_type': f'pick{num_digits}',
                'date': datetime.combine(draw_date, datetime.min.time()),
                'numbers': json.dumps(nums),
                'number_str': ''.join(nums),
                'normalized': ''.join(sorted(nums)),
                'digits_sum': sums or sum(int(d) for d in nums if d.isdigit()),
                'pairs_2dp': sorted(set(''.join(sorted(p)) for p in combinations(nums, 2))) if num_digits >= 4 else [],
                'triples_3dp': sorted(set(''.join(sorted(t)) for t in combinations(nums, 3))) if num_digits >= 5 else [],
                'tod': get_tod(game_name),
                'num_digits': num_digits,
                'source': 'supabase',
            }
            batch.append(doc)
            
            if len(batch) >= 5000:
                coll.insert_many(batch)
                phase3_count += len(batch)
                total_inserted += len(batch)
                print(f"   Inserted {phase3_count:,} from Supabase...")
                batch = []
        
        if batch:
            coll.insert_many(batch)
            phase3_count += len(batch)
            total_inserted += len(batch)
        
        pg_conn.close()
        print(f"   ✅ Supabase gaps: {phase3_count:,} records")
        
    except Exception as e:
        print(f"   ⚠️ Supabase error: {e}")
    
    # ===================
    # Create indexes
    # ===================
    print(f"\n📊 Creating indexes...")
    coll.create_index([('state_name', 1), ('game_name', 1), ('date', -1)])
    coll.create_index([('state', 1), ('game_type', 1), ('date', -1)])
    coll.create_index([('normalized', 1)])
    coll.create_index([('number_str', 1)])
    coll.create_index([('date', -1)])
    coll.create_index([('game_type', 1)])
    coll.create_index([('state_name', 1), ('game_name', 1), ('date', 1)], unique=True)
    print("   ✅ Indexes created")
    
    # Final stats
    final_count = coll.count_documents({})
    
    print(f"\n{'='*70}")
    print("SETUP COMPLETE")
    print(f"{'='*70}")
    print(f"Total documents: {final_count:,}")
    for gt in ['pick2', 'pick3', 'pick4', 'pick5']:
        count = coll.count_documents({'game_type': gt})
        print(f"   {gt}: {count:,}")
    
    oldest = coll.find_one(sort=[('date', 1)])
    newest = coll.find_one(sort=[('date', -1)])
    print(f"Date range: {oldest['date'].strftime('%Y-%m-%d')} to {newest['date'].strftime('%Y-%m-%d')}")
    
    # Source breakdown
    sqlite_count = coll.count_documents({'source': 'sqlite'})
    supa_count = coll.count_documents({'source': 'supabase'})
    print(f"\nBy source:")
    print(f"   SQLite: {sqlite_count:,}")
    print(f"   Supabase (gaps): {supa_count:,}")
    
    client.close()
    print(f"\n✅ Done!")


# =============================================================================
# DAILY SYNC
# =============================================================================

def sync_new_data():
    """Sync only new data from lotterycorner.com."""
    import requests
    from bs4 import BeautifulSoup
    
    print(f"\n{'='*70}")
    print("DAILY SYNC")
    print(f"{'='*70}")
    
    # Games to sync
    GAMES = [
        # Pick 4
        ('fl', 'pick-4-midday', 'Florida', 'Pick 4 Midday', 4),
        ('fl', 'pick-4-evening', 'Florida', 'Pick 4 Evening', 4),
        ('ga', 'cash-4-midday', 'Georgia', 'Cash 4 Midday', 4),
        ('ga', 'cash-4-evening', 'Georgia', 'Cash 4 Evening', 4),
        ('tx', 'daily-4-day', 'Texas', 'Daily 4 Day', 4),
        ('tx', 'daily-4-night', 'Texas', 'Daily 4 Night', 4),
        ('oh', 'pick-4-midday', 'Ohio', 'Pick 4 Midday', 4),
        ('oh', 'pick-4-evening', 'Ohio', 'Pick 4 Evening', 4),
        ('pa', 'pick-4-midday', 'Pennsylvania', 'Pick 4 Midday', 4),
        ('pa', 'pick-4-evening', 'Pennsylvania', 'Pick 4 Evening', 4),
        ('ca', 'daily-4', 'California', 'Daily 4', 4),
        ('ny', 'win-4-midday', 'New York', 'Win 4 Midday', 4),
        ('ny', 'win-4-evening', 'New York', 'Win 4 Evening', 4),
        ('nj', 'pick-4-midday', 'New Jersey', 'Pick 4 Midday', 4),
        ('nj', 'pick-4-evening', 'New Jersey', 'Pick 4 Evening', 4),
        ('il', 'pick-4-midday', 'Illinois', 'Pick 4 Midday', 4),
        ('il', 'pick-4-evening', 'Illinois', 'Pick 4 Evening', 4),
        ('md', 'pick-4-midday', 'Maryland', 'Pick 4 Midday', 4),
        ('md', 'pick-4-evening', 'Maryland', 'Pick 4 Evening', 4),
        ('va', 'pick-4-day', 'Virginia', 'Pick 4 Day', 4),
        ('va', 'pick-4-night', 'Virginia', 'Pick 4 Night', 4),
        ('mi', 'daily-4-midday', 'Michigan', 'Daily 4 Midday', 4),
        ('mi', 'daily-4-evening', 'Michigan', 'Daily 4 Evening', 4),
        ('nc', 'pick-4-day', 'North Carolina', 'Pick 4 Day', 4),
        ('nc', 'pick-4-evening', 'North Carolina', 'Pick 4 Evening', 4),
        # Pick 5
        ('fl', 'pick-5-midday', 'Florida', 'Pick 5 Midday', 5),
        ('fl', 'pick-5-evening', 'Florida', 'Pick 5 Evening', 5),
        ('oh', 'pick-5-midday', 'Ohio', 'Pick 5 Midday', 5),
        ('oh', 'pick-5-evening', 'Ohio', 'Pick 5 Evening', 5),
        ('pa', 'pick-5-midday', 'Pennsylvania', 'Pick 5 Midday', 5),
        ('pa', 'pick-5-evening', 'Pennsylvania', 'Pick 5 Evening', 5),
        ('ga', 'georgia-five-midday', 'Georgia', 'Georgia Five Midday', 5),
        ('ga', 'georgia-five-evening', 'Georgia', 'Georgia Five Evening', 5),
        # Pick 3
        ('fl', 'pick-3-midday', 'Florida', 'Pick 3 Midday', 3),
        ('fl', 'pick-3-evening', 'Florida', 'Pick 3 Evening', 3),
        ('ga', 'cash-3-midday', 'Georgia', 'Cash 3 Midday', 3),
        ('ga', 'cash-3-evening', 'Georgia', 'Cash 3 Evening', 3),
    ]
    
    def scrape_current_year(state, slug, digits):
        year = datetime.now().year
        url = f"https://www.lotterycorner.com/{state}/{slug}/{year}"
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, 'html.parser')
            draws = []
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2:
                    try:
                        date = datetime.strptime(cells[0].get_text(strip=True), '%B %d, %Y').date()
                        nums = re.findall(r'\d', cells[1].get_text())[:digits]
                        if len(nums) == digits:
                            draws.append((date, nums))
                    except:
                        pass
            return draws
        except:
            return []
    
    client = get_mongo_client()
    coll = client[MONGO_DB][MONGO_COLLECTION]
    
    today = datetime.now().date()
    total_added = 0
    
    for state_code, slug, state_name, game_name, digits in GAMES:
        # Get latest in MongoDB
        latest_doc = coll.find_one(
            {'state_name': state_name, 'game_name': game_name},
            sort=[('date', -1)]
        )
        latest_date = latest_doc['date'].date() if latest_doc else None
        
        if latest_date and (today - latest_date).days <= 0:
            continue
        
        draws = scrape_current_year(state_code, slug, digits)
        added = 0
        
        for draw_date, nums in draws:
            if latest_date and draw_date <= latest_date:
                continue
            if draw_date > today:
                continue
            
            doc = {
                'country': 'United States',
                'state': state_code,
                'state_name': state_name,
                'game': slug,
                'game_name': game_name,
                'game_type': f'pick{digits}',
                'date': datetime.combine(draw_date, datetime.min.time()),
                'numbers': json.dumps(nums),
                'number_str': ''.join(nums),
                'normalized': ''.join(sorted(nums)),
                'digits_sum': sum(int(d) for d in nums),
                'pairs_2dp': sorted(set(''.join(sorted(p)) for p in combinations(nums, 2))) if digits >= 4 else [],
                'triples_3dp': sorted(set(''.join(sorted(t)) for t in combinations(nums, 3))) if digits >= 5 else [],
                'tod': get_tod(game_name),
                'num_digits': digits,
                'source': 'sync',
            }
            
            try:
                coll.update_one(
                    {'state_name': state_name, 'game_name': game_name, 'date': doc['date']},
                    {'$set': doc},
                    upsert=True
                )
                added += 1
            except:
                pass
        
        if added > 0:
            print(f"   ✅ {state_name} {game_name}: +{added}")
            total_added += added
        
        time.sleep(0.1)
    
    client.close()
    
    print(f"\n{'='*70}")
    print(f"SYNC COMPLETE: +{total_added} new draws")
    print(f"{'='*70}\n")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Lottery data management')
    parser.add_argument('--status', action='store_true', help='Show database status')
    parser.add_argument('--compare', action='store_true', help='Compare databases')
    parser.add_argument('--full-setup', action='store_true', help='Full merge: SQLite + Supabase → MongoDB')
    parser.add_argument('--sync', action='store_true', help='Daily sync new data')
    args = parser.parse_args()
    
    if args.full_setup:
        full_setup()
    elif args.sync:
        sync_new_data()
    elif args.compare:
        # Import compare function from previous version
        print("Run: python3 lottery_master_sync.py --status")
        print("Then compare manually or use --full-setup to merge all data")
    else:
        show_status()


if __name__ == '__main__':
    main()
