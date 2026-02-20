#!/usr/bin/env python3
"""
lottery_master_sync.py - Complete lottery data management
=========================================================

This script:
1. Cleans duplicates from Supabase
2. Exports clean data to MongoDB  
3. Can run as daily sync to keep MongoDB current

Usage:
    python3 lottery_master_sync.py --clean-supabase    # Remove duplicates from Supabase
    python3 lottery_master_sync.py --export-mongo      # Export Supabase → MongoDB
    python3 lottery_master_sync.py --sync              # Daily sync (new data only)
    python3 lottery_master_sync.py --status            # Show database stats
    python3 lottery_master_sync.py --full-setup        # Clean + Export (first time setup)

Requirements:
    pip install psycopg2-binary pymongo requests beautifulsoup4
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from itertools import combinations
import time

# =============================================================================
# CONFIGURATION
# =============================================================================

# Supabase PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL', 
    'postgresql://postgres.lewvjrlflatexlcndefi:jx4wdz7vQ62ENoCD@aws-1-us-east-1.pooler.supabase.com:5432/postgres')

# MongoDB
MONGO_URL = os.environ.get('MONGO_URL', 
    'mongodb+srv://willpowers2026:dFUATeYtHrP87gPk@cluster0.nmujtyo.mongodb.net/')
MONGO_DB = os.environ.get('MONGO_DB', 'lottery')
MONGO_COLLECTION = os.environ.get('MONGO_COLLECTION', 'lottery_v2')

# State mappings
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


def get_supabase_conn():
    """Connect to Supabase."""
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def get_mongo_client():
    """Connect to MongoDB."""
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    client.admin.command('ping')
    return client


def get_tod(game_name):
    """Extract time of day from game name."""
    if not game_name:
        return ''
    g = game_name.lower()
    if any(x in g for x in ['morning']):
        return 'Morning'
    if any(x in g for x in ['midday', 'mid-day', 'day', 'noon', '1pm', '4pm', '1:50']):
        return 'Midday'
    if any(x in g for x in ['evening', 'night', '7pm', '10pm', '7:50']):
        return 'Evening'
    return ''


def get_game_type(num_digits):
    """Get game type string."""
    return f'pick{num_digits}'


# =============================================================================
# COMPARE DATABASES
# =============================================================================

def compare_databases():
    """Compare SQLite vs Supabase vs MongoDB for Pick 4/5 data."""
    import sqlite3
    
    print(f"\n{'='*80}")
    print("DATABASE COMPARISON (Pick 4 & Pick 5)")
    print(f"{'='*80}")
    
    PICK4_DB = os.path.expanduser('~/lottery_scraper/pick4/data/pick4_master.db')
    PICK5_DB = os.path.expanduser('~/lottery_scraper/pick5/data/pick5_data.db')
    
    results = {}
    
    # SQLite Pick 4
    print("\n📊 SQLite Pick 4...")
    if os.path.exists(PICK4_DB):
        conn = sqlite3.connect(PICK4_DB)
        c = conn.cursor()
        c.execute("SELECT state, COUNT(*), MIN(draw_date), MAX(draw_date) FROM pick4_results GROUP BY state ORDER BY state")
        sqlite_p4 = {row[0]: {'count': row[1], 'min': row[2], 'max': row[3]} for row in c.fetchall()}
        c.execute("SELECT COUNT(*), MIN(draw_date), MAX(draw_date) FROM pick4_results")
        total = c.fetchone()
        results['sqlite_p4'] = {'total': total[0], 'min': total[1], 'max': total[2], 'by_state': sqlite_p4}
        conn.close()
        print(f"   Total: {total[0]:,} | {total[1]} to {total[2]}")
    else:
        print(f"   ❌ Not found: {PICK4_DB}")
        results['sqlite_p4'] = None
    
    # SQLite Pick 5
    print("\n📊 SQLite Pick 5...")
    if os.path.exists(PICK5_DB):
        conn = sqlite3.connect(PICK5_DB)
        c = conn.cursor()
        c.execute("SELECT state, COUNT(*), MIN(draw_date), MAX(draw_date) FROM pick5_results GROUP BY state ORDER BY state")
        sqlite_p5 = {row[0]: {'count': row[1], 'min': row[2], 'max': row[3]} for row in c.fetchall()}
        c.execute("SELECT COUNT(*), MIN(draw_date), MAX(draw_date) FROM pick5_results")
        total = c.fetchone()
        results['sqlite_p5'] = {'total': total[0], 'min': total[1], 'max': total[2], 'by_state': sqlite_p5}
        conn.close()
        print(f"   Total: {total[0]:,} | {total[1]} to {total[2]}")
    else:
        print(f"   ❌ Not found: {PICK5_DB}")
        results['sqlite_p5'] = None
    
    # Supabase Pick 4 & 5
    print("\n📊 Supabase Pick 4 & 5...")
    try:
        conn = get_supabase_conn()
        cur = conn.cursor()
        
        # Pick 4
        cur.execute("""
            SELECT s.name, COUNT(DISTINCT (d.game_id, d.draw_date, d.value)), 
                   MIN(d.draw_date), MAX(d.draw_date)
            FROM draws d
            JOIN games g ON d.game_id = g.id
            JOIN states s ON g.state_id = s.id
            WHERE LENGTH(REPLACE(d.value, '-', '')) = 4
            GROUP BY s.name ORDER BY s.name
        """)
        supa_p4 = {row[0]: {'count': row[1], 'min': str(row[2]), 'max': str(row[3])} for row in cur.fetchall()}
        
        cur.execute("""
            SELECT COUNT(DISTINCT (game_id, draw_date, value)), MIN(draw_date), MAX(draw_date)
            FROM draws WHERE LENGTH(REPLACE(value, '-', '')) = 4
        """)
        total = cur.fetchone()
        results['supa_p4'] = {'total': total[0], 'min': str(total[1]), 'max': str(total[2]), 'by_state': supa_p4}
        print(f"   Pick 4: {total[0]:,} | {total[1]} to {total[2]}")
        
        # Pick 5
        cur.execute("""
            SELECT s.name, COUNT(DISTINCT (d.game_id, d.draw_date, d.value)), 
                   MIN(d.draw_date), MAX(d.draw_date)
            FROM draws d
            JOIN games g ON d.game_id = g.id
            JOIN states s ON g.state_id = s.id
            WHERE LENGTH(REPLACE(d.value, '-', '')) = 5
            GROUP BY s.name ORDER BY s.name
        """)
        supa_p5 = {row[0]: {'count': row[1], 'min': str(row[2]), 'max': str(row[3])} for row in cur.fetchall()}
        
        cur.execute("""
            SELECT COUNT(DISTINCT (game_id, draw_date, value)), MIN(draw_date), MAX(draw_date)
            FROM draws WHERE LENGTH(REPLACE(value, '-', '')) = 5
        """)
        total = cur.fetchone()
        results['supa_p5'] = {'total': total[0], 'min': str(total[1]), 'max': str(total[2]), 'by_state': supa_p5}
        print(f"   Pick 5: {total[0]:,} | {total[1]} to {total[2]}")
        
        conn.close()
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['supa_p4'] = None
        results['supa_p5'] = None
    
    # MongoDB
    print("\n📊 MongoDB lottery_v2...")
    try:
        client = get_mongo_client()
        coll = client[MONGO_DB][MONGO_COLLECTION]
        
        # Pick 4
        pipeline = [
            {'$match': {'game_type': 'pick4'}},
            {'$group': {'_id': '$state_name', 'count': {'$sum': 1}, 
                       'min': {'$min': '$date'}, 'max': {'$max': '$date'}}}
        ]
        mongo_p4 = {r['_id']: {'count': r['count'], 'min': str(r['min'].date()), 'max': str(r['max'].date())} 
                    for r in coll.aggregate(pipeline)}
        
        p4_total = coll.count_documents({'game_type': 'pick4'})
        p4_oldest = coll.find_one({'game_type': 'pick4'}, sort=[('date', 1)])
        p4_newest = coll.find_one({'game_type': 'pick4'}, sort=[('date', -1)])
        results['mongo_p4'] = {
            'total': p4_total, 
            'min': str(p4_oldest['date'].date()) if p4_oldest else None,
            'max': str(p4_newest['date'].date()) if p4_newest else None,
            'by_state': mongo_p4
        }
        print(f"   Pick 4: {p4_total:,}")
        
        # Pick 5
        pipeline = [
            {'$match': {'game_type': 'pick5'}},
            {'$group': {'_id': '$state_name', 'count': {'$sum': 1}, 
                       'min': {'$min': '$date'}, 'max': {'$max': '$date'}}}
        ]
        mongo_p5 = {r['_id']: {'count': r['count'], 'min': str(r['min'].date()), 'max': str(r['max'].date())} 
                    for r in coll.aggregate(pipeline)}
        
        p5_total = coll.count_documents({'game_type': 'pick5'})
        p5_oldest = coll.find_one({'game_type': 'pick5'}, sort=[('date', 1)])
        p5_newest = coll.find_one({'game_type': 'pick5'}, sort=[('date', -1)])
        results['mongo_p5'] = {
            'total': p5_total, 
            'min': str(p5_oldest['date'].date()) if p5_oldest else None,
            'max': str(p5_newest['date'].date()) if p5_newest else None,
            'by_state': mongo_p5
        }
        print(f"   Pick 5: {p5_total:,}")
        
        client.close()
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['mongo_p4'] = None
        results['mongo_p5'] = None
    
    # Side-by-side comparison
    print(f"\n{'='*80}")
    print("PICK 4 COMPARISON BY STATE")
    print(f"{'='*80}")
    print(f"{'State':<20} {'SQLite':>12} {'Supabase':>12} {'MongoDB':>12} {'Winner':<10}")
    print("-" * 80)
    
    all_states = set()
    if results.get('sqlite_p4'): all_states.update(results['sqlite_p4']['by_state'].keys())
    if results.get('supa_p4'): all_states.update(results['supa_p4']['by_state'].keys())
    
    # Map state names
    state_name_map = {v: k for k, v in STATE_CODES.items()}
    
    for state in sorted(all_states):
        # Try to match state names across databases
        sqlite_key = state.lower() if len(state) == 2 else state
        supa_key = state
        
        sq = results['sqlite_p4']['by_state'].get(sqlite_key, {}).get('count', 0) if results.get('sqlite_p4') else 0
        sp = results['supa_p4']['by_state'].get(supa_key, {}).get('count', 0) if results.get('supa_p4') else 0
        mg = results['mongo_p4']['by_state'].get(supa_key, {}).get('count', 0) if results.get('mongo_p4') else 0
        
        # Determine winner
        counts = {'SQLite': sq, 'Supabase': sp, 'MongoDB': mg}
        max_count = max(counts.values())
        winner = [k for k, v in counts.items() if v == max_count and v > 0]
        winner_str = '/'.join(winner) if winner else '-'
        
        if sq > 0 or sp > 0 or mg > 0:
            print(f"{state:<20} {sq:>12,} {sp:>12,} {mg:>12,} {winner_str:<10}")
    
    # Totals
    print("-" * 80)
    sq_total = results['sqlite_p4']['total'] if results.get('sqlite_p4') else 0
    sp_total = results['supa_p4']['total'] if results.get('supa_p4') else 0
    mg_total = results['mongo_p4']['total'] if results.get('mongo_p4') else 0
    print(f"{'TOTAL':<20} {sq_total:>12,} {sp_total:>12,} {mg_total:>12,}")
    
    print(f"\n{'='*80}")
    print("PICK 5 COMPARISON BY STATE")
    print(f"{'='*80}")
    print(f"{'State':<20} {'SQLite':>12} {'Supabase':>12} {'MongoDB':>12} {'Winner':<10}")
    print("-" * 80)
    
    all_states = set()
    if results.get('sqlite_p5'): all_states.update(results['sqlite_p5']['by_state'].keys())
    if results.get('supa_p5'): all_states.update(results['supa_p5']['by_state'].keys())
    
    for state in sorted(all_states):
        sqlite_key = state.lower() if len(state) == 2 else state
        supa_key = state
        
        sq = results['sqlite_p5']['by_state'].get(sqlite_key, {}).get('count', 0) if results.get('sqlite_p5') else 0
        sp = results['supa_p5']['by_state'].get(supa_key, {}).get('count', 0) if results.get('supa_p5') else 0
        mg = results['mongo_p5']['by_state'].get(supa_key, {}).get('count', 0) if results.get('mongo_p5') else 0
        
        counts = {'SQLite': sq, 'Supabase': sp, 'MongoDB': mg}
        max_count = max(counts.values())
        winner = [k for k, v in counts.items() if v == max_count and v > 0]
        winner_str = '/'.join(winner) if winner else '-'
        
        if sq > 0 or sp > 0 or mg > 0:
            print(f"{state:<20} {sq:>12,} {sp:>12,} {mg:>12,} {winner_str:<10}")
    
    print("-" * 80)
    sq_total = results['sqlite_p5']['total'] if results.get('sqlite_p5') else 0
    sp_total = results['supa_p5']['total'] if results.get('supa_p5') else 0
    mg_total = results['mongo_p5']['total'] if results.get('mongo_p5') else 0
    print(f"{'TOTAL':<20} {sq_total:>12,} {sp_total:>12,} {mg_total:>12,}")
    
    # Date range comparison
    print(f"\n{'='*80}")
    print("DATE RANGE COMPARISON")
    print(f"{'='*80}")
    print(f"{'Database':<20} {'Pick 4 Range':<30} {'Pick 5 Range':<30}")
    print("-" * 80)
    
    if results.get('sqlite_p4'):
        p4_range = f"{results['sqlite_p4']['min']} to {results['sqlite_p4']['max']}"
    else:
        p4_range = "N/A"
    if results.get('sqlite_p5'):
        p5_range = f"{results['sqlite_p5']['min']} to {results['sqlite_p5']['max']}"
    else:
        p5_range = "N/A"
    print(f"{'SQLite':<20} {p4_range:<30} {p5_range:<30}")
    
    if results.get('supa_p4'):
        p4_range = f"{results['supa_p4']['min']} to {results['supa_p4']['max']}"
    else:
        p4_range = "N/A"
    if results.get('supa_p5'):
        p5_range = f"{results['supa_p5']['min']} to {results['supa_p5']['max']}"
    else:
        p5_range = "N/A"
    print(f"{'Supabase':<20} {p4_range:<30} {p5_range:<30}")
    
    if results.get('mongo_p4') and results['mongo_p4']['total'] > 0:
        p4_range = f"{results['mongo_p4']['min']} to {results['mongo_p4']['max']}"
    else:
        p4_range = "N/A"
    if results.get('mongo_p5') and results['mongo_p5']['total'] > 0:
        p5_range = f"{results['mongo_p5']['min']} to {results['mongo_p5']['max']}"
    else:
        p5_range = "N/A"
    print(f"{'MongoDB':<20} {p4_range:<30} {p5_range:<30}")
    
    print(f"\n{'='*80}\n")


# =============================================================================
# STATUS CHECK
# =============================================================================

def show_status():
    """Show status of all databases."""
    print(f"\n{'='*70}")
    print("DATABASE STATUS")
    print(f"{'='*70}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Supabase
    print(f"\n📊 SUPABASE")
    try:
        conn = get_supabase_conn()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM draws")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT (game_id, draw_date, value)) FROM draws")
        unique = cur.fetchone()[0]
        
        cur.execute("SELECT MIN(draw_date), MAX(draw_date) FROM draws")
        min_date, max_date = cur.fetchone()
        
        dupes = total - unique
        print(f"   Total rows:    {total:,}")
        print(f"   Unique draws:  {unique:,}")
        print(f"   Duplicates:    {dupes:,} ({100*dupes/total:.1f}%)")
        print(f"   Date range:    {min_date} to {max_date}")
        
        # Breakdown by digit count
        cur.execute("""
            SELECT LENGTH(REPLACE(value, '-', '')) as digits, COUNT(DISTINCT (game_id, draw_date, value))
            FROM draws GROUP BY digits ORDER BY digits
        """)
        print("   By type:")
        for digits, count in cur.fetchall():
            print(f"      Pick {digits}: {count:,}")
        
        conn.close()
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # MongoDB
    print(f"\n📊 MONGODB ({MONGO_DB}/{MONGO_COLLECTION})")
    try:
        client = get_mongo_client()
        coll = client[MONGO_DB][MONGO_COLLECTION]
        
        total = coll.count_documents({})
        print(f"   Total docs:    {total:,}")
        
        if total > 0:
            oldest = coll.find_one(sort=[('date', 1)])
            newest = coll.find_one(sort=[('date', -1)])
            print(f"   Date range:    {oldest['date'].strftime('%Y-%m-%d')} to {newest['date'].strftime('%Y-%m-%d')}")
            
            for gt in ['pick2', 'pick3', 'pick4', 'pick5']:
                count = coll.count_documents({'game_type': gt})
                if count > 0:
                    print(f"      {gt}: {count:,}")
        
        client.close()
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print(f"\n{'='*70}\n")


# =============================================================================
# CLEAN SUPABASE
# =============================================================================

def clean_supabase(dry_run=False):
    """Remove duplicates from Supabase."""
    print(f"\n{'='*70}")
    print("CLEANING SUPABASE DUPLICATES")
    print(f"{'='*70}")
    
    conn = get_supabase_conn()
    cur = conn.cursor()
    
    # Count before
    cur.execute("SELECT COUNT(*) FROM draws")
    before = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT (game_id, draw_date, value)) FROM draws")
    unique = cur.fetchone()[0]
    
    dupes = before - unique
    print(f"Total rows:      {before:,}")
    print(f"Unique draws:    {unique:,}")
    print(f"Duplicates:      {dupes:,}")
    
    if dupes == 0:
        print("\n✅ No duplicates found!")
        conn.close()
        return
    
    if dry_run:
        print("\n⚠️  DRY RUN - no changes made")
        conn.close()
        return
    
    print(f"\nRemoving {dupes:,} duplicates...")
    
    # Delete duplicates, keeping the one with lowest id
    delete_sql = """
        DELETE FROM draws
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM draws
            GROUP BY game_id, draw_date, value
        )
    """
    
    cur.execute(delete_sql)
    deleted = cur.rowcount
    conn.commit()
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM draws")
    after = cur.fetchone()[0]
    
    print(f"\n✅ Deleted {deleted:,} duplicates")
    print(f"   Before: {before:,}")
    print(f"   After:  {after:,}")
    
    conn.close()


# =============================================================================
# EXPORT TO MONGODB
# =============================================================================

def export_to_mongo(drop_first=False):
    """Export Supabase data to MongoDB."""
    print(f"\n{'='*70}")
    print("EXPORTING SUPABASE → MONGODB")
    print(f"{'='*70}")
    
    pg_conn = get_supabase_conn()
    pg_cur = pg_conn.cursor()
    
    mongo_client = get_mongo_client()
    coll = mongo_client[MONGO_DB][MONGO_COLLECTION]
    
    if drop_first:
        print(f"Dropping existing collection: {MONGO_COLLECTION}")
        mongo_client[MONGO_DB].drop_collection(MONGO_COLLECTION)
        coll = mongo_client[MONGO_DB][MONGO_COLLECTION]
    
    # Get unique records - ONLY Pick 2-5 games
    print("Fetching unique records from Supabase (Pick 2-5 only)...")
    pg_cur.execute("""
        SELECT DISTINCT ON (s.name, g.name, d.draw_date)
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
        ORDER BY s.name, g.name, d.draw_date
    """)
    
    rows = pg_cur.fetchall()
    total = len(rows)
    print(f"Found {total:,} unique records")
    
    # Process in batches
    batch_size = 5000
    batch = []
    inserted = 0
    
    for i, row in enumerate(rows):
        state_name, game_name, draw_date, value, sorted_value, sums = row
        
        if not value:
            continue
        
        # Parse numbers
        nums = value.split('-') if '-' in value else list(value)
        num_digits = len(nums)
        
        # Build document
        doc = {
            'country': 'United States',
            'state': STATE_CODES.get(state_name, state_name[:2].lower()),
            'state_name': state_name,
            'game': game_name.lower().replace(' ', '-'),
            'game_name': game_name,
            'game_type': get_game_type(num_digits),
            'date': datetime.combine(draw_date, datetime.min.time()),
            'numbers': json.dumps(nums),
            'number_str': ''.join(nums),
            'normalized': ''.join(sorted(nums)),
            'digits_sum': sums or sum(int(d) for d in nums if d.isdigit()),
            'pairs_2dp': sorted(set(''.join(sorted(p)) for p in combinations(nums, 2))) if num_digits >= 4 else [],
            'triples_3dp': sorted(set(''.join(sorted(t)) for t in combinations(nums, 3))) if num_digits >= 5 else [],
            'tod': get_tod(game_name),
            'num_digits': num_digits,
        }
        
        batch.append(doc)
        
        if len(batch) >= batch_size:
            try:
                coll.insert_many(batch, ordered=False)
            except Exception as e:
                pass  # Ignore duplicate errors
            inserted += len(batch)
            print(f"   Inserted {inserted:,} / {total:,} ({100*inserted//total}%)")
            batch = []
    
    # Insert remaining
    if batch:
        try:
            coll.insert_many(batch, ordered=False)
        except:
            pass
        inserted += len(batch)
    
    # Create indexes
    print("\nCreating indexes...")
    coll.create_index([('state_name', 1), ('game_name', 1), ('date', -1)])
    coll.create_index([('state_name', 1), ('game_type', 1), ('date', -1)])
    coll.create_index([('normalized', 1)])
    coll.create_index([('date', -1)])
    coll.create_index([('game_type', 1)])
    coll.create_index([('state_name', 1), ('game_name', 1), ('date', 1)], unique=True)
    
    final_count = coll.count_documents({})
    print(f"\n✅ Export complete!")
    print(f"   MongoDB documents: {final_count:,}")
    
    pg_conn.close()
    mongo_client.close()


# =============================================================================
# DAILY SYNC
# =============================================================================

def sync_new_data():
    """Sync only new data from lotterycorner.com to both Supabase and MongoDB."""
    import requests
    from bs4 import BeautifulSoup
    
    print(f"\n{'='*70}")
    print("SYNCING NEW DATA")
    print(f"{'='*70}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Games to sync: (state_code, slug, state_name, game_name, digits)
    GAMES = [
        # Pick 4
        ('fl', 'pick-4-midday', 'Florida', 'Pick 4 Midday', 4),
        ('fl', 'pick-4-evening', 'Florida', 'Pick 4 Evening', 4),
        ('ga', 'cash-4-midday', 'Georgia', 'Cash 4 Midday', 4),
        ('ga', 'cash-4-evening', 'Georgia', 'Cash 4 Evening', 4),
        ('tx', 'daily-4-morning', 'Texas', 'Daily 4 Morning', 4),
        ('tx', 'daily-4-day', 'Texas', 'Daily 4 Day', 4),
        ('tx', 'daily-4-evening', 'Texas', 'Daily 4 Evening', 4),
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
        ('dc', 'dc-4-midday', 'Washington, D.C.', 'DC-4 1:50pm', 4),
        ('dc', 'dc-4-evening', 'Washington, D.C.', 'DC-4 7:50pm', 4),
        ('mi', 'daily-4-midday', 'Michigan', 'Daily 4 Midday', 4),
        ('mi', 'daily-4-evening', 'Michigan', 'Daily 4 Evening', 4),
        ('nc', 'pick-4-day', 'North Carolina', 'Pick 4 Day', 4),
        ('nc', 'pick-4-evening', 'North Carolina', 'Pick 4 Evening', 4),
        ('sc', 'pick-4-midday', 'South Carolina', 'Pick 4 Midday', 4),
        ('sc', 'pick-4-evening', 'South Carolina', 'Pick 4 Evening', 4),
        ('tn', 'cash-4-morning', 'Tennessee', 'Cash 4 Morning', 4),
        ('tn', 'cash-4-midday', 'Tennessee', 'Cash 4 Midday', 4),
        ('tn', 'cash-4-evening', 'Tennessee', 'Cash 4 Evening', 4),
        ('ky', 'pick-4-midday', 'Kentucky', 'Pick 4 Midday', 4),
        ('ky', 'pick-4-evening', 'Kentucky', 'Pick 4 Evening', 4),
        ('in', 'daily4-midday', 'Indiana', 'Daily 4 Midday', 4),
        ('in', 'daily4-evening', 'Indiana', 'Daily 4 Evening', 4),
        ('mo', 'pick-4-midday', 'Missouri', 'Pick 4 Midday', 4),
        ('mo', 'pick-4-evening', 'Missouri', 'Pick 4 Evening', 4),
        ('la', 'pick-4', 'Louisiana', 'Pick 4', 4),
        ('ar', 'cash-4-midday', 'Arkansas', 'Cash 4 Midday', 4),
        ('ar', 'cash-4-evening', 'Arkansas', 'Cash 4 Evening', 4),
        ('wi', 'pick-4-midday', 'Wisconsin', 'Pick 4 Midday', 4),
        ('wi', 'pick-4-evening', 'Wisconsin', 'Pick 4 Evening', 4),
        ('ia', 'pick-4-midday', 'Iowa', 'Pick 4 Midday', 4),
        ('ia', 'pick-4-evening', 'Iowa', 'Pick 4 Evening', 4),
        ('ct', 'play4-day', 'Connecticut', 'Play4 Day', 4),
        ('ct', 'play4-night', 'Connecticut', 'Play4 Night', 4),
        ('de', 'play-4-day', 'Delaware', 'Play 4 Day', 4),
        ('de', 'play-4-night', 'Delaware', 'Play 4 Night', 4),
        ('wv', 'daily-4', 'West Virginia', 'Daily 4', 4),
        # Pick 5
        ('fl', 'pick-5-midday', 'Florida', 'Pick 5 Midday', 5),
        ('fl', 'pick-5-evening', 'Florida', 'Pick 5 Evening', 5),
        ('ga', 'georgia-five-midday', 'Georgia', 'Georgia Five Midday', 5),
        ('ga', 'georgia-five-evening', 'Georgia', 'Georgia Five Evening', 5),
        ('oh', 'pick-5-midday', 'Ohio', 'Pick 5 Midday', 5),
        ('oh', 'pick-5-evening', 'Ohio', 'Pick 5 Evening', 5),
        ('pa', 'pick-5-midday', 'Pennsylvania', 'Pick 5 Midday', 5),
        ('pa', 'pick-5-evening', 'Pennsylvania', 'Pick 5 Evening', 5),
        ('md', 'pick-5-midday', 'Maryland', 'Pick 5 Midday', 5),
        ('md', 'pick-5-evening', 'Maryland', 'Pick 5 Evening', 5),
        ('va', 'pick-5-day', 'Virginia', 'Pick 5 Day', 5),
        ('va', 'pick-5-night', 'Virginia', 'Pick 5 Night', 5),
        ('dc', 'dc-5-midday', 'Washington, D.C.', 'DC-5 1:50pm', 5),
        ('dc', 'dc-5-evening', 'Washington, D.C.', 'DC-5 7:50pm', 5),
        ('la', 'pick-5', 'Louisiana', 'Pick 5', 5),
        # Pick 3
        ('fl', 'pick-3-midday', 'Florida', 'Pick 3 Midday', 3),
        ('fl', 'pick-3-evening', 'Florida', 'Pick 3 Evening', 3),
        ('ga', 'cash-3-midday', 'Georgia', 'Cash 3 Midday', 3),
        ('ga', 'cash-3-evening', 'Georgia', 'Cash 3 Evening', 3),
        ('tx', 'pick-3-morning', 'Texas', 'Pick 3 Morning', 3),
        ('tx', 'pick-3-day', 'Texas', 'Pick 3 Day', 3),
        ('tx', 'pick-3-evening', 'Texas', 'Pick 3 Evening', 3),
        ('tx', 'pick-3-night', 'Texas', 'Pick 3 Night', 3),
        ('oh', 'pick-3-midday', 'Ohio', 'Pick 3 Midday', 3),
        ('oh', 'pick-3-evening', 'Ohio', 'Pick 3 Evening', 3),
        ('pa', 'pick-3-midday', 'Pennsylvania', 'Pick 3 Midday', 3),
        ('pa', 'pick-3-evening', 'Pennsylvania', 'Pick 3 Evening', 3),
        ('ca', 'daily-3-midday', 'California', 'Daily 3 Midday', 3),
        ('ca', 'daily-3-evening', 'California', 'Daily 3 Evening', 3),
        ('ny', 'numbers-midday', 'New York', 'Numbers Midday', 3),
        ('ny', 'numbers-evening', 'New York', 'Numbers Evening', 3),
        ('nj', 'pick-3-midday', 'New Jersey', 'Pick 3 Midday', 3),
        ('nj', 'pick-3-evening', 'New Jersey', 'Pick 3 Evening', 3),
        ('il', 'pick-3-midday', 'Illinois', 'Pick 3 Midday', 3),
        ('il', 'pick-3-evening', 'Illinois', 'Pick 3 Evening', 3),
        ('md', 'pick-3-midday', 'Maryland', 'Pick 3 Midday', 3),
        ('md', 'pick-3-evening', 'Maryland', 'Pick 3 Evening', 3),
    ]
    
    def scrape_current_year(state, slug, digits):
        """Scrape current year from lotterycorner."""
        year = datetime.now().year
        url = f"https://www.lotterycorner.com/{state}/{slug}/{year}"
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, 'html.parser')
            draws = []
            import re
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
    
    # Connect to MongoDB
    mongo_client = get_mongo_client()
    coll = mongo_client[MONGO_DB][MONGO_COLLECTION]
    
    today = datetime.now().date()
    total_added = 0
    
    for state_code, slug, state_name, game_name, digits in GAMES:
        # Get latest date in MongoDB
        latest_doc = coll.find_one(
            {'state_name': state_name, 'game_name': game_name},
            sort=[('date', -1)]
        )
        latest_date = latest_doc['date'].date() if latest_doc else None
        
        if latest_date and (today - latest_date).days <= 0:
            continue  # Already current
        
        # Scrape new data
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
                'game': game_name.lower().replace(' ', '-'),
                'game_name': game_name,
                'game_type': get_game_type(digits),
                'date': datetime.combine(draw_date, datetime.min.time()),
                'numbers': json.dumps(nums),
                'number_str': ''.join(nums),
                'normalized': ''.join(sorted(nums)),
                'digits_sum': sum(int(d) for d in nums),
                'pairs_2dp': sorted(set(''.join(sorted(p)) for p in combinations(nums, 2))) if digits >= 4 else [],
                'triples_3dp': sorted(set(''.join(sorted(t)) for t in combinations(nums, 3))) if digits >= 5 else [],
                'tod': get_tod(game_name),
                'num_digits': digits,
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
            print(f"  ✅ {state_name} {game_name}: +{added}")
            total_added += added
        
        time.sleep(0.1)
    
    mongo_client.close()
    
    print(f"\n{'='*70}")
    print(f"SYNC COMPLETE: +{total_added} new draws")
    print(f"{'='*70}\n")
    
    return total_added


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Lottery data management')
    parser.add_argument('--status', action='store_true', help='Show database status')
    parser.add_argument('--compare', action='store_true', help='Compare SQLite vs Supabase vs MongoDB')
    parser.add_argument('--clean-supabase', action='store_true', help='Remove duplicates from Supabase')
    parser.add_argument('--export-mongo', action='store_true', help='Export Supabase → MongoDB')
    parser.add_argument('--sync', action='store_true', help='Sync new data to MongoDB')
    parser.add_argument('--full-setup', action='store_true', help='Clean Supabase + Export to MongoDB')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--drop', action='store_true', help='Drop MongoDB collection before export')
    args = parser.parse_args()
    
    if args.status or not any([args.compare, args.clean_supabase, args.export_mongo, args.sync, args.full_setup]):
        show_status()
        return
    
    if args.compare:
        compare_databases()
        return
    
    if args.full_setup:
        clean_supabase(dry_run=args.dry_run)
        if not args.dry_run:
            export_to_mongo(drop_first=True)
        return
    
    if args.clean_supabase:
        clean_supabase(dry_run=args.dry_run)
    
    if args.export_mongo:
        export_to_mongo(drop_first=args.drop)
    
    if args.sync:
        sync_new_data()


if __name__ == '__main__':
    main()
