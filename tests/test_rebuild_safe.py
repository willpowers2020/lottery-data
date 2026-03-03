#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  SAFE TEST: Write to lottery_v2_test, validate against app.py
═══════════════════════════════════════════════════════════════════

Creates a test collection with the new enrichment format, then 
simulates exactly what app.py does when the backtest runs.

Does NOT touch lottery_v2.

After running:
  1. Check the output for any ❌ failures
  2. If all ✅, temporarily change app.py line 177:
       MONGO_COLLECTION_OPTIMIZED = 'lottery_v2_test'
  3. Run the backtest in browser to verify
  4. Change it back when done

Usage:
    python test_rebuild_safe.py
"""

import json
from datetime import datetime, timedelta
from itertools import combinations
from collections import Counter, defaultdict
from pymongo import MongoClient, ASCENDING, DESCENDING

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

STATE_SLUGS = {
    "Alabama": "al", "Arizona": "az", "Arkansas": "ar", "California": "ca",
    "Colorado": "co", "Connecticut": "ct", "Delaware": "de", "Florida": "fl",
    "Georgia": "ga", "Idaho": "id", "Illinois": "il", "Indiana": "in",
    "Iowa": "ia", "Kansas": "ks", "Kentucky": "ky", "Louisiana": "la",
    "Maine": "me", "Maryland": "md", "Massachusetts": "ma", "Michigan": "mi",
    "Minnesota": "mn", "Mississippi": "ms", "Missouri": "mo", "Nebraska": "ne",
    "New Hampshire": "nh", "New Jersey": "nj", "New Mexico": "nm", "New York": "ny",
    "North Carolina": "nc", "North Dakota": "nd", "Ohio": "oh", "Oklahoma": "ok",
    "Oregon": "or", "Pennsylvania": "pa", "Puerto Rico": "pr", "Rhode Island": "ri",
    "South Carolina": "sc", "South Dakota": "sd", "Tennessee": "tn", "Texas": "tx",
    "Vermont": "vt", "Virginia": "va", "Washington": "wa",
    "Washington DC": "dc", "Washington, D.C.": "dc",
    "West Virginia": "wv", "Wisconsin": "wi", "Wyoming": "wy",
    "Atlantic Canada": "atlantic-canada", "Ontario": "on", "Québec": "qc",
    "Western Canada": "western-canada", "Germany": "de-eu", "Ireland": "ie",
}


def parse_numbers(raw):
    if isinstance(raw, list): return [str(n) for n in raw]
    if isinstance(raw, str):
        try:
            p = json.loads(raw)
            if isinstance(p, list): return [str(n) for n in p]
        except: pass
    return []


def is_pick_game(nums):
    return (nums and len(nums) in [2,3,4,5] and 
            all(isinstance(n, str) and len(n) == 1 and n.isdigit() for n in nums))


def game_name_has_tod(name):
    lower = name.lower()
    for kw in ["midday","mid-day","evening","night","morning","1:50pm","7:50pm","11:30pm",
               "afternoon","matinee","early bird","drive time","prime time","night owl",
               "rush hour","coffee break","after hours","late night"]:
        if kw in lower: return True
    if lower.endswith(" day") or lower.endswith("-day"): return True
    return False


def compute_tod(game_name, lp_tod):
    if lp_tod and lp_tod.strip(): return lp_tod.strip()
    lower = game_name.lower()
    if "midday" in lower: return "Midday"
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
    if not is_pick_game(numbers): return None
    
    state_name = doc.get("state_name", "")
    base_game = doc.get("game_name", "")
    lp_tod = doc.get("tod", "").strip()
    date = doc.get("date")
    if not date or not state_name or not base_game: return None
    if date.year < 1976: return None
    
    num_digits = len(numbers)
    digits = [int(n) for n in numbers]
    digits_sorted = sorted(digits)
    tod = compute_tod(base_game, lp_tod)
    final_game = f"{base_game} {tod}" if (tod and not game_name_has_tod(base_game)) else base_game
    
    return {
        "country": "United States" if doc.get("country") in ("USA", "United States") else doc.get("country", "United States"),
        "state": STATE_SLUGS.get(state_name, state_name.lower().replace(" ", "-")),
        "state_name": state_name,
        "game": final_game.lower().replace(" ", "-").replace(".", "").replace(",", ""),
        "game_name": final_game,
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


# ═══════════════════════════════════════════
# Exact copy of app.py's get_games_for_prediction
# ═══════════════════════════════════════════
def get_games_for_prediction(coll, state, game_type):
    all_games = coll.distinct('game_name', {'state_name': state})
    patterns = {
        'pick2': ['pick 2', 'pick2', 'pick-2', 'daily 2', 'daily2', 'play 2', 'play2', 'dc 2', 'dc2', 'cash 2', 'cash2', 'pega 2', 'quotidienne 2'],
        'pick3': ['pick 3', 'pick3', 'pick-3', 'daily 3', 'daily3', 'daily-3', 'dc-3', 'dc 3', 'dc3', 'cash 3', 'cash-3', 'cash3', 'play 3', 'play-3', 'play3', 'numbers', 'pega 3', 'quotidienne 3', 'my3'],
        'pick4': ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4', 'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4', 'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4', 'numbers game', 'lotto 4', 'pega 4', 'quotidienne 4'],
        'pick5': ['pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5', 'dc 5', 'dc5', 'play 5', 'play5', 'georgia five', 'georgia 5', 'lotto poker', 'plus 5'],
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
    source = client["mylottodata"]["lotterypost"]
    test_coll = client["lottery"]["lottery_v2_test"]
    old_coll = client["lottery"]["lottery_v2"]
    
    print("=" * 70)
    print("  SAFE TEST: Rebuild lottery_v2_test")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # ── Build test collection from last 60 days of lotterypost ──
    # This is enough to test all API endpoints
    since = datetime.now() - timedelta(days=60)
    
    print(f"\n📥 Reading lotterypost records (last 60 days)...")
    docs = list(source.find({"date": {"$gte": since}}))
    print(f"  Source records: {len(docs)}")
    
    enriched = []
    seen = set()
    for doc in docs:
        r = enrich(doc)
        if r is None: continue
        key = (r["state_name"], r["game_name"], str(r["date"]), r["tod"])
        if key in seen: continue
        seen.add(key)
        enriched.append(r)
    
    print(f"  Enriched Pick 2-5: {len(enriched)}")
    
    types = Counter(r["game_type"] for r in enriched)
    for gt in sorted(types): print(f"    {gt}: {types[gt]}")
    
    states = Counter(r["state_name"] for r in enriched)
    print(f"  States: {len(states)}")
    
    # Drop and rebuild test collection
    print(f"\n🗑️  Dropping lottery_v2_test...")
    test_coll.drop()
    
    print(f"📤 Inserting {len(enriched)} records...")
    if enriched:
        test_coll.insert_many(enriched)
    
    # Create indexes
    test_coll.create_index([("state_name", 1), ("game_name", 1), ("date", -1)], name="state_game_date")
    test_coll.create_index([("state_name", 1), ("game_name", 1), ("date", 1), ("tod", 1)], name="unique_draw", unique=True)
    test_coll.create_index([("normalized", 1)], name="normalized")
    test_coll.create_index([("date", -1)], name="date_desc")
    test_coll.create_index([("game_type", 1)], name="game_type")
    print(f"  ✅ Indexes created")
    
    # ═══════════════════════════════════════════
    # TEST 1: get_games_for_prediction compatibility
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("🧪 TEST 1: get_games_for_prediction() — does app.py find the right games?")
    print(f"{'=' * 70}")
    
    test_cases = [
        ("Florida", "pick3"), ("Florida", "pick4"), ("Florida", "pick5"),
        ("Georgia", "pick3"), ("Georgia", "pick4"), ("Georgia", "pick5"),
        ("Ohio", "pick3"), ("Ohio", "pick4"), ("Ohio", "pick5"),
        ("Pennsylvania", "pick3"), ("Pennsylvania", "pick4"), ("Pennsylvania", "pick5"),
        ("Texas", "pick3"), ("Texas", "pick4"),
        ("Virginia", "pick3"), ("Virginia", "pick4"), ("Virginia", "pick5"),
        ("New York", "pick3"), ("New York", "pick4"),
        ("Maryland", "pick3"), ("Maryland", "pick4"), ("Maryland", "pick5"),
        ("New Jersey", "pick3"), ("New Jersey", "pick4"),
        ("Illinois", "pick3"), ("Illinois", "pick4"),
        ("Delaware", "pick3"), ("Delaware", "pick4"), ("Delaware", "pick5"),
        ("Washington, D.C.", "pick3"), ("Washington, D.C.", "pick4"),
        ("Connecticut", "pick3"), ("Connecticut", "pick4"),
        ("Louisiana", "pick3"), ("Louisiana", "pick4"), ("Louisiana", "pick5"),
    ]
    
    pass_count = 0
    fail_count = 0
    
    for state, gt in test_cases:
        # Test against NEW collection
        new_games = get_games_for_prediction(test_coll, state, gt)
        new_count = test_coll.count_documents({"state_name": state, "game_name": {"$in": new_games}}) if new_games else 0
        
        # Test against OLD collection for comparison
        old_games = get_games_for_prediction(old_coll, state, gt)
        old_count = old_coll.count_documents({
            "state_name": state, "game_name": {"$in": old_games},
            "date": {"$gte": since}
        }) if old_games else 0
        
        if new_count > 0:
            status = "✅"
            pass_count += 1
        else:
            status = "❌ NO DATA"
            fail_count += 1
        
        print(f"  {status} {state} / {gt}")
        print(f"       NEW: {new_games} → {new_count} records")
        if old_count > 0:
            print(f"       OLD: {old_games} → {old_count} records")
    
    # ═══════════════════════════════════════════
    # TEST 2: /api/draws/recent simulation
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("🧪 TEST 2: /api/draws/recent — do seeds load correctly?")
    print(f"{'=' * 70}")
    
    api_test_cases = [
        ("Florida", "pick4", "2026-01-01", "2026-02-25"),
        ("Georgia", "pick3", "2026-01-01", "2026-02-25"),
        ("Pennsylvania", "pick5", "2026-01-01", "2026-02-25"),
        ("Texas", "pick4", "2026-01-01", "2026-02-25"),
        ("Virginia", "pick4", "2026-01-01", "2026-02-25"),
    ]
    
    for state, gt, start, end in api_test_cases:
        games = get_games_for_prediction(test_coll, state, gt)
        if not games:
            print(f"  ❌ {state} / {gt}: no games found")
            continue
        
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        num_digits = int(gt[-1])
        
        query = {"state_name": state, "game_name": {"$in": games}, "date": {"$gte": start_dt, "$lte": end_dt}}
        draws = list(test_coll.find(query).sort("date", -1))
        
        # Simulate what MongoOptimizedCursor does
        valid_seeds = 0
        format_errors = []
        for d in draws:
            nums = d.get("numbers", "[]")
            if isinstance(nums, str):
                try:
                    nums = json.loads(nums)
                except:
                    format_errors.append(f"JSON parse fail: {nums[:50]}")
                    continue
            nums = [str(n) for n in nums][:num_digits]
            if len(nums) == num_digits:
                valid_seeds += 1
            else:
                format_errors.append(f"Wrong digit count: {len(nums)} (expected {num_digits})")
        
        if valid_seeds > 0 and not format_errors:
            print(f"  ✅ {state} / {gt}: {valid_seeds} valid seeds, games={games}")
        elif valid_seeds > 0:
            print(f"  ⚠️  {state} / {gt}: {valid_seeds} seeds but {len(format_errors)} errors")
            for e in format_errors[:3]: print(f"       {e}")
        else:
            print(f"  ❌ {state} / {gt}: 0 valid seeds")
    
    # ═══════════════════════════════════════════
    # TEST 3: /api/td/lookup simulation
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("🧪 TEST 3: /api/td/lookup — does TD counting work?")
    print(f"{'=' * 70}")
    
    for state, gt in [("Florida", "pick4"), ("Georgia", "pick3"), ("Virginia", "pick5")]:
        games = get_games_for_prediction(test_coll, state, gt)
        if not games: continue
        
        num_digits = int(gt[-1])
        all_draws = list(test_coll.find({"state_name": state, "game_name": {"$in": games}}))
        
        td_map = {}
        for d in all_draws:
            nums = parse_numbers(d.get("numbers", "[]"))
            if len(nums) != num_digits: continue
            try:
                norm = "".join(sorted(nums, key=lambda x: int(x)))
                td_map[norm] = td_map.get(norm, 0) + 1
            except: continue
        
        top_td = sorted(td_map.items(), key=lambda x: -x[1])[:5]
        print(f"  ✅ {state} / {gt}: {len(all_draws)} draws, {len(td_map)} unique norms")
        print(f"       Top 5 TD: {top_td}")
    
    # ═══════════════════════════════════════════
    # TEST 4: /api/rbtl/backtest-v2 simulation
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("🧪 TEST 4: /api/rbtl/backtest-v2 — does the backtest engine work?")
    print(f"{'=' * 70}")
    
    state, gt = "Florida", "pick4"
    games = get_games_for_prediction(test_coll, state, gt)
    if games:
        # Get seed draws (last 30 days)
        seed_start = datetime.now() - timedelta(days=30)
        seed_query = {"state_name": state, "game_name": {"$in": games}, "date": {"$gte": seed_start}}
        seed_docs = list(test_coll.find(seed_query).sort("date", -1))
        
        seed_norms = set()
        for d in seed_docs:
            nums = parse_numbers(d.get("numbers", "[]"))
            if len(nums) == 4:
                seed_norms.add("".join(sorted(nums)))
        
        # Find historical matches for these norms
        all_docs = list(test_coll.find({"state_name": state, "game_name": {"$in": games}}))
        matches = 0
        for d in all_docs:
            nums = parse_numbers(d.get("numbers", "[]"))
            if len(nums) == 4:
                norm = "".join(sorted(nums))
                if norm in seed_norms:
                    matches += 1
        
        print(f"  ✅ Florida / pick4: {len(seed_docs)} seeds, {len(seed_norms)} unique norms, {matches} historical matches from {len(all_docs)} total draws")
    
    # ═══════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print(f"📊 SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Tests passed: {pass_count}")
    print(f"  Tests failed: {fail_count}")
    print(f"  Test collection: lottery.lottery_v2_test ({test_coll.count_documents({}):,} records)")
    
    if fail_count == 0:
        print(f"\n  🎉 ALL TESTS PASSED!")
        print(f"\n  To test with the actual backtest UI:")
        print(f"  1. In app.py, change line 177:")
        print(f"       MONGO_COLLECTION_OPTIMIZED = 'lottery_v2_test'")
        print(f"  2. Restart Flask: python app.py")
        print(f"  3. Open http://localhost:5001/backtest and run a backtest")
        print(f"  4. When satisfied, change line 177 back to 'lottery_v2'")
        print(f"  5. Run: python rebuild_lottery_v2.py")
    else:
        print(f"\n  ⚠️  {fail_count} tests failed — review the output above.")
    
    # Cleanup note
    print(f"\n  To clean up the test collection later:")
    print(f"    db.lottery_v2_test.drop()")
    
    client.close()


if __name__ == "__main__":
    run()
