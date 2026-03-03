#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
  Simulate Backtest V5: "All States" Pick 5 for Feb 25, 2026
═══════════════════════════════════════════════════════════════════════

Replicates the exact flow:
1. /api/consecutive/states?game_type=pick5 → returns PICK5_STATES list
2. For each state: /api/draws/recent → get_games_for_prediction() → query
3. Collect all seeds

Tests against BOTH lottery_v2 (current) and lottery_v2_test (rebuilt)
"""

from pymongo import MongoClient
from datetime import datetime
import json

client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)

# ── Hardcoded lists from app.py and backtest_mockup_v5.html ──
PICK5_STATES_APP_PY = [
    'Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio',
    'Pennsylvania', 'Georgia', 'Washington DC', 'Louisiana', 'Germany'
]

PICK5_STATES_HTML = [
    'Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio',
    'Pennsylvania', 'Georgia', 'Washington DC', 'Louisiana'
]

# What the DB actually stores for DC
PICK5_STATES_FIXED = [
    'Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio',
    'Pennsylvania', 'Georgia', 'Washington, D.C.', 'Louisiana'
]

# ── Pick 5 patterns from get_games_for_prediction() ──
PICK5_PATTERNS = [
    'pick 5 day', 'pick 5 evening', 'pick 5 midday',
    'play 5 day', 'play 5 night',
    'dc 5 evening', 'dc 5 midday',
    'georgia five evening', 'georgia five midday',
    'pick 5', 'pick5',
    'daily 5', 'daily5',
    'cash 5', 'cash5',
    'dc 5', 'dc5',
    'play 5', 'play5',
    'georgia five', 'georgia 5',
]

def get_games_for_prediction(collection, state, game_type='pick5'):
    """Exact replica of app.py's get_games_for_prediction()"""
    all_games = collection.distinct('game_name', {'state_name': state})
    pats = PICK5_PATTERNS
    matched = [g for g in all_games if any(p in g.lower() for p in pats)]

    # Remove parent games if child TOD variants exist
    filtered = []
    for game in matched:
        game_lower = game.lower()
        is_parent = not any(tod in game_lower for tod in ['day', 'night', 'midday', 'evening'])
        if is_parent:
            has_child = any(
                g.lower().startswith(game_lower) and g.lower() != game_lower
                for g in matched
            )
            if has_child:
                continue
        filtered.append(game)

    return filtered if filtered else matched


def fetch_seeds_for_state(collection, state, start_date, end_date, num_digits=5):
    """Exact replica of /api/draws/recent for one state"""
    games = get_games_for_prediction(collection, state)
    if not games:
        return [], games, "NO GAMES FOUND"

    query = {
        'state_name': state,
        'game_name': {'$in': games},
        'date': {'$gte': start_date, '$lte': end_date}
    }

    all_draws = list(collection.find(query).sort('date', -1))
    seeds = []
    for d in all_draws:
        nums = d.get('winning_numbers', d.get('numbers', []))
        if isinstance(nums, str):
            try:
                nums = json.loads(nums)
            except (json.JSONDecodeError, ValueError):
                nums = list(nums.replace(' ', '').replace('-', ''))
        nums = [str(n) for n in nums][:num_digits]
        if len(nums) != num_digits:
            continue
        value = ''.join(nums)
        actual = ''.join(sorted(nums))
        tod = d.get('tod', d.get('draw_time', ''))
        if not tod:
            gn = d.get('game_name', '').lower()
            if 'midday' in gn or 'mid-day' in gn or 'day' in gn:
                tod = 'Midday'
            elif 'evening' in gn or 'eve' in gn or 'night' in gn:
                tod = 'Evening'
            else:
                tod = ''
        seeds.append({
            'date': d['date'].strftime('%Y-%m-%d'),
            'value': value,
            'actual': actual,
            'tod': tod,
            'state': state,
            'game': d.get('game_name', '')
        })
    return seeds, games, "OK"


def simulate_backtest(collection_name, states_list, label):
    """Simulate the full backtest v5 flow"""
    db = client['lottery']
    collection = db[collection_name]

    start_date = datetime(2026, 2, 25)
    end_date = datetime(2026, 2, 25)

    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"  Collection: lottery.{collection_name}")
    print(f"  States list: {states_list}")
    print(f"  Date: 2026-02-25")
    print(f"{'=' * 70}")

    total_seeds = []
    for state in states_list:
        seeds, games, status = fetch_seeds_for_state(collection, state, start_date, end_date)
        marker = "✅" if seeds else "❌"
        print(f"\n  {marker} {state}")
        print(f"     Games matched: {games if games else 'NONE'}")
        print(f"     Seeds found: {len(seeds)}")
        for s in seeds:
            print(f"       {s['date']} {s['tod'][:1] if s['tod'] else '?'} {s['value']}  (norm: {s['actual']})  [{s['game']}]")
        total_seeds.extend(seeds)

    norms = sorted(set(s['actual'] for s in total_seeds))
    print(f"\n  ────────────────────────────────────")
    print(f"  TOTAL: {len(total_seeds)} draws from {len([s for s in states_list if any(sd['state']==s for sd in total_seeds)])} states")
    print(f"  Unique normalized: {len(norms)}")
    print(f"  Normalized: {' '.join(norms)}")
    return total_seeds


# ═══════════════════════════════════════════════════════════════════
#  RUN SIMULATIONS
# ═══════════════════════════════════════════════════════════════════

print("=" * 70)
print("  BACKTEST V5 SIMULATION — Pick 5 All States, Feb 25, 2026")
print("=" * 70)

# Simulation 1: Current lottery_v2 with CURRENT buggy states list
print("\n\n🔴 SIMULATION 1: Current state (BEFORE fix)")
print("   lottery_v2 + 'Washington DC' in states list")
try:
    sim1 = simulate_backtest('lottery_v2', PICK5_STATES_HTML, 
                              "CURRENT: lottery_v2 + Washington DC")
except Exception as e:
    print(f"   ERROR: {e}")
    sim1 = []

# Simulation 2: Current lottery_v2 with FIXED states list
print("\n\n🟡 SIMULATION 2: After DC name fix only")
print("   lottery_v2 + 'Washington, D.C.' in states list")
try:
    sim2 = simulate_backtest('lottery_v2', PICK5_STATES_FIXED,
                              "FIX 1: lottery_v2 + Washington, D.C.")
except Exception as e:
    print(f"   ERROR: {e}")
    sim2 = []

# Simulation 3: Test collection with FIXED states list
print("\n\n🟢 SIMULATION 3: After full rebuild (test collection)")
print("   lottery_v2_test + 'Washington, D.C.' in states list")
try:
    sim3 = simulate_backtest('lottery_v2_test', PICK5_STATES_FIXED,
                              "FIX 2: lottery_v2_test + Washington, D.C.")
except Exception as e:
    print(f"   ERROR: {e}")
    sim3 = []

# ── Summary ──
print("\n\n" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"  Sim 1 (current bug):    {len(sim1)} draws")
print(f"  Sim 2 (DC name fix):    {len(sim2)} draws")
print(f"  Sim 3 (full rebuild):   {len(sim3)} draws")
print()
if len(sim1) == 15:
    print("  ✅ Sim 1 confirms the 15-draw bug you're seeing")
if len(sim2) > len(sim1):
    print(f"  ✅ DC fix alone adds {len(sim2) - len(sim1)} draws")
if len(sim3) > len(sim2):
    print(f"  ✅ Full rebuild adds {len(sim3) - len(sim2)} more draws")
print()

# ── Check what DC actually looks like in each collection ──
print("\n── DC State Name Check ──")
for coll_name in ['lottery_v2', 'lottery_v2_test']:
    coll = client['lottery'][coll_name]
    dc_variants = [
        s for s in coll.distinct('state_name')
        if 'wash' in s.lower() or 'dc' in s.lower() or 'd.c' in s.lower()
    ]
    print(f"  {coll_name}: DC stored as {dc_variants if dc_variants else 'NOT FOUND'}")
