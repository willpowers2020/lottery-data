#!/usr/bin/env python3
"""
Post-Sync Gap Check — What's STILL missing from Feb 25?
"""

from pymongo import MongoClient
from datetime import datetime
from collections import defaultdict
import json

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def run():
    client = MongoClient(MONGO_URL)
    
    db_v2 = client["lottery"]["lottery_v2"]
    db_lp = client["mylottodata"]["lotterypost"]
    
    yesterday = datetime(2026, 2, 25)
    
    print("=" * 70)
    print(f"  POST-SYNC GAP CHECK — {yesterday.date()}")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # ── What does lottery_v2 have now? ──
    v2_docs = list(db_v2.find({"date": yesterday}))
    print(f"\n📊 lottery_v2 now has {len(v2_docs)} records for Feb 25")
    
    v2_keys = set()
    v2_by_state = defaultdict(list)
    for doc in v2_docs:
        key = (doc.get("state_name", ""), doc.get("game_name", ""), doc.get("tod", ""))
        v2_keys.add(key)
        v2_by_state[doc.get("state_name", "")].append(doc.get("game_name", ""))
    
    print(f"   States covered: {len(v2_by_state)}")
    for state in sorted(v2_by_state.keys()):
        games = sorted(set(v2_by_state[state]))
        print(f"     {state}: {', '.join(games)}")
    
    # ── What does lotterypost have? ──
    lp_docs = list(db_lp.find({"date": yesterday}))
    print(f"\n📊 lotterypost has {len(lp_docs)} total records for Feb 25")
    
    # Filter to Pick 2-5
    pick_games = []
    for doc in lp_docs:
        numbers_raw = doc.get("numbers", "[]")
        try:
            numbers = json.loads(numbers_raw) if isinstance(numbers_raw, str) else numbers_raw
            if isinstance(numbers, list) and len(numbers) in [2,3,4,5] and all(
                isinstance(n, str) and len(n) == 1 and n.isdigit() for n in numbers
            ):
                doc["_pick_type"] = f"pick{len(numbers)}"
                pick_games.append(doc)
        except:
            pass
    
    print(f"   Pick 2-5 records: {len(pick_games)}")
    
    # ── What's still missing? ──
    lp_keys = set()
    still_missing = []
    for doc in pick_games:
        key = (doc.get("state_name", ""), doc.get("game_name", ""), doc.get("tod", ""))
        lp_keys.add(key)
        if key not in v2_keys:
            still_missing.append(doc)
    
    # Also check: what's in v2 but NOT matching lotterypost keys? (possible tod mismatch)
    v2_not_in_lp = []
    for key in v2_keys:
        if key not in lp_keys:
            v2_not_in_lp.append(key)
    
    print(f"\n{'=' * 70}")
    print(f"🔍 STILL MISSING from lottery_v2: {len(still_missing)}")
    print(f"   In lottery_v2 but not matching lotterypost keys: {len(v2_not_in_lp)}")
    print(f"{'=' * 70}")
    
    if still_missing:
        missing_by_state = defaultdict(list)
        for doc in still_missing:
            missing_by_state[doc.get("state_name")].append({
                "game": doc.get("game_name"),
                "tod_lp": doc.get("tod", ""),
                "pick": doc.get("_pick_type"),
                "numbers": doc.get("numbers"),
            })
        
        print(f"\n  Missing by state ({len(missing_by_state)} states):")
        for state in sorted(missing_by_state.keys()):
            entries = missing_by_state[state]
            for e in sorted(entries, key=lambda x: x["game"]):
                print(f"    {state} / {e['game']} / lp_tod=\"{e['tod_lp']}\" ({e['pick']})")
    else:
        print("\n  ✅ Nothing missing! Full coverage!")
    
    if v2_not_in_lp:
        print(f"\n  In lottery_v2 but no lotterypost match (possible tod mismatch):")
        for key in sorted(v2_not_in_lp):
            print(f"    {key[0]} / {key[1]} / v2_tod=\"{key[2]}\"")
    
    # ── TOD analysis: show how tod values compare ──
    print(f"\n{'=' * 70}")
    print("🔎 TOD (Time of Day) MISMATCH ANALYSIS")
    print(f"{'=' * 70}")
    
    # For records that exist in BOTH, compare tod values
    lp_by_key_loose = defaultdict(list)  # keyed by (state, game, date) without tod
    for doc in pick_games:
        loose_key = (doc.get("state_name", ""), doc.get("game_name", ""))
        lp_by_key_loose[loose_key].append(doc.get("tod", ""))
    
    v2_by_key_loose = defaultdict(list)
    for doc in v2_docs:
        loose_key = (doc.get("state_name", ""), doc.get("game_name", ""))
        v2_by_key_loose[loose_key].append(doc.get("tod", ""))
    
    # Find games where both have data but tod differs
    tod_mismatches = []
    all_loose_keys = set(list(lp_by_key_loose.keys()) + list(v2_by_key_loose.keys()))
    for key in sorted(all_loose_keys):
        lp_tods = set(lp_by_key_loose.get(key, []))
        v2_tods = set(v2_by_key_loose.get(key, []))
        if lp_tods and v2_tods and lp_tods != v2_tods:
            tod_mismatches.append((key, lp_tods, v2_tods))
    
    if tod_mismatches:
        print(f"\n  Found {len(tod_mismatches)} games with TOD mismatches:")
        for key, lp_tods, v2_tods in tod_mismatches[:20]:
            print(f"    {key[0]} / {key[1]}")
            print(f"      lotterypost tod: {lp_tods}")
            print(f"      lottery_v2  tod: {v2_tods}")
    else:
        print("\n  ✅ No TOD mismatches found")
    
    print(f"\n{'=' * 70}")
    print("  GAP CHECK COMPLETE")
    print(f"{'=' * 70}")
    
    client.close()

if __name__ == "__main__":
    run()
