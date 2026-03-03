#!/usr/bin/env python3
"""
Test ALL Pick 5 states against lottery_v2_test
"""

import json
from datetime import datetime, timedelta
from pymongo import MongoClient

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"


def parse_numbers(raw):
    if isinstance(raw, list): return [str(n) for n in raw]
    if isinstance(raw, str):
        try:
            p = json.loads(raw)
            if isinstance(p, list): return [str(n) for n in p]
        except: pass
    return []


def get_games_for_prediction(coll, state, game_type):
    """Exact copy of app.py logic"""
    all_games = coll.distinct('game_name', {'state_name': state})
    patterns = {
        'pick2': ['pick 2', 'pick2', 'pick-2', 'daily 2', 'daily2', 'play 2', 'play2', 'dc 2', 'dc2', 'cash 2', 'cash2', 'pega 2', 'quotidienne 2'],
        'pick3': ['pick 3', 'pick3', 'pick-3', 'daily 3', 'daily3', 'daily-3', 'dc-3', 'dc 3', 'dc3', 'cash 3', 'cash-3', 'cash3', 'play 3', 'play-3', 'play3', 'numbers', 'pega 3', 'quotidienne 3', 'my3'],
        'pick4': ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4', 'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4', 'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4', 'numbers game', 'lotto 4', 'pega 4', 'quotidienne 4'],
        'pick5': [
            'pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5',
            'dc 5', 'dc5', 'dc-5', 'play 5', 'play5',
            'georgia five', 'georgia 5', 'lotto poker', 'plus 5',
        ],
    }
    pats = patterns.get(game_type.lower(), [game_type.lower()])
    matched = [g for g in all_games if any(p in g.lower() for p in pats)]
    
    filtered = []
    for game in matched:
        gl = game.lower()
        is_parent = not any(t in gl for t in ['day', 'night', 'midday', 'evening', 'morning', '1:50pm', '7:50pm', '11:30pm'])
        if is_parent:
            has_child = any(g.lower().startswith(gl) and g.lower() != gl for g in matched)
            if has_child:
                continue
        filtered.append(game)
    return filtered if filtered else matched


def run():
    client = MongoClient(MONGO_URL)
    test_coll = client["lottery"]["lottery_v2_test"]
    lp_coll = client["mylottodata"]["lotterypost"]
    
    since = datetime.now() - timedelta(days=60)
    
    print("=" * 70)
    print("  PICK 5 FULL STATE TEST")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # Step 1: Find ALL states that have Pick 5 data in lotterypost (last 60 days)
    print("\n📥 Finding all states with Pick 5 data in lotterypost...")
    lp_docs = list(lp_coll.find({"date": {"$gte": since}}))
    
    pick5_states = set()
    pick5_by_state = {}
    
    for doc in lp_docs:
        nums = parse_numbers(doc.get("numbers"))
        if len(nums) == 5 and all(isinstance(n, str) and len(n) == 1 and n.isdigit() for n in nums):
            state = doc.get("state_name", "")
            game = doc.get("game_name", "")
            tod = doc.get("tod", "")
            pick5_states.add(state)
            if state not in pick5_by_state:
                pick5_by_state[state] = set()
            pick5_by_state[state].add((game, tod))
    
    print(f"  Found {len(pick5_states)} states with Pick 5 in lotterypost")
    
    # Step 2: Test each state against lottery_v2_test
    print(f"\n{'=' * 70}")
    print("🧪 TESTING EACH PICK 5 STATE")
    print(f"{'=' * 70}")
    
    pass_count = 0
    fail_count = 0
    warnings = 0
    
    for state in sorted(pick5_states):
        lp_games = pick5_by_state[state]
        lp_count = sum(1 for doc in lp_docs 
                       if doc.get("state_name") == state 
                       and len(parse_numbers(doc.get("numbers"))) == 5
                       and all(isinstance(n, str) and len(n) == 1 and n.isdigit() for n in parse_numbers(doc.get("numbers"))))
        
        # What does app.py find?
        games = get_games_for_prediction(test_coll, state, "pick5")
        
        if not games:
            print(f"  ❌ {state}")
            print(f"       lotterypost has: {sorted(lp_games)} ({lp_count} records)")
            print(f"       app.py found: NO GAMES")
            all_games = test_coll.distinct("game_name", {"state_name": state})
            print(f"       all game_names in test: {sorted(all_games)}")
            fail_count += 1
            continue
        
        test_count = test_coll.count_documents({
            "state_name": state, 
            "game_name": {"$in": games}
        })
        
        # Validate seeds
        draws = list(test_coll.find({
            "state_name": state,
            "game_name": {"$in": games},
        }).sort("date", -1).limit(10))
        
        valid = 0
        for d in draws:
            nums = d.get("numbers", "[]")
            if isinstance(nums, str):
                try: nums = json.loads(nums)
                except: continue
            if len(nums) == 5:
                valid += 1
        
        # Compare counts
        if test_count >= lp_count * 0.9:  # Allow small variance
            status = "✅"
            pass_count += 1
        elif test_count > 0:
            status = "⚠️ "
            warnings += 1
        else:
            status = "❌"
            fail_count += 1
        
        lp_game_names = sorted(set(g for g, t in lp_games))
        print(f"  {status} {state}")
        print(f"       lotterypost: {lp_game_names} ({lp_count} records)")
        print(f"       app.py sees: {games} ({test_count} records, {valid}/{min(10, test_count)} valid seeds)")
        
        if test_count < lp_count * 0.9 and test_count > 0:
            print(f"       ⚠️  Count mismatch: test has {test_count} vs lotterypost {lp_count}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print(f"📊 PICK 5 SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total Pick 5 states: {len(pick5_states)}")
    print(f"  ✅ Passed: {pass_count}")
    print(f"  ⚠️  Warnings: {warnings}")
    print(f"  ❌ Failed: {fail_count}")
    
    if fail_count == 0 and warnings == 0:
        print(f"\n  🎉 ALL PICK 5 STATES PASSED!")
    elif fail_count == 0:
        print(f"\n  ✅ No failures, but {warnings} warnings to review.")
    else:
        print(f"\n  ⚠️  {fail_count} states failed — review output above.")
    
    client.close()


if __name__ == "__main__":
    run()
