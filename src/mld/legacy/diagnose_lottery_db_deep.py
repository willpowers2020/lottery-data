#!/usr/bin/env python3
"""
Lottery Database DEEP Diagnostic - Part 2
==========================================
Run this after the initial diagnostic to find specific data integrity issues.

Usage:
    python diagnose_lottery_db_deep.py
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
import json

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def run_deep_diagnostics():
    client = MongoClient(MONGO_URL)

    print("=" * 70)
    print("  LOTTERY DATABASE DEEP DIAGNOSTIC")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 70)

    # =============================================
    # 1. LOTTERY_V2 - Check for true duplicate draws
    # =============================================
    db1 = client["lottery"]
    coll1 = db1["lottery_v2"]

    print("\n" + "=" * 70)
    print("📊 DATABASE: lottery / lottery_v2")
    print("=" * 70)

    # Check for duplicate draw entries (same game + state + date + time of day)
    print("\n🔍 Checking for TRUE duplicate draws (same state + game + date + tod)...")
    pipeline = [
        {"$group": {
            "_id": {
                "state": "$state",
                "game": "$game",
                "date": "$date",
                "tod": "$tod"
            },
            "count": {"$sum": 1},
            "ids": {"$push": "$_id"}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    dupes = list(coll1.aggregate(pipeline, allowDiskUse=True))
    if dupes:
        total_dupe_groups = len(list(coll1.aggregate([
            {"$group": {
                "_id": {"state": "$state", "game": "$game", "date": "$date", "tod": "$tod"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "total"}
        ], allowDiskUse=True)))
        print(f"  ⚠️  Found duplicate draw groups!")
        print(f"  Total duplicate groups: {total_dupe_groups}")
        print(f"  Top 10 worst duplicates:")
        for d in dupes[:10]:
            print(f"    {d['_id']['state']} / {d['_id']['game']} / {d['_id']['date']} / tod={d['_id'].get('tod','')} → {d['count']} copies")
    else:
        print("  ✅ No true duplicate draws found")

    # List all unique game types
    print("\n🎰 Game types in lottery_v2:")
    game_types = coll1.distinct("game_type")
    for gt in sorted(game_types):
        count = coll1.count_documents({"game_type": gt})
        print(f"    {gt}: {count:,} records")

    # List all unique states
    print("\n🗺️  States in lottery_v2:")
    states = coll1.distinct("state_name")
    print(f"    Total states: {len(states)}")
    print(f"    States: {', '.join(sorted(states)[:20])}{'...' if len(states) > 20 else ''}")

    # Check recency by game type
    print("\n📅 Most recent record per game_type:")
    for gt in sorted(game_types):
        newest = coll1.find({"game_type": gt}).sort("date", -1).limit(1)
        for doc in newest:
            print(f"    {gt}: {doc['date']} ({doc.get('state_name', '?')} / {doc.get('game_name', '?')})")

    # Check for null/missing critical fields
    print("\n🔎 Null/missing field check (lottery_v2):")
    for field in ["state", "state_name", "game", "game_name", "game_type", "date", "numbers", "number_str"]:
        null_count = coll1.count_documents({"$or": [{field: None}, {field: {"$exists": False}}, {field: ""}]})
        if null_count > 0:
            print(f"    ⚠️  {field}: {null_count:,} records with null/missing/empty values")
        else:
            print(f"    ✅ {field}: OK")

    # =============================================
    # 2. MYLOTTODATA / LOTTERYPOST
    # =============================================
    db2 = client["mylottodata"]
    coll2 = db2["lotterypost"]

    print("\n" + "=" * 70)
    print("📊 DATABASE: mylottodata / lotterypost")
    print("=" * 70)

    # Check for true duplicate draws
    print("\n🔍 Checking for TRUE duplicate draws (same state + game + date + tod)...")
    pipeline2 = [
        {"$group": {
            "_id": {
                "state_name": "$state_name",
                "game_name": "$game_name",
                "date": "$date",
                "tod": "$tod"
            },
            "count": {"$sum": 1},
            "ids": {"$push": "$_id"}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    dupes2 = list(coll2.aggregate(pipeline2, allowDiskUse=True))
    if dupes2:
        total_dupe_groups2_result = list(coll2.aggregate([
            {"$group": {
                "_id": {"state_name": "$state_name", "game_name": "$game_name", "date": "$date", "tod": "$tod"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "total"}
        ], allowDiskUse=True))
        total_dupe_groups2 = total_dupe_groups2_result[0]["total"] if total_dupe_groups2_result else 0
        print(f"  ⚠️  Found duplicate draw groups!")
        print(f"  Total duplicate groups: {total_dupe_groups2}")
        print(f"  Top 10 worst duplicates:")
        for d in dupes2[:10]:
            print(f"    {d['_id']['state_name']} / {d['_id']['game_name']} / {d['_id']['date']} / tod={d['_id'].get('tod','')} → {d['count']} copies")
    else:
        print("  ✅ No true duplicate draws found")

    # Unique games
    print("\n🎰 Top 20 games by record count in lotterypost:")
    pipeline_games = [
        {"$group": {"_id": "$game_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20}
    ]
    for g in coll2.aggregate(pipeline_games):
        print(f"    {g['_id']}: {g['count']:,}")

    # Unique states
    print("\n🗺️  States in lotterypost:")
    states2 = coll2.distinct("state_name")
    print(f"    Total states: {len(states2)}")

    # Check recency for major games
    print("\n📅 Most recent records for major games:")
    major_games = ["Powerball", "Mega Millions", "Pick 3", "Pick 4", "Cash 5"]
    for game in major_games:
        newest = coll2.find({"game_name": {"$regex": game, "$options": "i"}}).sort("date", -1).limit(1)
        for doc in newest:
            print(f"    {doc['game_name']} ({doc.get('state_name', '?')}): {doc['date']}")

    # Check for null/missing critical fields
    print("\n🔎 Null/missing field check (lotterypost):")
    for field in ["country", "state_name", "game_name", "date", "numbers", "lp_game_id"]:
        null_count = coll2.count_documents({"$or": [{field: None}, {field: {"$exists": False}}, {field: ""}]})
        if null_count > 0:
            print(f"    ⚠️  {field}: {null_count:,} records with null/missing/empty values")
        else:
            print(f"    ✅ {field}: OK")

    # =============================================
    # 3. OVERLAP CHECK between the two databases
    # =============================================
    print("\n" + "=" * 70)
    print("🔄 OVERLAP CHECK: lottery_v2 vs lotterypost")
    print("=" * 70)

    # Compare a specific recent date to see if both have the same data
    recent_date = datetime(2026, 2, 24)
    print(f"\n  Comparing records for {recent_date.date()}:")
    
    v2_records = list(coll1.find({"date": recent_date}, {"state_name": 1, "game_name": 1, "numbers": 1}).limit(20))
    lp_records = list(coll2.find({"date": recent_date}, {"state_name": 1, "game_name": 1, "numbers": 1}).limit(20))
    
    print(f"    lottery_v2: {len(v2_records)} records (showing up to 20)")
    for r in v2_records[:5]:
        print(f"      {r.get('state_name')} / {r.get('game_name')} → {r.get('numbers')}")
    
    print(f"    lotterypost: {len(lp_records)} records (showing up to 20)")
    for r in lp_records[:5]:
        print(f"      {r.get('state_name')} / {r.get('game_name')} → {r.get('numbers')}")

    # =============================================
    # 4. SOURCE FIELD ANALYSIS
    # =============================================
    print("\n" + "=" * 70)
    print("📡 SOURCE ANALYSIS")
    print("=" * 70)
    
    print("\n  lottery_v2 - distinct 'source' values:")
    sources1 = coll1.distinct("source")
    for s in sources1:
        count = coll1.count_documents({"source": s})
        print(f"    '{s}': {count:,} records")

    print("\n" + "=" * 70)
    print("  DEEP DIAGNOSTIC COMPLETE")
    print("=" * 70)
    print("\nCopy and paste this entire output and share it with Claude!")

    client.close()

if __name__ == "__main__":
    run_deep_diagnostics()
