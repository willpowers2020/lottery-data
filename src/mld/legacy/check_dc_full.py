#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
  DC FULL DIAGNOSTIC + PATTERN GAP CHECK
═══════════════════════════════════════════════════════════════
"""
from pymongo import MongoClient
from datetime import datetime, timedelta
import json

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net"
client = MongoClient(MONGO_URL)

print("=" * 65)
print("  PART 1: WHERE IS DC IN LOTTERYPOST?")
print("=" * 65)

lp = client['mylottodata']['lotterypost']
# Search broadly
all_states = sorted(lp.distinct('state'))
dc_like = [s for s in all_states if 'wash' in s.lower() or 'dc' in s.lower() or 'd.c' in s.lower() or 'dist' in s.lower() or 'colum' in s.lower()]
print(f"\n  All states matching DC/Washington/District/Columbia: {dc_like}")

if not dc_like:
    # Maybe it's stored differently
    print("  Searching by game name instead...")
    all_games = lp.distinct('game')
    dc_games = [g for g in all_games if 'dc' in g.lower()]
    print(f"  Games with 'dc': {dc_games[:20]}")
    if dc_games:
        sample = lp.find_one({'game': dc_games[0]})
        print(f"  Sample record state field: '{sample.get('state', '???')}'")

# Try exact strings
for name in ['Washington, D.C.', 'Washington DC', 'Washington D.C.', 'District of Columbia', 'DC']:
    count = lp.count_documents({'state': name})
    if count > 0:
        print(f"  '{name}': {count} records")
        games = lp.distinct('game', {'state': name})
        p5 = [g for g in games if '5' in g or 'five' in g.lower()]
        print(f"    Pick5 games: {p5}")

print("\n" + "=" * 65)
print("  PART 2: DC DRAWS IN lottery_v2_test (Feb 25)")
print("=" * 65)

test = client['lottery']['lottery_v2_test']
dc_games_all = test.distinct('game_name', {'state_name': 'Washington, D.C.'})
print(f"\n  All DC games in test: {dc_games_all}")

feb25 = list(test.find({
    'state_name': 'Washington, D.C.',
    'date': datetime(2026, 2, 25)
}).sort([('game_name', 1), ('tod', 1)]))

print(f"  Feb 25 total DC draws: {len(feb25)}")
for d in feb25:
    nums = d.get('winning_numbers', d.get('numbers', '?'))
    print(f"    {d['game_name']:20s} tod={d.get('tod','?'):8s} nums={nums}")

print("\n" + "=" * 65)
print("  PART 3: PATTERN MATCHING GAP ANALYSIS")
print("=" * 65)

# Current patterns from app.py
patterns = {
    'pick2': ['pick 2', 'pick2', 'pick-2', 'daily 2', 'daily2', 'play 2', 'play2', 'dc 2', 'dc2', 'cash 2', 'cash2'],
    'pick3': ['pick 3', 'pick3', 'pick-3', 'daily 3', 'daily3', 'daily-3', 'dc-3', 'dc 3', 'dc3', 'cash 3', 'cash-3', 'cash3', 'play 3', 'play-3', 'play3'],
    'pick4': ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4', 'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4', 'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4'],
    'pick5': ['pick 5 day', 'pick 5 evening', 'pick 5 midday', 'play 5 day', 'play 5 night',
              'dc 5 evening', 'dc 5 midday', 'georgia five evening', 'georgia five midday',
              'pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5',
              'dc 5', 'dc5', 'dc-5',  # dc-5 = your new fix
              'play 5', 'play5', 'georgia five', 'georgia 5'],
}

# Check each game in test collection against patterns
all_games_test = test.distinct('game_name')
print(f"\n  All games in lottery_v2_test: {len(all_games_test)}")

for game_type, pats in patterns.items():
    matched = [g for g in all_games_test if any(p in g.lower() for p in pats)]
    unmatched_candidates = [g for g in all_games_test 
                            if game_type[-1] in g  # has the right digit
                            and g not in matched
                            and not any(g in m for m in matched)]
    if unmatched_candidates:
        # Filter to likely matches
        digit = game_type[-1]
        real_unmatched = [g for g in unmatched_candidates 
                          if f'-{digit}' in g or f' {digit}' in g or g.endswith(digit)]
        if real_unmatched:
            print(f"\n  ⚠️  {game_type}: These games DON'T match current patterns:")
            for g in real_unmatched:
                count = test.count_documents({'game_name': g})
                print(f"      '{g}' ({count} records)")

# Specifically check DC pick2 (missing dc-2 pattern)
dc_p2 = [g for g in dc_games_all if '2' in g]
print(f"\n  DC Pick 2 games: {dc_p2}")
for g in dc_p2:
    matched = any(p in g.lower() for p in patterns['pick2'])
    print(f"    '{g}' matches pick2 patterns: {'✅' if matched else '❌'}")

print("\n" + "=" * 65)
print("  PART 4: RECOMMENDED PATTERN FIXES")
print("=" * 65)

# Check what's missing
missing_fixes = []
if not any('dc-2' in p for p in patterns['pick2']):
    missing_fixes.append("pick2: add 'dc-2'")
if not any('dc-5' in p for p in patterns['pick5']):
    missing_fixes.append("pick5: add 'dc-5' (already done!)")

# Check for 11:30pm games (DC-3 and DC-4 have these)
dc_1130 = [g for g in dc_games_all if '11:30' in g]
if dc_1130:
    print(f"\n  Note: DC has late-night games: {dc_1130}")
    print(f"  These will match via 'dc-3'/'dc-4' substring patterns ✅")

if missing_fixes:
    print(f"\n  Fixes needed:")
    for f in missing_fixes:
        print(f"    → {f}")
else:
    print(f"\n  ✅ All patterns look good!")

print(f"\n  sed command for pick2 dc-2 fix:")
print(f"    sed -i '' \"s/'dc 2', 'dc2',/'dc 2', 'dc2', 'dc-2',/\" app.py")
