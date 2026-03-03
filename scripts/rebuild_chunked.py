#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  REBUILD lottery_v2 in chunks (Atlas-safe)
═══════════════════════════════════════════════════════════════════

Processes lotterypost in 1-year chunks to avoid cursor timeouts.

Usage:
  python rebuild_chunked.py --restore     # Restore from backup FIRST
  python rebuild_chunked.py --dry-run     # Preview rebuild
  python rebuild_chunked.py               # Full rebuild
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from itertools import combinations
from collections import Counter
from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"
DB_LOTTERY = "lottery"
DB_SOURCE = "mylottodata"

STATE_SLUGS = {
    "Alabama": "al", "Alaska": "ak", "Arizona": "az", "Arkansas": "ar",
    "California": "ca", "Colorado": "co", "Connecticut": "ct", "Delaware": "de",
    "Florida": "fl", "Georgia": "ga", "Hawaii": "hi", "Idaho": "id",
    "Illinois": "il", "Indiana": "in", "Iowa": "ia", "Kansas": "ks",
    "Kentucky": "ky", "Louisiana": "la", "Maine": "me", "Maryland": "md",
    "Massachusetts": "ma", "Michigan": "mi", "Minnesota": "mn", "Mississippi": "ms",
    "Missouri": "mo", "Montana": "mt", "Nebraska": "ne", "Nevada": "nv",
    "New Hampshire": "nh", "New Jersey": "nj", "New Mexico": "nm", "New York": "ny",
    "North Carolina": "nc", "North Dakota": "nd", "Ohio": "oh", "Oklahoma": "ok",
    "Oregon": "or", "Pennsylvania": "pa", "Puerto Rico": "pr", "Rhode Island": "ri",
    "South Carolina": "sc", "South Dakota": "sd", "Tennessee": "tn", "Texas": "tx",
    "Utah": "ut", "Vermont": "vt", "Virginia": "va", "Washington": "wa",
    "Washington DC": "dc", "Washington, D.C.": "dc",
    "West Virginia": "wv", "Wisconsin": "wi", "Wyoming": "wy",
    "Atlantic Canada": "atlantic-canada", "British Columbia": "bc",
    "Ontario": "on", "Québec": "qc", "Western Canada": "western-canada",
    "Germany": "de-eu", "Ireland": "ie", "Multi-State": "multi",
}


def parse_numbers(raw):
    if isinstance(raw, list):
        return [str(n) for n in raw]
    if isinstance(raw, str):
        try:
            p = json.loads(raw)
            if isinstance(p, list):
                return [str(n) for n in p]
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def is_pick_game(nums):
    if not nums or len(nums) not in [2, 3, 4, 5]:
        return False
    return all(isinstance(n, str) and len(n) == 1 and n.isdigit() for n in nums)


def game_name_has_tod(name):
    lower = name.lower()
    indicators = ["midday", "mid-day", "evening", "night", "morning",
                  "1:50pm", "7:50pm", "11:30pm", "afternoon", "matinee",
                  "early bird", "drive time", "prime time", "night owl",
                  "rush hour", "coffee break", "after hours", "late night"]
    for ind in indicators:
        if ind == " day":
            if lower.endswith(" day") or lower.endswith("-day"):
                return True
        elif ind in lower:
            return True
    if lower.endswith(" day") or lower.endswith("-day"):
        return True
    return False


def compute_tod(game_name, lp_tod):
    if lp_tod and lp_tod.strip():
        return lp_tod.strip()
    lower = game_name.lower()
    if "midday" in lower or "mid-day" in lower: return "Midday"
    if "evening" in lower: return "Evening"
    if "night" in lower: return "Night"
    if lower.endswith(" day") or lower.endswith("-day"): return "Day"
    if "morning" in lower: return "Morning"
    if "1:50pm" in lower: return "Midday"
    if "7:50pm" in lower: return "Evening"
    if "11:30pm" in lower: return "Night"
    return ""


def enrich(doc):
    numbers = parse_numbers(doc.get("numbers"))
    if not is_pick_game(numbers):
        return None
    state_name = doc.get("state", doc.get("state_name", ""))
    base_game = doc.get("game", doc.get("game_name", ""))
    lp_tod = doc.get("tod", "").strip()
    date = doc.get("date")
    if not date or not state_name or not base_game:
        return None
    num_digits = len(numbers)
    digits = [int(n) for n in numbers]
    digits_sorted = sorted(digits)
    tod = compute_tod(base_game, lp_tod)
    final_game_name = f"{base_game} {tod}" if (tod and not game_name_has_tod(base_game)) else base_game
    return {
        "country": "United States" if doc.get("country") in ("USA", "United States", None) else doc.get("country", "United States"),
        "state": STATE_SLUGS.get(state_name, state_name.lower().replace(" ", "-")),
        "state_name": state_name,
        "game": final_game_name.lower().replace(" ", "-").replace(".", "").replace(",", ""),
        "game_name": final_game_name,
        "game_type": f"pick{num_digits}",
        "date": date,
        "numbers": json.dumps(numbers),
        "number_str": "".join(numbers),
        "normalized": "".join(str(d) for d in digits_sorted),
        "digits_sum": sum(digits),
        "pairs_2dp": sorted(set("".join(str(d) for d in sorted(c)) for c in combinations(digits, 2))),
        "triples_3dp": sorted(set("".join(str(d) for d in sorted(c)) for c in combinations(digits, 3))) if num_digits >= 4 else [],
        "tod": tod,
        "num_digits": num_digits,
        "source": "lotterypost",
    }


def cmd_restore():
    """Restore lottery_v2 from most recent backup."""
    client = MongoClient(MONGO_URL)
    db = client[DB_LOTTERY]
    
    all_colls = db.list_collection_names()
    backups = sorted([c for c in all_colls if c.startswith("lottery_v2_backup_")])
    
    if not backups:
        print("❌ No backups found!")
        return
    
    latest = backups[-1]
    backup_count = db[latest].count_documents({})
    current_count = db["lottery_v2"].count_documents({})
    
    print(f"  Restoring from: {latest} ({backup_count:,} records)")
    print(f"  Current lottery_v2: {current_count:,} records")
    
    if current_count > 0:
        confirm = input("  lottery_v2 is not empty. Overwrite? (YES): ").strip()
        if confirm != "YES":
            print("  Aborted.")
            return
        db["lottery_v2"].drop()
    
    # Batched restore
    restored = 0
    batch = []
    for doc in db[latest].find({}).batch_size(5000):
        doc.pop('_id', None)
        batch.append(doc)
        if len(batch) >= 2000:
            db["lottery_v2"].insert_many(batch, ordered=False)
            restored += len(batch)
            print(f"     Restored: {restored:,}", end="\r")
            batch = []
    if batch:
        db["lottery_v2"].insert_many(batch, ordered=False)
        restored += len(batch)
    
    # Recreate index
    db["lottery_v2"].create_index(
        [("state_name", ASCENDING), ("game_name", ASCENDING),
         ("date", ASCENDING), ("tod", ASCENDING)],
        unique=True, name="unique_draw"
    )
    
    final = db["lottery_v2"].count_documents({})
    print(f"\n  ✅ Restored: {final:,} records from {latest}")
    client.close()


def cmd_rebuild(dry_run=False):
    """Rebuild lottery_v2 from lotterypost in yearly chunks."""
    client = MongoClient(MONGO_URL)
    source = client[DB_SOURCE]["lotterypost"]
    target = client[DB_LOTTERY]["lottery_v2"]
    
    # Find date range in source
    first = source.find_one(sort=[("date", 1)])
    last = source.find_one(sort=[("date", -1)])
    
    if not first or not last:
        print("❌ No data in lotterypost!")
        return
    
    first_year = first["date"].year
    last_year = last["date"].year
    
    current_count = target.count_documents({})
    total_source = source.count_documents({})
    
    print("=" * 65)
    print("  CHUNKED REBUILD: lotterypost → lottery_v2")
    print("=" * 65)
    print(f"  Source: {total_source:,} records ({first_year}-{last_year})")
    print(f"  Current lottery_v2: {current_count:,} records")
    print(f"  Strategy: Process 1 year at a time to avoid timeouts")
    
    if dry_run:
        print(f"\n  [DRY RUN] Would process {last_year - first_year + 1} yearly chunks")
        for year in range(first_year, last_year + 1):
            start = datetime(year, 1, 1)
            end = datetime(year, 12, 31, 23, 59, 59)
            count = source.count_documents({"date": {"$gte": start, "$lte": end}})
            print(f"    {year}: {count:,} source records")
        client.close()
        return
    
    # Confirm
    if current_count > 0:
        print(f"\n  ⚠️  lottery_v2 has {current_count:,} records. Drop and rebuild?")
        confirm = input("  Type YES: ").strip()
        if confirm != "YES":
            print("  Aborted.")
            client.close()
            return
        target.drop()
    
    # Process year by year
    total_written = 0
    total_skipped = 0
    seen = set()
    
    for year in range(first_year, last_year + 1):
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31, 23, 59, 59)
        
        docs = list(source.find({"date": {"$gte": start, "$lte": end}}).batch_size(5000))
        
        batch = []
        year_written = 0
        year_skipped = 0
        
        for doc in docs:
            r = enrich(doc)
            if r is None:
                year_skipped += 1
                continue
            key = (r["state_name"], r["game_name"], str(r["date"]), r["tod"])
            if key in seen:
                year_skipped += 1
                continue
            seen.add(key)
            batch.append(r)
            
            if len(batch) >= 2000:
                target.insert_many(batch, ordered=False)
                year_written += len(batch)
                batch = []
        
        if batch:
            target.insert_many(batch, ordered=False)
            year_written += len(batch)
        
        total_written += year_written
        total_skipped += year_skipped
        print(f"    {year}: +{year_written:,} written, {year_skipped:,} skipped  (total: {total_written:,})")
    
    # Create unique index
    print(f"\n  📇 Creating unique index...")
    target.create_index(
        [("state_name", ASCENDING), ("game_name", ASCENDING),
         ("date", ASCENDING), ("tod", ASCENDING)],
        unique=True, name="unique_draw"
    )
    
    # Final stats
    final = target.count_documents({})
    states = len(target.distinct("state_name"))
    games = len(target.distinct("game_name"))
    print(f"\n  ✅ REBUILD COMPLETE")
    print(f"     Records: {final:,}")
    print(f"     States:  {states}")
    print(f"     Games:   {games}")
    print(f"     Skipped: {total_skipped:,}")
    
    client.close()


def main():
    parser = argparse.ArgumentParser(description="Chunked rebuild for Atlas")
    parser.add_argument("--restore", action="store_true", help="Restore from backup")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    
    if args.restore:
        cmd_restore()
    else:
        cmd_rebuild(args.dry_run)


if __name__ == "__main__":
    main()
