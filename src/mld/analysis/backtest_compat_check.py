#!/usr/bin/env python3
"""
Backtest Compatibility Check
=============================
Simulates what the Flask app does when the backtest runs,
to find where data is getting lost.
"""

from pymongo import MongoClient
from datetime import datetime
import json

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def get_games_for_prediction(coll, state, game_type):
    """Exact copy of the function from app.py"""
    all_games = coll.distinct('game_name', {'state_name': state})
    patterns = {
        'pick2': ['pick 2', 'pick2', 'pick-2', 'daily 2', 'daily2', 'play 2', 'play2', 'dc 2', 'dc2', 'cash 2', 'cash2'],
        'pick3': ['pick 3', 'pick3', 'pick-3', 'daily 3', 'daily3', 'daily-3', 'dc-3', 'dc 3', 'dc3', 'cash 3', 'cash-3', 'cash3', 'play 3', 'play-3', 'play3'],
        'pick4': ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4', 'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4', 'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4',
                  'numbers game'],
        'pick5': [
            'pick 5 day', 'pick 5 evening', 'pick 5 midday',
            'play 5 day', 'play 5 night',
            'dc 5 evening', 'dc 5 midday',
            'georgia five evening', 'georgia five midday',
            'pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5',
            'dc 5', 'dc5', 'play 5', 'play5', 'georgia five', 'georgia 5',
        ],
    }
    pats = patterns.get(game_type.lower(), [game_type.lower()])
    matched = [g for g in all_games if any(p in g.lower() for p in pats)]
    
    # The filtering logic from app.py
    filtered = []
    for game in matched:
        game_lower = game.lower()
        is_parent = not any(tod in game_lower for tod in ['day', 'night', 'midday', 'evening'])
        if is_parent:
            has_child = any(
                g.lower().startswith(game_lower) and g.lower() != game_lower 
                for g in matched
            )
            if has_child:
                continue
        filtered.append(game)
    
    return filtered if filtered else matched

def run():
    client = MongoClient(MONGO_URL)
    coll = client["lottery"]["lottery_v2"]
    
    test_states = ["Florida", "Georgia", "Ohio", "Pennsylvania", "Texas", "Virginia", 
                   "Maryland", "New York", "New Jersey", "Illinois", "Delaware", 
                   "Washington, D.C.", "Connecticut"]
    test_types = ["pick3", "pick4", "pick5"]
    
    print("=" * 70)
    print("  BACKTEST COMPATIBILITY CHECK")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 70)
    
    for state in test_states:
        print(f"\n{'─' * 50}")
        print(f"📍 {state}")
        
        # All game names in this state
        all_games = coll.distinct('game_name', {'state_name': state})
        print(f"  All game_names: {sorted(all_games)}")
        
        for gt in test_types:
            games = get_games_for_prediction(coll, state, gt)
            if not games:
                continue
            
            print(f"\n  🎯 {gt} → matched games: {games}")
            
            # Check what records exist for Jan-Feb 2026
            start = datetime(2026, 1, 1)
            end = datetime(2026, 2, 26)
            
            query = {
                'state_name': state,
                'game_name': {'$in': games},
                'date': {'$gte': start, '$lte': end}
            }
            
            count = coll.count_documents(query)
            
            # Get a recent sample
            sample = list(coll.find(query).sort('date', -1).limit(3))
            
            print(f"    Records (Jan-Feb 2026): {count}")
            for s in sample:
                nums = s.get('numbers')
                if isinstance(nums, str):
                    try:
                        nums = json.loads(nums)
                    except:
                        pass
                print(f"      {s.get('date').strftime('%Y-%m-%d')} | {s.get('game_name')} | tod={s.get('tod','')} | numbers={nums} | source={s.get('source','?')}")
            
            # KEY CHECK: Are there old-format game names that are being EXCLUDED?
            old_format_games = [g for g in all_games if any(
                g.lower().startswith(base) and g.lower() != base
                for base in [gm.lower() for gm in games]
            )]
            if old_format_games:
                old_count = coll.count_documents({
                    'state_name': state,
                    'game_name': {'$in': old_format_games},
                    'date': {'$gte': start, '$lte': end}
                })
                if old_count > 0:
                    print(f"    ⚠️  OLD FORMAT games excluded: {old_format_games} ({old_count} records)")
    
    # Also check total record counts
    print(f"\n{'=' * 70}")
    print("📊 OVERALL COUNTS")
    print(f"{'=' * 70}")
    total = coll.count_documents({})
    jan_feb = coll.count_documents({'date': {'$gte': datetime(2026, 1, 1)}})
    feb = coll.count_documents({'date': {'$gte': datetime(2026, 2, 1)}})
    print(f"  Total records: {total:,}")
    print(f"  Jan-Feb 2026: {jan_feb:,}")
    print(f"  Feb 2026: {feb:,}")
    
    # Check numbers format
    print(f"\n📋 NUMBERS FORMAT CHECK (last 10 records):")
    recent = list(coll.find().sort('date', -1).limit(10))
    for r in recent:
        nums = r.get('numbers')
        print(f"  {r.get('state_name')} / {r.get('game_name')} / {type(nums).__name__}: {repr(nums)[:80]}")
    
    print(f"\n{'=' * 70}")
    print("  CHECK COMPLETE")
    print(f"{'=' * 70}")
    
    client.close()

if __name__ == "__main__":
    run()
