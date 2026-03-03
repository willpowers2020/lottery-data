#!/usr/bin/env python3
"""
Lottery Database DEEP Diagnostic v2 (Atlas-friendly)
=====================================================
Avoids heavy $group aggregations that exceed free-tier memory limits.
Uses sampling and targeted queries instead.

Usage:
    python diagnose_lottery_db_deep_v2.py
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import Counter

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def run_deep_diagnostics():
    client = MongoClient(MONGO_URL)

    print("=" * 70)
    print("  LOTTERY DATABASE DEEP DIAGNOSTIC v2 (Atlas-friendly)")
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
        {"state": 1, "game": 1, "date": 1, "tod": 1, "numbers": 1, "number_str": 1}
    ))
    print(f"  Records in last 7 days: {len(recent_docs)}")

    # Group manually
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
            print(f"    {key[0]} / {key[1]} / {key[2]} / tod={key[3]} → {seen[key]} copies")
    else:
        print("  ✅ No duplicates in last 7 days")

    # --- Game types ---
    print("\n🎰 Game types in lottery_v2:")
    game_types = coll1.distinct("game_type")
    for gt in sorted(game_types):
        # Use count with index hint for speed
        count = coll1.count_documents({"game_type": gt})
        print(f"    {gt}: {count:,} records")

    # --- States ---
    print("\n🗺️  States in lottery_v2:")
    states = coll1.distinct("state_name")
    print(f"    Total: {len(states)}")
    print(f"    List: {', '.join(sorted(states))}")

    # --- Most recent per game type ---
    print("\n📅 Most recent record per game_type:")
    for gt in sorted(game_types):
        newest = list(coll1.find({"game_type": gt}).sort("date", -1).limit(1))
        if newest:
            doc = newest[0]
            print(f"    {gt}: {doc['date'].strftime('%Y-%m-%d')} ({doc.get('state_name', '?')} / {doc.get('game_name', '?')})")

    # --- Null/missing fields ---
    print("\n🔎 Null/missing field check (lottery_v2):")
    for field in ["state", "state_name", "game", "game_name", "game_type", "date", "numbers", "number_str"]:
        null_count = coll1.count_documents(
            {"$or": [{field: None}, {field: {"$exists": False}}, {field: ""}]}
        )
        status = f"⚠️  {null_count:,} records" if null_count > 0 else "✅ OK"
        print(f"    {field}: {status}")

    # --- Source field ---
    print("\n📡 Sources in lottery_v2:")
    sources1 = coll1.distinct("source")
    for s in sources1:
        count = coll1.count_documents({"source": s})
        print(f"    '{s}': {count:,} records")

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

    # --- Top games ---
    print("\n🎰 Top 20 games in lotterypost (sampled from last 30 days):")
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
    print(f"    Total: {len(states2)}")

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

    # --- Null/missing fields ---
    print("\n🔎 Null/missing field check (lotterypost):")
    for field in ["country", "state_name", "game_name", "date", "numbers", "lp_game_id"]:
        null_count = coll2.count_documents(
            {"$or": [{field: None}, {field: {"$exists": False}}, {field: ""}]}
        )
        status = f"⚠️  {null_count:,} records" if null_count > 0 else "✅ OK"
        print(f"    {field}: {status}")

    # =============================================
    # 3. OVERLAP CHECK
    # =============================================
    print("\n" + "=" * 70)
    print("🔄 OVERLAP CHECK: lottery_v2 vs lotterypost")
    print("=" * 70)

    # Compare Feb 24, 2026
    test_date = datetime(2026, 2, 24)
    print(f"\n  Comparing records for {test_date.date()}:")

    v2_records = list(coll1.find({"date": test_date}, {"state_name": 1, "game_name": 1, "numbers": 1, "game_type": 1}))
    lp_records = list(coll2.find({"date": test_date}, {"state_name": 1, "game_name": 1, "numbers": 1}))

    print(f"\n  lottery_v2: {len(v2_records)} records")
    for r in v2_records[:8]:
        print(f"    {r.get('state_name')} / {r.get('game_name')} ({r.get('game_type')}) → {r.get('numbers')}")
    if len(v2_records) > 8:
        print(f"    ... and {len(v2_records) - 8} more")

    print(f"\n  lotterypost: {len(lp_records)} records")
    for r in lp_records[:8]:
        print(f"    {r.get('state_name')} / {r.get('game_name')} → {r.get('numbers')}")
    if len(lp_records) > 8:
        print(f"    ... and {len(lp_records) - 8} more")

    # =============================================
    # 4. SCHEMA COMPARISON
    # =============================================
    print("\n" + "=" * 70)
    print("📋 SCHEMA COMPARISON")
    print("=" * 70)

    sample1 = coll1.find_one()
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
    print("  DEEP DIAGNOSTIC v2 COMPLETE")
    print("=" * 70)
    print("\nCopy and paste this entire output and share it with Claude!")

    client.close()

if __name__ == "__main__":
    run_deep_diagnostics()
