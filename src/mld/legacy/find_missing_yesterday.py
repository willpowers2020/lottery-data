#!/usr/bin/env python3
"""
Find Missing Data for Yesterday (Feb 25, 2026)
================================================
Compares lottery_v2 (enriched) vs lotterypost (raw) to find gaps.
Also checks what lotterypost has for Pick 2-5 games yesterday.

Usage:
    python find_missing_yesterday.py
"""

from pymongo import MongoClient
from datetime import datetime
from collections import defaultdict

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def run():
    client = MongoClient(MONGO_URL)
    
    db_v2 = client["lottery"]["lottery_v2"]
    db_lp = client["mylottodata"]["lotterypost"]
    
    yesterday = datetime(2026, 2, 25)
    today = datetime(2026, 2, 26)
    
    print("=" * 70)
    print(f"  MISSING DATA REPORT — {yesterday.date()}")
    print("=" * 70)
    
    # ── 1. What does lottery_v2 have for yesterday? ──
    print("\n📊 lottery_v2 records for Feb 25:")
    v2_docs = list(db_v2.find({"date": yesterday}).sort([("state_name", 1), ("game_name", 1)]))
    print(f"  Total records: {len(v2_docs)}")
    
    v2_good = [d for d in v2_docs if d.get("state") is not None]
    v2_broken = [d for d in v2_docs if d.get("state") is None]
    print(f"  Good records: {len(v2_good)}")
    print(f"  Broken records (null state): {len(v2_broken)}")
    
    # Group by state
    v2_by_state = defaultdict(list)
    for doc in v2_good:
        v2_by_state[doc.get("state_name")].append(doc.get("game_name"))
    
    print(f"\n  States with data in lottery_v2: {len(v2_by_state)}")
    for state in sorted(v2_by_state.keys()):
        games = sorted(set(v2_by_state[state]))
        print(f"    {state}: {', '.join(games)}")
    
    if v2_broken:
        print(f"\n  Broken records detail:")
        for doc in v2_broken:
            print(f"    {doc.get('state_name', '?')} / {doc.get('game_name', '?')} / tod={doc.get('tod', '?')}")
    
    # ── 2. What does lotterypost have for yesterday (Pick 2-5 only)? ──
    print("\n" + "=" * 70)
    print("📊 lotterypost Pick 2-5 records for Feb 25:")
    print("=" * 70)
    
    # Find all pick 2-5 style games
    # These have various names: Pick 3, Cash 3, Daily 3, Numbers, Win 4, etc.
    # Best approach: find games where numbers array has 2-5 single-digit elements
    
    lp_docs = list(db_lp.find({"date": yesterday}).sort([("state_name", 1), ("game_name", 1)]))
    print(f"  Total lotterypost records for yesterday: {len(lp_docs)}")
    
    # Filter to Pick 2-5 games (numbers arrays with 2-5 single digits)
    pick_games = []
    non_pick_games = []
    
    for doc in lp_docs:
        numbers_raw = doc.get("numbers", "[]")
        try:
            if isinstance(numbers_raw, str):
                import json
                numbers = json.loads(numbers_raw)
            else:
                numbers = numbers_raw
            
            # Pick games have 2-5 numbers, each is a single digit (0-9)
            if len(numbers) in [2, 3, 4, 5] and all(
                isinstance(n, str) and len(n) == 1 and n.isdigit() for n in numbers
            ):
                doc["_pick_type"] = f"pick{len(numbers)}"
                pick_games.append(doc)
            else:
                non_pick_games.append(doc)
        except:
            non_pick_games.append(doc)
    
    print(f"  Pick 2-5 games: {len(pick_games)}")
    print(f"  Other games (Powerball, Mega Millions, etc.): {len(non_pick_games)}")
    
    # Group lotterypost pick games by state
    lp_by_state = defaultdict(list)
    for doc in pick_games:
        key = (doc.get("state_name"), doc.get("game_name"), doc.get("tod", ""))
        lp_by_state[doc.get("state_name")].append({
            "game_name": doc.get("game_name"),
            "tod": doc.get("tod", ""),
            "numbers": doc.get("numbers"),
            "pick_type": doc.get("_pick_type"),
        })
    
    print(f"\n  States with Pick 2-5 data in lotterypost: {len(lp_by_state)}")
    
    # ── 3. Find what's MISSING from lottery_v2 ──
    print("\n" + "=" * 70)
    print("🔍 MISSING FROM lottery_v2 (in lotterypost but NOT in lottery_v2):")
    print("=" * 70)
    
    # Build set of what lottery_v2 has
    v2_keys = set()
    for doc in v2_good:
        key = (doc.get("state_name"), doc.get("game_name"), doc.get("tod", ""))
        v2_keys.add(key)
    
    # Also include broken records (they exist, just incomplete)
    v2_broken_keys = set()
    for doc in v2_broken:
        key = (doc.get("state_name"), doc.get("game_name"), doc.get("tod", ""))
        v2_broken_keys.add(key)
    
    missing = []
    present_but_broken = []
    
    for doc in pick_games:
        key = (doc.get("state_name"), doc.get("game_name"), doc.get("tod", ""))
        if key not in v2_keys:
            if key in v2_broken_keys:
                present_but_broken.append(doc)
            else:
                missing.append(doc)
    
    # Group missing by state
    missing_by_state = defaultdict(list)
    for doc in missing:
        missing_by_state[doc.get("state_name")].append(doc)
    
    print(f"\n  Completely missing records: {len(missing)}")
    print(f"  Present but broken (null state): {len(present_but_broken)}")
    
    if missing:
        print(f"\n  Missing by state ({len(missing_by_state)} states):")
        for state in sorted(missing_by_state.keys()):
            docs = missing_by_state[state]
            games = [f"{d.get('game_name')} ({d.get('_pick_type')})" for d in docs]
            print(f"    {state}: {', '.join(sorted(set(games)))}")
    
    if present_but_broken:
        print(f"\n  Present but broken (need re-import with full fields):")
        for doc in present_but_broken:
            print(f"    {doc.get('state_name')} / {doc.get('game_name')} / tod={doc.get('tod', '')}")
    
    # ── 4. Summary stats ──
    print("\n" + "=" * 70)
    print("📈 SUMMARY")
    print("=" * 70)
    
    # Count by pick type
    lp_by_type = defaultdict(int)
    v2_by_type = defaultdict(int)
    missing_by_type = defaultdict(int)
    
    for doc in pick_games:
        lp_by_type[doc["_pick_type"]] += 1
    for doc in v2_good:
        gt = doc.get("game_type", "?")
        v2_by_type[gt] += 1
    for doc in missing:
        missing_by_type[doc["_pick_type"]] += 1
    
    print(f"\n  {'Game Type':<12} {'lotterypost':<15} {'lottery_v2':<15} {'Missing':<15}")
    print(f"  {'-'*12} {'-'*15} {'-'*15} {'-'*15}")
    for gt in ["pick2", "pick3", "pick4", "pick5"]:
        lp_count = lp_by_type.get(gt, 0)
        v2_count = v2_by_type.get(gt, 0)
        miss_count = missing_by_type.get(gt, 0)
        print(f"  {gt:<12} {lp_count:<15} {v2_count:<15} {miss_count:<15}")
    
    total_lp = sum(lp_by_type.values())
    total_v2 = sum(v2_by_type.values())
    total_miss = sum(missing_by_type.values())
    print(f"  {'TOTAL':<12} {total_lp:<15} {total_v2:<15} {total_miss:<15}")
    
    coverage = (total_v2 / total_lp * 100) if total_lp > 0 else 0
    print(f"\n  lottery_v2 coverage of lotterypost Pick 2-5: {coverage:.1f}%")
    
    # ── 5. Also check today (Feb 26) ──
    print("\n" + "=" * 70)
    print(f"📊 BONUS: What's available for TODAY ({today.date()}):")
    print("=" * 70)
    
    v2_today = db_v2.count_documents({"date": today})
    lp_today = db_lp.count_documents({"date": today})
    print(f"  lottery_v2: {v2_today} records")
    print(f"  lotterypost: {lp_today} records")
    
    print("\n" + "=" * 70)
    print("  REPORT COMPLETE")
    print("=" * 70)
    print("\nCopy and paste this entire output and share it with Claude!")
    
    client.close()

if __name__ == "__main__":
    run()
