#!/usr/bin/env python3
"""
MyLottoData: Sync & Enrich Pipeline
=====================================
Pulls Pick 2-5 data from mylottodata.lotterypost,
enriches it with computed analytical fields, and
upserts into lottery.lottery_v2.

Usage:
    # Sync yesterday's data
    python sync_enrich.py

    # Sync a specific date
    python sync_enrich.py --date 2026-02-25

    # Sync a date range
    python sync_enrich.py --from 2026-02-01 --to 2026-02-25

    # Sync last N days
    python sync_enrich.py --days 7

    # Dry run (show what would be synced without writing)
    python sync_enrich.py --dry-run

    # Full historical rebuild (WARNING: processes all records)
    python sync_enrich.py --full-rebuild
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from itertools import combinations
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

# ── Game slug mappings ──
# Maps (state_name, game_name) patterns to (state_slug, game_slug)
# We'll auto-generate these from the data where possible

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
    # Canadian provinces
    "Atlantic Canada": "atlantic-canada", "British Columbia": "bc",
    "Ontario": "on", "Québec": "qc", "Western Canada": "western-canada",
    # International
    "Germany": "de-eu", "Ireland": "ie",
    # Multi-state
    "Multi-State": "multi",
}


def make_game_slug(game_name):
    """Convert game name to URL-friendly slug."""
    return game_name.lower().replace(" ", "-").replace(".", "").replace(",", "")


def detect_tod(game_name, tod_field):
    """Determine time of day from game name and/or tod field.
    
    Priority: 
    1. Use the lotterypost tod field as-is if present (preserves source data)
    2. Only infer from game_name if tod is empty (for games like "Pick 4 Midday")
    """
    # If lotterypost provides a tod value, use it directly
    if tod_field and tod_field.strip():
        return tod_field.strip()
    
    # Only infer from game name if tod is empty
    name_lower = game_name.lower()
    if any(kw in name_lower for kw in ["midday", "mid-day"]):
        return "Midday"
    if "evening" in name_lower:
        return "Evening"
    if " night" in name_lower or name_lower.endswith("night"):
        return "Night"
    if " day" in name_lower or name_lower.endswith("day"):
        return "Day"
    if "morning" in name_lower:
        return "Morning"
    
    return ""


def is_pick_game(numbers):
    """Check if a draw is a Pick 2-5 game (2-5 single digits)."""
    if not numbers or not isinstance(numbers, list):
        return False
    if len(numbers) not in [2, 3, 4, 5]:
        return False
    return all(isinstance(n, str) and len(n) == 1 and n.isdigit() for n in numbers)


def parse_numbers(numbers_raw):
    """Parse numbers from various formats into a list of strings."""
    if isinstance(numbers_raw, list):
        return [str(n) for n in numbers_raw]
    if isinstance(numbers_raw, str):
        try:
            parsed = json.loads(numbers_raw)
            if isinstance(parsed, list):
                return [str(n) for n in parsed]
        except json.JSONDecodeError:
            pass
    return []


def enrich_record(doc):
    """
    Transform a lotterypost document into an enriched lottery_v2 document.
    Returns None if the record is not a valid Pick 2-5 game.
    """
    numbers = parse_numbers(doc.get("numbers"))
    
    if not is_pick_game(numbers):
        return None
    
    num_digits = len(numbers)
    game_type = f"pick{num_digits}"
    state_name = doc.get("state_name", "")
    game_name = doc.get("game_name", "")
    
    # Compute analytical fields
    digits = [int(n) for n in numbers]
    digits_sorted = sorted(digits)
    
    number_str = "".join(numbers)
    normalized = "".join(str(d) for d in digits_sorted)
    digits_sum = sum(digits)
    
    # Generate pair combinations (sorted 2-digit strings)
    pairs_2dp = sorted(set(
        "".join(str(d) for d in sorted(combo))
        for combo in combinations(digits, 2)
    ))
    
    # Generate triple combinations (sorted 3-digit strings) — only for 4+ digit games
    triples_3dp = []
    if num_digits >= 4:
        triples_3dp = sorted(set(
            "".join(str(d) for d in sorted(combo))
            for combo in combinations(digits, 3)
        ))
    
    # Determine slugs
    state_slug = STATE_SLUGS.get(state_name, state_name.lower().replace(" ", "-"))
    game_slug = make_game_slug(game_name)
    tod = detect_tod(game_name, doc.get("tod", ""))
    
    return {
        "country": "United States" if doc.get("country") == "USA" else doc.get("country", "United States"),
        "state": state_slug,
        "state_name": state_name,
        "game": game_slug,
        "game_name": game_name,
        "game_type": game_type,
        "date": doc.get("date"),
        "numbers": json.dumps(numbers),  # Always store as JSON string for consistency
        "number_str": number_str,
        "normalized": normalized,
        "digits_sum": digits_sum,
        "pairs_2dp": pairs_2dp,
        "triples_3dp": triples_3dp,
        "tod": tod,
        "num_digits": num_digits,
        "source": "sync",
    }


def ensure_unique_index(coll):
    """Create the unique index if it doesn't exist."""
    existing = coll.index_information()
    if "unique_draw" not in existing:
        print("  Creating unique index 'unique_draw'...")
        try:
            coll.create_index(
                [("state_name", 1), ("game_name", 1), ("date", 1), ("tod", 1)],
                unique=True,
                name="unique_draw"
            )
            print("  ✅ Unique index created!")
        except Exception as e:
            print(f"  ⚠️  Could not create unique index: {e}")
            print("     You may need to remove duplicate records first.")
            return False
    else:
        print("  ✅ Unique index already exists.")
    return True


def sync(date_from, date_to, dry_run=False, full_rebuild=False):
    """Main sync function."""
    client = MongoClient(MONGO_URL)
    
    source = client["mylottodata"]["lotterypost"]
    target = client["lottery"]["lottery_v2"]
    
    print("=" * 70)
    print("  MyLottoData Sync & Enrich Pipeline")
    print(f"  Run at: {datetime.now().isoformat()}")
    print(f"  Date range: {date_from.date()} → {date_to.date()}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 70)
    
    # Ensure unique index exists
    if not dry_run:
        print("\n🔧 Checking indexes...")
        ensure_unique_index(target)
    
    # Query lotterypost for the date range
    query = {"date": {"$gte": date_from, "$lte": date_to}}
    
    print(f"\n📥 Fetching records from lotterypost...")
    lp_docs = list(source.find(query))
    print(f"  Found {len(lp_docs)} total records in date range")
    
    # Enrich and filter to Pick 2-5
    enriched = []
    skipped = 0
    
    for doc in lp_docs:
        result = enrich_record(doc)
        if result:
            enriched.append(result)
        else:
            skipped += 1
    
    print(f"  Enriched Pick 2-5 records: {len(enriched)}")
    print(f"  Skipped (non-Pick 2-5): {skipped}")
    
    if not enriched:
        print("\n  Nothing to sync!")
        client.close()
        return
    
    # Show summary by game type
    from collections import Counter
    type_counts = Counter(r["game_type"] for r in enriched)
    state_counts = Counter(r["state_name"] for r in enriched)
    
    print(f"\n  By game type:")
    for gt in sorted(type_counts.keys()):
        print(f"    {gt}: {type_counts[gt]}")
    
    print(f"\n  By state ({len(state_counts)} states):")
    for state in sorted(state_counts.keys()):
        print(f"    {state}: {state_counts[state]}")
    
    if dry_run:
        print(f"\n🔍 DRY RUN — showing first 5 enriched records:")
        for doc in enriched[:5]:
            print(f"  {doc['state_name']} / {doc['game_name']} / {doc['date'].date()} / tod={doc['tod']}")
            print(f"    numbers={doc['numbers']} number_str={doc['number_str']} normalized={doc['normalized']}")
            print(f"    digits_sum={doc['digits_sum']} pairs={doc['pairs_2dp']}")
        print(f"\n  Would upsert {len(enriched)} records. Run without --dry-run to execute.")
        client.close()
        return
    
    # Reconcile old-format records where tod was baked into game_name
    # e.g., old sync created "Pick 4 Midday" + "Pick 4 Evening" as game_name
    # but lotterypost has "Pick 4" with tod="Day"/"Evening"
    # We need to remove the old-format duplicates so they don't coexist
    print(f"\n🔧 Reconciling old-format records (tod in game_name)...")
    
    tod_suffixes = [" Midday", " Evening", " Day", " Night", " Morning"]
    old_format_filter = {
        "source": {"$in": ["sync", None]},
        "date": {"$gte": date_from, "$lte": date_to},
        "$or": [{"game_name": {"$regex": suffix + "$"}} for suffix in tod_suffixes]
    }
    old_format_count = target.count_documents(old_format_filter)
    if old_format_count > 0:
        print(f"  Found {old_format_count} old-format records with tod in game_name")
        if not dry_run:
            # Only delete old-format records that will be replaced by new-format ones
            # Build a set of (state_name, base_game, date) from our enriched data
            new_keys = set()
            for doc in enriched:
                new_keys.add((doc["state_name"], doc["game_name"], str(doc["date"])))
            
            old_to_delete = list(target.find(old_format_filter, {"_id": 1, "state_name": 1, "game_name": 1, "date": 1}))
            ids_to_remove = []
            for old_doc in old_to_delete:
                # Strip tod suffix from old game_name to get base name
                old_game = old_doc.get("game_name", "")
                base_game = old_game
                for suffix in tod_suffixes:
                    if old_game.endswith(suffix):
                        base_game = old_game[:-len(suffix)]
                        break
                # Check if we have a new-format replacement
                key = (old_doc.get("state_name"), base_game, str(old_doc.get("date")))
                if key in new_keys:
                    ids_to_remove.append(old_doc["_id"])
            
            if ids_to_remove:
                result = target.delete_many({"_id": {"$in": ids_to_remove}})
                print(f"  ✅ Removed {result.deleted_count} old-format records (replaced by new-format)")
            else:
                print(f"  No old-format records need removal (no matching new-format replacements)")
    else:
        print(f"  ✅ No old-format records found")

    # Upsert into lottery_v2
    print(f"\n📤 Upserting {len(enriched)} records into lottery_v2...")
    
    operations = []
    for doc in enriched:
        filter_key = {
            "state_name": doc["state_name"],
            "game_name": doc["game_name"],
            "date": doc["date"],
            "tod": doc["tod"],
        }
        operations.append(UpdateOne(filter_key, {"$set": doc}, upsert=True))
    
    # Execute in batches of 500
    batch_size = 500
    total_inserted = 0
    total_updated = 0
    total_errors = 0
    
    for i in range(0, len(operations), batch_size):
        batch = operations[i:i + batch_size]
        try:
            result = target.bulk_write(batch, ordered=False)
            total_inserted += result.upserted_count
            total_updated += result.modified_count
        except BulkWriteError as bwe:
            total_errors += len(bwe.details.get("writeErrors", []))
            # Still count successes
            total_inserted += bwe.details.get("nUpserted", 0)
            total_updated += bwe.details.get("nModified", 0)
            print(f"  ⚠️  Batch {i//batch_size + 1}: {len(bwe.details.get('writeErrors', []))} errors")
    
    print(f"\n  ✅ Sync complete!")
    print(f"     Inserted (new):  {total_inserted}")
    print(f"     Updated:         {total_updated}")
    print(f"     Errors:          {total_errors}")
    
    # Verify
    print(f"\n🔍 Verification:")
    for dt in [date_from, date_to]:
        count = target.count_documents({"date": dt})
        lp_count = source.count_documents({"date": dt})
        print(f"  {dt.date()}: lottery_v2 has {count} records (lotterypost has {lp_count} total)")
    
    total = target.count_documents({})
    print(f"\n  Total lottery_v2 records: {total:,}")
    
    print("\n" + "=" * 70)
    print("  SYNC COMPLETE")
    print("=" * 70)
    
    client.close()


def main():
    parser = argparse.ArgumentParser(description="MyLottoData Sync & Enrich Pipeline")
    parser.add_argument("--date", help="Sync a specific date (YYYY-MM-DD)")
    parser.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, help="Sync last N days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without writing")
    parser.add_argument("--full-rebuild", action="store_true", help="Rebuild all Pick 2-5 data from lotterypost")
    
    args = parser.parse_args()
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    
    if args.full_rebuild:
        # Full rebuild from the beginning of time
        date_from = datetime(1900, 1, 1)
        date_to = today
        print("⚠️  FULL REBUILD MODE — this will process ALL lotterypost records!")
        if not args.dry_run:
            confirm = input("Are you sure? (type YES to confirm): ")
            if confirm != "YES":
                print("Aborted.")
                sys.exit(0)
    elif args.date:
        date_from = datetime.strptime(args.date, "%Y-%m-%d")
        date_to = date_from
    elif args.date_from and args.date_to:
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d")
        date_to = datetime.strptime(args.date_to, "%Y-%m-%d")
    elif args.days:
        date_from = today - timedelta(days=args.days)
        date_to = today
    else:
        # Default: sync yesterday
        date_from = yesterday
        date_to = yesterday
    
    sync(date_from, date_to, dry_run=args.dry_run, full_rebuild=args.full_rebuild)


if __name__ == "__main__":
    main()
