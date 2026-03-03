#!/usr/bin/env python3
"""
Lottery Database DEEP Diagnostic v3 (null-safe)
================================================
Handles None values and digs deeper into broken records.

Usage:
    python diagnose_lottery_db_deep_v3.py
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import Counter

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def safe_sort(items):
    """Sort a list that may contain None values."""
    return sorted(items, key=lambda x: (x is None, x or ""))

def run_deep_diagnostics():
    client = MongoClient(MONGO_URL)

    print("=" * 70)
    print("  LOTTERY DATABASE DEEP DIAGNOSTIC v3 (null-safe)")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 70)

    # =============================================
    # 1. LOTTERY_V2
    # =============================================
    db1 = client["lottery"]
    coll1 = db1["lottery_v2"]

    print("\n" + "=" * 70)
    print("📊 DATABASE: lottery / lottery_v2")
    print("=" * 70)

    # --- Spot-check duplicates on a recent date range ---
    print("\n🔍 Spot-checking duplicates (last 7 days)...")
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_docs = list(coll1.find(
        {"date": {"$gte": seven_days_ago}},
        {"state": 1, "state_name": 1, "game": 1, "game_name": 1, "game_type": 1,
         "date": 1, "tod": 1, "numbers": 1, "number_str": 1, "source": 1}
    ))
    print(f"  Records in last 7 days: {len(recent_docs)}")

    seen = Counter()
    dupe_examples = []
    for doc in recent_docs:
        key = (doc.get("state"), doc.get("game"), str(doc.get("date")), doc.get("tod", ""))
        seen[key] += 1
        if seen[key] == 2:
            dupe_examples.append(key)

    dupe_count = sum(1 for v in seen.values() if v > 1)
    if dupe_count > 0:
        print(f"  ⚠️  {dupe_count} duplicate draw groups found in last 7 days!")
        for key in dupe_examples[:10]:
            print(f"    state={key[0]} / game={key[1]} / {key[2]} / tod={key[3]} → {seen[key]} copies")
    else:
        print("  ✅ No duplicates in last 7 days")

    # --- CRITICAL: Examine the broken records ---
    print("\n" + "-" * 50)
    print("🚨 BROKEN RECORDS ANALYSIS (lottery_v2)")
    print("-" * 50)

    # How many records have null state?
    null_state_count = coll1.count_documents(
        {"$or": [{"state": None}, {"state": {"$exists": False}}]}
    )
    print(f"\n  Records with null/missing 'state': {null_state_count:,}")

    null_game_count = coll1.count_documents(
        {"$or": [{"game": None}, {"game": {"$exists": False}}]}
    )
    print(f"  Records with null/missing 'game': {null_game_count:,}")

    null_game_type_count = coll1.count_documents(
        {"$or": [{"game_type": None}, {"game_type": {"$exists": False}}]}
    )
    print(f"  Records with null/missing 'game_type': {null_game_type_count:,}")

    # Show sample broken records
    print("\n  📝 Sample BROKEN records (null state/game):")
    broken_samples = list(coll1.find(
        {"$or": [{"state": None}, {"state": {"$exists": False}}]}
    ).sort("date", -1).limit(5))
    for i, doc in enumerate(broken_samples):
        print(f"\n  --- Broken record #{i+1} ---")
        for key, value in doc.items():
            val_str = repr(value)
            if len(val_str) > 120:
                val_str = val_str[:120] + "..."
            print(f"    {key}: {val_str}")

    # Date range of broken records
    if null_state_count > 0:
        oldest_broken = list(coll1.find(
            {"$or": [{"state": None}, {"state": {"$exists": False}}]}
        ).sort("date", 1).limit(1))
        newest_broken = list(coll1.find(
            {"$or": [{"state": None}, {"state": {"$exists": False}}]}
        ).sort("date", -1).limit(1))
        if oldest_broken and newest_broken:
            print(f"\n  Broken records date range:")
            print(f"    Oldest: {oldest_broken[0].get('date')}")
            print(f"    Newest: {newest_broken[0].get('date')}")

    # Show sample GOOD records for comparison
    print("\n  📝 Sample GOOD records (for comparison):")
    good_samples = list(coll1.find(
        {"state": {"$exists": True, "$ne": None}, "game": {"$exists": True, "$ne": None}}
    ).sort("date", -1).limit(3))
    for i, doc in enumerate(good_samples):
        print(f"\n  --- Good record #{i+1} ---")
        for key, value in doc.items():
            val_str = repr(value)
            if len(val_str) > 120:
                val_str = val_str[:120] + "..."
            print(f"    {key}: {val_str}")

    # --- Source breakdown ---
    print("\n📡 Sources in lottery_v2:")
    sources1 = coll1.distinct("source")
    for s in safe_sort(sources1):
        count = coll1.count_documents({"source": s})
        # Also check how many of those have null state
        null_in_source = coll1.count_documents(
            {"source": s, "$or": [{"state": None}, {"state": {"$exists": False}}]}
        )
        broken_pct = f" ({null_in_source:,} broken)" if null_in_source > 0 else ""
        print(f"    '{s}': {count:,} records{broken_pct}")

    # Also check records with no source
    no_source = coll1.count_documents(
        {"$or": [{"source": None}, {"source": {"$exists": False}}]}
    )
    if no_source > 0:
        print(f"    [no source field]: {no_source:,} records")

    # --- Game types (null-safe) ---
    print("\n🎰 Game types in lottery_v2:")
    game_types = coll1.distinct("game_type")
    for gt in safe_sort(game_types):
        count = coll1.count_documents({"game_type": gt})
        label = gt if gt is not None else "[NULL]"
        print(f"    {label}: {count:,} records")

    # --- States (null-safe) ---
    print("\n🗺️  States in lottery_v2:")
    states = coll1.distinct("state_name")
    non_null_states = [s for s in states if s is not None]
    null_states = len(states) - len(non_null_states)
    print(f"    Total: {len(non_null_states)} states" + (f" + {null_states} NULL" if null_states else ""))
    print(f"    List: {', '.join(sorted(non_null_states))}")

    # --- Most recent per game type (null-safe) ---
    print("\n📅 Most recent record per game_type:")
    for gt in safe_sort(game_types):
        label = gt if gt is not None else "[NULL]"
        query = {"game_type": gt} if gt is not None else {"$or": [{"game_type": None}, {"game_type": {"$exists": False}}]}
        newest = list(coll1.find(query).sort("date", -1).limit(1))
        if newest:
            doc = newest[0]
            print(f"    {label}: {doc['date'].strftime('%Y-%m-%d')} ({doc.get('state_name', '?')} / {doc.get('game_name', '?')})")

    # =============================================
    # 2. MYLOTTODATA / LOTTERYPOST
    # =============================================
    db2 = client["mylottodata"]
    coll2 = db2["lotterypost"]

    print("\n" + "=" * 70)
    print("📊 DATABASE: mylottodata / lotterypost")
    print("=" * 70)

    # --- Spot-check duplicates ---
    print("\n🔍 Spot-checking duplicates (last 7 days)...")
    recent_docs2 = list(coll2.find(
        {"date": {"$gte": seven_days_ago}},
        {"state_name": 1, "game_name": 1, "date": 1, "tod": 1, "numbers": 1}
    ))
    print(f"  Records in last 7 days: {len(recent_docs2)}")

    seen2 = Counter()
    dupe_examples2 = []
    for doc in recent_docs2:
        key = (doc.get("state_name"), doc.get("game_name"), str(doc.get("date")), doc.get("tod", ""))
        seen2[key] += 1
        if seen2[key] == 2:
            dupe_examples2.append(key)

    dupe_count2 = sum(1 for v in seen2.values() if v > 1)
    if dupe_count2 > 0:
        print(f"  ⚠️  {dupe_count2} duplicate draw groups found in last 7 days!")
        for key in dupe_examples2[:10]:
            print(f"    {key[0]} / {key[1]} / {key[2]} / tod={key[3]} → {seen2[key]} copies")
    else:
        print("  ✅ No duplicates in last 7 days")

    # --- Null check ---
    print("\n🔎 Null/missing field check (lotterypost):")
    for field in ["country", "state_name", "game_name", "date", "numbers", "lp_game_id", "tod"]:
        null_count = coll2.count_documents(
            {"$or": [{field: None}, {field: {"$exists": False}}, {field: ""}]}
        )
        status = f"⚠️  {null_count:,} records" if null_count > 0 else "✅ OK"
        print(f"    {field}: {status}")

    # --- Top games (last 30 days) ---
    print("\n🎰 Top 20 games in lotterypost (last 30 days):")
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_30 = list(coll2.find(
        {"date": {"$gte": thirty_days_ago}},
        {"game_name": 1}
    ))
    game_counts = Counter(doc.get("game_name") for doc in recent_30)
    for game, count in game_counts.most_common(20):
        print(f"    {game}: {count:,}")

    # --- States ---
    print("\n🗺️  States in lotterypost:")
    states2 = coll2.distinct("state_name")
    non_null_states2 = [s for s in states2 if s]
    print(f"    Total: {len(non_null_states2)}")

    # --- Most recent for major games ---
    print("\n📅 Most recent records for major games:")
    major_games = ["Powerball", "Mega Millions", "Pick 3", "Pick 4", "Cash 5", "Cash4Life"]
    for game in major_games:
        newest = list(coll2.find({"game_name": {"$regex": f"^{game}$", "$options": "i"}}).sort("date", -1).limit(1))
        if newest:
            doc = newest[0]
            print(f"    {doc['game_name']} ({doc.get('state_name', '?')}): {doc['date'].strftime('%Y-%m-%d')}")
        else:
            print(f"    {game}: NOT FOUND")

    # =============================================
    # 3. OVERLAP CHECK
    # =============================================
    print("\n" + "=" * 70)
    print("🔄 OVERLAP CHECK: lottery_v2 vs lotterypost (Feb 24, 2026)")
    print("=" * 70)

    test_date = datetime(2026, 2, 24)

    v2_records = list(coll1.find(
        {"date": test_date},
        {"state_name": 1, "game_name": 1, "game_type": 1, "numbers": 1, "source": 1}
    ))
    lp_records = list(coll2.find(
        {"date": test_date},
        {"state_name": 1, "game_name": 1, "numbers": 1}
    ))

    print(f"\n  lottery_v2: {len(v2_records)} records")
    for r in v2_records[:10]:
        print(f"    {r.get('state_name')} / {r.get('game_name')} ({r.get('game_type')}) → {r.get('numbers')} [source: {r.get('source')}]")
    if len(v2_records) > 10:
        print(f"    ... and {len(v2_records) - 10} more")

    print(f"\n  lotterypost: {len(lp_records)} records")
    for r in lp_records[:10]:
        print(f"    {r.get('state_name')} / {r.get('game_name')} → {r.get('numbers')}")
    if len(lp_records) > 10:
        print(f"    ... and {len(lp_records) - 10} more")

    # =============================================
    # 4. SCHEMA COMPARISON
    # =============================================
    print("\n" + "=" * 70)
    print("📋 SCHEMA COMPARISON")
    print("=" * 70)

    sample1 = coll1.find_one({"state": {"$exists": True, "$ne": None}})
    sample2 = coll2.find_one()

    fields1 = set(sample1.keys()) if sample1 else set()
    fields2 = set(sample2.keys()) if sample2 else set()

    print(f"\n  lottery_v2 fields ({len(fields1)}):")
    print(f"    {', '.join(sorted(fields1))}")
    print(f"\n  lotterypost fields ({len(fields2)}):")
    print(f"    {', '.join(sorted(fields2))}")
    print(f"\n  Common fields: {', '.join(sorted(fields1 & fields2))}")
    print(f"  Only in lottery_v2: {', '.join(sorted(fields1 - fields2))}")
    print(f"  Only in lotterypost: {', '.join(sorted(fields2 - fields1))}")

    print("\n" + "=" * 70)
    print("  DEEP DIAGNOSTIC v3 COMPLETE")
    print("=" * 70)
    print("\nCopy and paste this entire output and share it with Claude!")

    client.close()

if __name__ == "__main__":
    run_deep_diagnostics()
