#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
  MyLottoData: Database Maintenance Suite
═══════════════════════════════════════════════════════════════════════

Commands:
  python db_maintenance.py promote      # Copy lottery_v2_test → lottery_v2 (with backup)
  python db_maintenance.py sync         # Daily sync from lotterypost → lottery_v2
  python db_maintenance.py sync --days 7
  python db_maintenance.py healthcheck  # Compare lottery_v2 vs lotterypost
  python db_maintenance.py backup       # Backup lottery_v2 → lottery_v2_backup_YYYYMMDD
  python db_maintenance.py restore      # Restore from most recent backup
  python db_maintenance.py rollback     # Swap lottery_v2_backup → lottery_v2

All commands support --dry-run for preview.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from itertools import combinations
from collections import Counter, defaultdict
from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"
DB_LOTTERY = "lottery"
DB_SOURCE  = "mylottodata"
COLL_V2       = "lottery_v2"
COLL_TEST     = "lottery_v2_test"
COLL_SOURCE   = "lotterypost"

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


# ═══════════════════════════════════════════════════════════════════
#  ENRICHMENT (shared by sync and rebuild)
# ═══════════════════════════════════════════════════════════════════

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
    """Transform a lotterypost record into lottery_v2 format."""
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


# ═══════════════════════════════════════════════════════════════════
#  COMMAND: promote — copy lottery_v2_test → lottery_v2
# ═══════════════════════════════════════════════════════════════════

def cmd_promote(args):
    """
    Strategy: 
    1. Full rebuild from lotterypost (not just copy test's 60 days)
    2. Backup old lottery_v2 first
    3. Drop and rebuild lottery_v2 from scratch
    4. Create unique index
    """
    client = MongoClient(MONGO_URL)
    db = client[DB_LOTTERY]
    source = client[DB_SOURCE][COLL_SOURCE]
    target = db[COLL_V2]

    # Step 1: Backup
    old_count = target.count_documents({})
    backup_name = f"lottery_v2_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print("=" * 65)
    print("  PROMOTE: Full Rebuild lottery_v2 from lotterypost")
    print("=" * 65)
    print(f"\n  Current lottery_v2: {old_count:,} records")
    print(f"  Backup to: {backup_name}")
    
    if args.dry_run:
        # Count what we'd write
        total_source = source.count_documents({})
        print(f"  Source (lotterypost): {total_source:,} records")
        print(f"\n  [DRY RUN] Would backup → rebuild → reindex")
        client.close()
        return

    # Confirm
    print(f"\n  ⚠️  This will DROP lottery_v2 ({old_count:,} records) and rebuild from lotterypost.")
    confirm = input("  Type YES to proceed: ").strip()
    if confirm != "YES":
        print("  Aborted.")
        client.close()
        return

    # Backup (batched to avoid Atlas timeout)
    if args.skip_backup:
        print(f"\n  ⏭️  Skipping backup (--skip-backup)")
        backup_count = 0
    else:
        print(f"\n  📦 Backing up lottery_v2 → {backup_name} (batched)...")
        backup_coll = db[backup_name]
        backup_batch = []
        backup_count = 0
        for doc in target.find({}).batch_size(5000):
            doc.pop('_id', None)
            backup_batch.append(doc)
            if len(backup_batch) >= 2000:
                backup_coll.insert_many(backup_batch, ordered=False)
                backup_count += len(backup_batch)
                print(f"     Backed up: {backup_count:,}", end="\r")
                backup_batch = []
        if backup_batch:
            backup_coll.insert_many(backup_batch, ordered=False)
            backup_count += len(backup_batch)
        print(f"     Backup: {backup_count:,} records ✅              ")

    # Drop and rebuild
    print(f"\n  🗑️  Dropping lottery_v2...")
    target.drop()

    print(f"\n  🔄 Rebuilding from lotterypost...")
    batch = []
    written = 0
    skipped = 0
    seen = set()
    
    cursor = source.find({}).batch_size(5000)
    total = source.count_documents({})
    
    for i, doc in enumerate(cursor):
        r = enrich(doc)
        if r is None:
            skipped += 1
            continue
        
        key = (r["state_name"], r["game_name"], str(r["date"]), r["tod"])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        
        batch.append(r)
        if len(batch) >= 2000:
            target.insert_many(batch, ordered=False)
            written += len(batch)
            pct = (i + 1) / total * 100
            print(f"     Written: {written:,} ({pct:.1f}%)", end="\r")
            batch = []
    
    if batch:
        target.insert_many(batch, ordered=False)
        written += len(batch)
    
    print(f"     Written: {written:,} records              ")
    print(f"     Skipped: {skipped:,} (non-pick or dupes)")

    # Create unique index
    print(f"\n  📇 Creating unique index...")
    target.create_index(
        [("state_name", ASCENDING), ("game_name", ASCENDING),
         ("date", ASCENDING), ("tod", ASCENDING)],
        unique=True, name="unique_draw"
    )
    print(f"     unique_draw index created ✅")

    # Verify
    final_count = target.count_documents({})
    states = len(target.distinct("state_name"))
    games = len(target.distinct("game_name"))
    print(f"\n  ✅ DONE: {final_count:,} records, {states} states, {games} games")
    print(f"     Backup preserved as: {backup_name} ({backup_count:,} records)")
    
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  COMMAND: sync — daily sync from lotterypost → lottery_v2
# ═══════════════════════════════════════════════════════════════════

def cmd_sync(args):
    client = MongoClient(MONGO_URL)
    source = client[DB_SOURCE][COLL_SOURCE]
    target = client[DB_LOTTERY][COLL_V2]

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
        date_from, date_to = d, d
    elif args.date_from and args.date_to:
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d")
        date_to = datetime.strptime(args.date_to, "%Y-%m-%d")
    else:
        days = args.days or 1
        date_from = today - timedelta(days=days)
        date_to = today

    print("=" * 65)
    print(f"  SYNC: {date_from.date()} → {date_to.date()}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 65)

    docs = list(source.find({"date": {"$gte": date_from, "$lte": date_to}}))
    print(f"\n  Source records: {len(docs)}")

    enriched = []
    seen = set()
    for doc in docs:
        r = enrich(doc)
        if r is None:
            continue
        key = (r["state_name"], r["game_name"], str(r["date"]), r["tod"])
        if key in seen:
            continue
        seen.add(key)
        enriched.append(r)

    types = Counter(r["game_type"] for r in enriched)
    print(f"  Enriched: {len(enriched)}")
    for gt in sorted(types):
        print(f"    {gt}: {types[gt]}")

    if args.dry_run:
        print(f"\n  [DRY RUN] Would upsert {len(enriched)} records")
        for r in enriched[:10]:
            print(f"    {r['state_name']:25s} {r['game_name']:25s} {r['date'].strftime('%Y-%m-%d')} tod={r['tod']}")
        if len(enriched) > 10:
            print(f"    ... and {len(enriched)-10} more")
        client.close()
        return

    if not enriched:
        print("  Nothing to sync.")
        client.close()
        return

    ops = [
        UpdateOne(
            {"state_name": r["state_name"], "game_name": r["game_name"],
             "date": r["date"], "tod": r["tod"]},
            {"$set": r}, upsert=True
        ) for r in enriched
    ]

    inserted = modified = errors = 0
    for i in range(0, len(ops), 500):
        try:
            res = target.bulk_write(ops[i:i+500], ordered=False)
            inserted += res.upserted_count
            modified += res.modified_count
        except BulkWriteError as e:
            errors += len(e.details.get("writeErrors", []))
            inserted += e.details.get("nUpserted", 0)
            modified += e.details.get("nModified", 0)

    print(f"\n  ✅ Inserted: {inserted}, Updated: {modified}, Errors: {errors}")
    print(f"  Total lottery_v2: {target.count_documents({}):,}")
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  COMMAND: healthcheck
# ═══════════════════════════════════════════════════════════════════

def cmd_healthcheck(args):
    client = MongoClient(MONGO_URL)
    source = client[DB_SOURCE][COLL_SOURCE]
    target = client[DB_LOTTERY][COLL_V2]
    
    print("=" * 65)
    print("  HEALTHCHECK: lottery_v2 vs lotterypost")
    print("=" * 65)
    
    # Basic counts
    src_count = source.count_documents({})
    tgt_count = target.count_documents({})
    print(f"\n  lotterypost:  {src_count:,} records")
    print(f"  lottery_v2:   {tgt_count:,} records")
    
    # Check last dates
    src_last = source.find_one(sort=[("date", -1)])
    tgt_last = target.find_one(sort=[("date", -1)])
    src_date = src_last["date"].strftime("%Y-%m-%d") if src_last else "NONE"
    tgt_date = tgt_last["date"].strftime("%Y-%m-%d") if tgt_last else "NONE"
    print(f"\n  Last date (source): {src_date}")
    print(f"  Last date (target): {tgt_date}")
    
    if src_date != tgt_date:
        print(f"  ⚠️  TARGET IS BEHIND by {src_date} vs {tgt_date}")
    else:
        print(f"  ✅ Both up to date")
    
    # Check recent days
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"\n  Recent day-by-day comparison:")
    issues = 0
    for days_ago in range(7):
        d = today - timedelta(days=days_ago)
        src_n = source.count_documents({"date": d})
        tgt_n = target.count_documents({"date": d})
        
        # Count only pick games in source
        src_picks = 0
        for doc in source.find({"date": d}):
            nums = parse_numbers(doc.get("numbers"))
            if is_pick_game(nums):
                src_picks += 1
        
        status = "✅" if tgt_n >= src_picks * 0.9 else "⚠️"
        if tgt_n < src_picks * 0.9:
            issues += 1
        print(f"    {d.strftime('%Y-%m-%d')}: source={src_n} (picks={src_picks}) target={tgt_n}  {status}")
    
    # Check Pick 5 states specifically
    print(f"\n  Pick 5 states check (last 3 days):")
    pick5_states = ['Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio',
                    'Pennsylvania', 'Georgia', 'Washington, D.C.', 'Louisiana']
    
    for state in pick5_states:
        recent = target.count_documents({
            "state_name": state,
            "game_type": "pick5",
            "date": {"$gte": today - timedelta(days=3)}
        })
        expected = 6 if state != "Louisiana" else 3  # 2 draws/day × 3 days, Louisiana = 1/day
        status = "✅" if recent >= expected * 0.8 else "⚠️"
        print(f"    {state:25s}: {recent} draws (expected ~{expected})  {status}")
    
    # Check for duplicates
    pipeline = [
        {"$group": {
            "_id": {"state": "$state_name", "game": "$game_name", "date": "$date", "tod": "$tod"},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$count": "duplicates"}
    ]
    dup_result = list(target.aggregate(pipeline))
    dup_count = dup_result[0]["duplicates"] if dup_result else 0
    
    if dup_count:
        print(f"\n  ❌ DUPLICATES FOUND: {dup_count}")
    else:
        print(f"\n  ✅ No duplicates")
    
    # Check for null/broken records
    broken = target.count_documents({"$or": [
        {"state_name": None}, {"state_name": ""},
        {"game_name": None}, {"game_name": ""},
        {"numbers": None},
    ]})
    if broken:
        print(f"  ❌ BROKEN RECORDS: {broken}")
    else:
        print(f"  ✅ No broken records")
    
    # Indexes
    indexes = target.index_information()
    has_unique = any(idx.get("unique") for idx in indexes.values() if "_id" not in idx.get("key", [[""]])[0])
    if has_unique:
        print(f"  ✅ Unique index present")
    else:
        print(f"  ⚠️  No unique index — duplicates can creep in")
    
    # Summary
    print(f"\n  {'─' * 50}")
    if issues == 0 and dup_count == 0 and broken == 0 and src_date == tgt_date:
        print(f"  ✅ HEALTHY — all checks passed")
    else:
        print(f"  ⚠️  ISSUES: {issues} day gaps, {dup_count} dupes, {broken} broken, lag={src_date != tgt_date}")
        if tgt_date < src_date:
            print(f"     FIX: python db_maintenance.py sync --days 3")
    
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  COMMAND: backup
# ═══════════════════════════════════════════════════════════════════

def cmd_backup(args):
    client = MongoClient(MONGO_URL)
    db = client[DB_LOTTERY]
    target = db[COLL_V2]
    
    backup_name = f"lottery_v2_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    count = target.count_documents({})
    
    print("=" * 65)
    print(f"  BACKUP: lottery_v2 → {backup_name}")
    print(f"  Records: {count:,}")
    print("=" * 65)
    
    if args.dry_run:
        print(f"  [DRY RUN] Would create backup with {count:,} records")
        client.close()
        return
    
    backup_coll = db[backup_name]
    backed = 0
    batch = []
    for doc in target.find({}).batch_size(5000):
        doc.pop('_id', None)
        batch.append(doc)
        if len(batch) >= 2000:
            backup_coll.insert_many(batch, ordered=False)
            backed += len(batch)
            print(f"     Backed up: {backed:,}", end="\r")
            batch = []
    if batch:
        backup_coll.insert_many(batch, ordered=False)
        backed += len(batch)
    
    print(f"\n  ✅ Backup created: {backup_name} ({backed:,} records)")
    
    # List all backups
    all_colls = db.list_collection_names()
    backups = sorted([c for c in all_colls if c.startswith("lottery_v2_backup_")])
    print(f"\n  All backups ({len(backups)}):")
    for b in backups:
        bc = db[b].count_documents({})
        print(f"    {b}: {bc:,} records")
    
    # Auto-cleanup: keep only last 3 backups
    if len(backups) > 3:
        to_delete = backups[:-3]
        print(f"\n  🧹 Cleaning old backups (keeping last 3):")
        for old in to_delete:
            db[old].drop()
            print(f"    Dropped: {old}")
    
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  COMMAND: restore — restore from most recent backup
# ═══════════════════════════════════════════════════════════════════

def cmd_restore(args):
    client = MongoClient(MONGO_URL)
    db = client[DB_LOTTERY]
    
    all_colls = db.list_collection_names()
    backups = sorted([c for c in all_colls if c.startswith("lottery_v2_backup_")])
    
    if not backups:
        print("  ❌ No backups found!")
        client.close()
        return
    
    latest = backups[-1]
    backup_count = db[latest].count_documents({})
    current_count = db[COLL_V2].count_documents({})
    
    print("=" * 65)
    print(f"  RESTORE: {latest} → lottery_v2")
    print(f"  Backup records:  {backup_count:,}")
    print(f"  Current records: {current_count:,}")
    print("=" * 65)
    
    if args.dry_run:
        print(f"  [DRY RUN] Would restore {backup_count:,} records from {latest}")
        client.close()
        return
    
    confirm = input(f"  Type YES to restore from {latest}: ").strip()
    if confirm != "YES":
        print("  Aborted.")
        client.close()
        return
    
    # Safety: backup current before restoring
    safety_name = f"lottery_v2_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n  📦 Safety backup: lottery_v2 → {safety_name}...")
    safety_coll = db[safety_name]
    s_count = 0
    s_batch = []
    for doc in db[COLL_V2].find({}).batch_size(5000):
        doc.pop('_id', None)
        s_batch.append(doc)
        if len(s_batch) >= 2000:
            safety_coll.insert_many(s_batch, ordered=False)
            s_count += len(s_batch)
            print(f"     Safety backed up: {s_count:,}", end="\r")
            s_batch = []
    if s_batch:
        safety_coll.insert_many(s_batch, ordered=False)
        s_count += len(s_batch)
    print(f"     Safety backup: {s_count:,} records              ")
    
    # Restore
    print(f"  🔄 Restoring from {latest}...")
    db[COLL_V2].drop()
    
    r_count = 0
    r_batch = []
    for doc in db[latest].find({}).batch_size(5000):
        doc.pop('_id', None)
        r_batch.append(doc)
        if len(r_batch) >= 2000:
            db[COLL_V2].insert_many(r_batch, ordered=False)
            r_count += len(r_batch)
            print(f"     Restored: {r_count:,}", end="\r")
            r_batch = []
    if r_batch:
        db[COLL_V2].insert_many(r_batch, ordered=False)
        r_count += len(r_batch)
    
    # Recreate index
    db[COLL_V2].create_index(
        [("state_name", ASCENDING), ("game_name", ASCENDING),
         ("date", ASCENDING), ("tod", ASCENDING)],
        unique=True, name="unique_draw"
    )
    
    restored = db[COLL_V2].count_documents({})
    print(f"\n  ✅ Restored: {restored:,} records")
    print(f"     Pre-restore saved as: {safety_name}")
    
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MyLottoData DB Maintenance Suite")
    sub = parser.add_subparsers(dest="command")
    
    # promote
    p_promote = sub.add_parser("promote", help="Full rebuild lottery_v2 from lotterypost")
    p_promote.add_argument("--dry-run", action="store_true")
    p_promote.add_argument("--skip-backup", action="store_true", help="Skip backup (use if backup already exists)")
    
    # sync
    p_sync = sub.add_parser("sync", help="Daily sync from lotterypost")
    p_sync.add_argument("--date", help="YYYY-MM-DD")
    p_sync.add_argument("--from", dest="date_from", help="Start date")
    p_sync.add_argument("--to", dest="date_to", help="End date")
    p_sync.add_argument("--days", type=int, help="Last N days")
    p_sync.add_argument("--dry-run", action="store_true")
    
    # healthcheck
    p_health = sub.add_parser("healthcheck", help="Compare lottery_v2 vs lotterypost")
    p_health.add_argument("--dry-run", action="store_true")
    
    # backup
    p_backup = sub.add_parser("backup", help="Backup lottery_v2")
    p_backup.add_argument("--dry-run", action="store_true")
    
    # restore
    p_restore = sub.add_parser("restore", help="Restore from latest backup")
    p_restore.add_argument("--dry-run", action="store_true")
    
    args = parser.parse_args()
    
    commands = {
        "promote": cmd_promote,
        "sync": cmd_sync,
        "healthcheck": cmd_healthcheck,
        "backup": cmd_backup,
        "restore": cmd_restore,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        print("\n  Quick start:")
        print("    python db_maintenance.py healthcheck          # Check status")
        print("    python db_maintenance.py promote --dry-run    # Preview rebuild")
        print("    python db_maintenance.py promote              # Full rebuild")
        print("    python db_maintenance.py sync                 # Sync yesterday")
        print("    python db_maintenance.py sync --days 7        # Sync last week")
        print("    python db_maintenance.py backup               # Manual backup")
        print("    python db_maintenance.py restore              # Restore from backup")


if __name__ == "__main__":
    main()
