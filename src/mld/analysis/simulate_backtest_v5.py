#!/usr/bin/env python3
"""
Simulate Backtest V5: "All States" Pick 5 for Feb 25, 2026
Uses actual Atlas MongoDB connection.
"""

from pymongo import MongoClient
from datetime import datetime
import json

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net"
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)

PICK5_PATTERNS = [
    'pick 5 day', 'pick 5 evening', 'pick 5 midday',
    'play 5 day', 'play 5 night',
    'dc 5 evening', 'dc 5 midday',
    'georgia five evening', 'georgia five midday',
    'pick 5', 'pick5', 'daily 5', 'daily5',
    'cash 5', 'cash5', 'dc 5', 'dc5',
    'play 5', 'play5', 'georgia five', 'georgia 5',
]

STATES_BUGGY = ['Maryland','Florida','Virginia','Delaware','Ohio','Pennsylvania','Georgia','Washington DC','Louisiana']
STATES_FIXED = ['Maryland','Florida','Virginia','Delaware','Ohio','Pennsylvania','Georgia','Washington, D.C.','Louisiana']

def get_games_for_prediction(collection, state):
    all_games = collection.distinct('game_name', {'state_name': state})
    matched = [g for g in all_games if any(p in g.lower() for p in PICK5_PATTERNS)]
    filtered = []
    for game in matched:
        gl = game.lower()
        is_parent = not any(tod in gl for tod in ['day','night','midday','evening'])
        if is_parent:
            has_child = any(g.lower().startswith(gl) and g.lower() != gl for g in matched)
            if has_child:
                continue
        filtered.append(game)
    return filtered if filtered else matched

def fetch_seeds(collection, state, start, end):
    games = get_games_for_prediction(collection, state)
    if not games:
        return [], games
    query = {'state_name': state, 'game_name': {'$in': games}, 'date': {'$gte': start, '$lte': end}}
    draws = list(collection.find(query).sort('date', -1))
    seeds = []
    for d in draws:
        nums = d.get('winning_numbers', d.get('numbers', []))
        if isinstance(nums, str):
            try: nums = json.loads(nums)
            except: nums = list(nums.replace(' ','').replace('-',''))
        nums = [str(n) for n in nums][:5]
        if len(nums) != 5:
            continue
        value = ''.join(nums)
        actual = ''.join(sorted(nums))
        tod = d.get('tod', d.get('draw_time', ''))
        if not tod:
            gn = d.get('game_name', '').lower()
            if 'midday' in gn or 'day' in gn: tod = 'Midday'
            elif 'evening' in gn or 'night' in gn: tod = 'Evening'
        seeds.append({'date': d['date'].strftime('%Y-%m-%d'), 'value': value, 'actual': actual, 'tod': tod, 'state': state, 'game': d.get('game_name','')})
    return seeds, games

def run_sim(coll_name, db_name, states, label):
    coll = client[db_name][coll_name]
    start = datetime(2026, 2, 25)
    end = datetime(2026, 2, 25)
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  Collection: {db_name}.{coll_name} | States: {len(states)}")
    print(f"{'='*70}")
    all_seeds = []
    for state in states:
        seeds, games = fetch_seeds(coll, state, start, end)
        m = "✅" if seeds else "❌"
        print(f"  {m} {state:25s} → {len(seeds)} draws | games: {games}")
        for s in seeds:
            print(f"      {s['date']} {s['tod'][:1] if s['tod'] else '?':2s} {s['value']}  norm:{s['actual']}  [{s['game']}]")
        all_seeds.extend(seeds)
    norms = sorted(set(s['actual'] for s in all_seeds))
    print(f"\n  TOTAL: {len(all_seeds)} draws, {len(norms)} unique normalized")
    print(f"  Normalized: {' '.join(norms)}")
    return all_seeds

print("="*70)
print("  BACKTEST V5 SIMULATION — Pick 5 All States, Feb 25")
print("="*70)

# Check what DC is stored as
for db_name, coll_name in [('lottery','lottery_v2'), ('lottery','lottery_v2_test')]:
    coll = client[db_name][coll_name]
    dc = [s for s in coll.distinct('state_name') if 'wash' in s.lower() or 'dc' in s.lower() or 'd.c' in s.lower()]
    print(f"  {db_name}.{coll_name}: DC stored as {dc}")

# Sim 1: Current bug — lottery_v2_test (what app uses) + "Washington DC"
s1 = run_sim('lottery_v2_test', 'lottery', STATES_BUGGY, "🔴 CURRENT BUG: lottery_v2_test + 'Washington DC'")

# Sim 2: DC fix — lottery_v2_test + "Washington, D.C."
s2 = run_sim('lottery_v2_test', 'lottery', STATES_FIXED, "🟢 DC FIX: lottery_v2_test + 'Washington, D.C.'")

# Sim 3: Old lottery_v2 + buggy name (for comparison)
s3 = run_sim('lottery_v2', 'lottery', STATES_BUGGY, "🟡 OLD DATA: lottery_v2 + 'Washington DC'")

print(f"\n{'='*70}")
print(f"  SUMMARY")
print(f"{'='*70}")
print(f"  Sim 1 (current bug):  {len(s1)} draws")
print(f"  Sim 2 (DC fixed):     {len(s2)} draws")
print(f"  Sim 3 (old data):     {len(s3)} draws")
if len(s2) > len(s1):
    print(f"  → DC fix adds {len(s2)-len(s1)} draws")
