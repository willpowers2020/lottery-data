#!/usr/bin/env python3
"""
RBTL Algorithm Test for Sept 15, 2019 Evening

Algorithm:
1. JOP: Midday 9/15 + 5 days back (9/10-9/14) -> extract 2DP pairs
2. HOT 2DPs: Find most common 2DP pairs across seeds
3. Find Hot Months: months where 2+ seeds appeared historically
4. Get Candidates: ALL numbers from hot months that share 2DP with seeds (EXCLUDE seeds)
5. Rank by RBTL: frequency (how many times candidate repeated across hot months)

Usage: python3 rbtl_test_20190915.py
"""

import requests
from itertools import combinations
from collections import defaultdict, Counter
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5001"
STATE = "Florida"
GAME_TYPE = "pick4"
TARGET_DATE = "2019-09-15"
TARGET_TOD = "evening"
LOOKBACK_DAYS = 5
MIN_SEEDS_FOR_HOT = 2

def get_2dp_pairs(num):
    """Get all 2-digit pairs from a 4-digit number (sorted)"""
    return set([''.join(sorted(p)) for p in combinations(str(num).zfill(4), 2)])

print("="*70)
print("RBTL ALGORITHM TEST - Sept 15, 2019 Evening")
print("="*70)
print()

# ============================================================
# Use the RBTL backtest endpoint to get all the data we need
# ============================================================
print("Fetching data from RBTL backtest API...")
print("-"*70)

resp = requests.post(f"{BASE_URL}/api/rbtl/backtest", json={
    "state": STATE,
    "game_type": GAME_TYPE,
    "target_date": TARGET_DATE,
    "target_tod": TARGET_TOD,
    "include_same_day": True,
    "lookback_days": LOOKBACK_DAYS,
    "dp_size": 2,
    "min_seeds_for_hot": MIN_SEEDS_FOR_HOT,
    "max_hot_months": 0  # No limit
})

if resp.status_code != 200:
    print(f"Error: {resp.status_code}")
    print(resp.text)
    exit(1)

data = resp.json()

# ============================================================
# STEP 1: JOP (Seeds)
# ============================================================
print()
print("STEP 1: JOP (Jump-off-point)")
print("-"*70)

seed_perms = data.get('seed_perms', [])
seed_set = set(seed_perms)  # For fast lookup
print(f"Seeds ({len(seed_perms)}): {seed_perms}")
print()

# Get all 2DP pairs from seeds
all_seed_2dp = set()
for seed in seed_perms:
    all_seed_2dp.update(get_2dp_pairs(seed))

print(f"Seed 2DP pairs ({len(all_seed_2dp)}): {sorted(all_seed_2dp)}")
print()

# ============================================================
# STEP 2: HOT 2DPs (Most common pairs across seeds)
# ============================================================
print("STEP 2: HOT 2DPs (Most common pairs across seeds)")
print("-"*70)

# Count how many seeds each 2DP appears in
pair_seed_count = Counter()
pair_to_seeds = defaultdict(list)

for seed in seed_perms:
    seed_pairs = get_2dp_pairs(seed)
    for pair in seed_pairs:
        pair_seed_count[pair] += 1
        pair_to_seeds[pair].append(seed)

# Rank by frequency
hot_2dps = pair_seed_count.most_common()

print(f"{'2DP':<6} {'Count':<6} {'Seeds with this pair'}")
print("-"*50)
for pair, count in hot_2dps[:15]:
    seeds_with_pair = pair_to_seeds[pair]
    print(f"{pair:<6} {count:<6} {seeds_with_pair}")

print()
print(f"Hottest 2DPs (appear in 3+ seeds): ", end="")
hottest = [p for p, c in hot_2dps if c >= 3]
print(hottest if hottest else "None")
print()

# ============================================================
# STEP 3: Hot Months
# ============================================================
print("STEP 3: Hot Months (months where 2+ seeds appeared)")
print("-"*70)

hot_months = data.get('hot_months', [])
print(f"Hot months found: {len(hot_months)}")
print()
print("Top 20 hot months:")
for i, hm in enumerate(hot_months[:20]):
    print(f"  {hm['month']}: {hm['unique_seeds']} seeds - {hm['seeds']}")
print()

# ============================================================
# STEP 4: Get Candidates (filtered by 2DP, EXCLUDE seeds)
# ============================================================
print("STEP 4: Get Candidates from Hot Months (filtered by 2DP, EXCLUDING seeds)")
print("-"*70)

# Get all candidate details
all_details = data.get('hot_month_candidate_details', [])
print(f"Total candidate appearances from hot months: {len(all_details)}")

# Group by candidate and filter by 2DP match
candidate_appearances = defaultdict(list)
for detail in all_details:
    candidate_appearances[detail['actual']].append(detail)

print(f"Total unique candidates: {len(candidate_appearances)}")

# Filter to only candidates that:
# 1. Share 2DP with seeds
# 2. Are NOT already a seed
filtered_candidates = {}
excluded_seeds = []

for candidate, appearances in candidate_appearances.items():
    # EXCLUDE if candidate is already a seed
    if candidate in seed_set:
        excluded_seeds.append(candidate)
        continue
    
    cand_2dp = get_2dp_pairs(candidate)
    shared_2dp = cand_2dp & all_seed_2dp
    
    if shared_2dp:  # Has at least 1 2DP match
        unique_months = set(a['month'] for a in appearances)
        filtered_candidates[candidate] = {
            'appearances': appearances,
            'frequency': len(appearances),
            'shared_2dp': shared_2dp,
            'unique_months': len(unique_months),
            'months_list': sorted(unique_months)
        }

print(f"Excluded (already seeds): {len(excluded_seeds)} -> {excluded_seeds}")
print(f"Candidates after 2DP filter (excl seeds): {len(filtered_candidates)}")

# ============================================================
# STEP 4b: Filter by HOT 2DPs only (pairs in 3+ seeds)
# ============================================================
hot_2dp_set = set(p for p, c in hot_2dps if c >= 3)
print()
print(f"STEP 4b: Filter by HOT 2DPs only")
print(f"  HOT 2DPs (in 3+ seeds): {sorted(hot_2dp_set)}")

filtered_by_hot_2dp = {}
for candidate, info in filtered_candidates.items():
    # Check if candidate has at least 1 HOT 2DP
    hot_matches = info['shared_2dp'] & hot_2dp_set
    if hot_matches:
        filtered_by_hot_2dp[candidate] = {
            **info,
            'hot_2dp_matches': hot_matches
        }

print(f"  Candidates after HOT 2DP filter: {len(filtered_by_hot_2dp)}")
print()

# ============================================================
# STEP 5: Rank by RBTL (Frequency)
# ============================================================
print("STEP 5: Rank by RBTL (Repeat Frequency)")
print("-"*70)

# Sort by frequency descending, then by unique months, then by 2DP match count
ranked = sorted(
    filtered_candidates.items(),
    key=lambda x: (x[1]['frequency'], x[1]['unique_months'], len(x[1]['shared_2dp'])),
    reverse=True
)

# Find the actual winner
actual_winner = '6899'  # 9869 sorted

print(f"Target Evening Winner: {actual_winner} (9869)")
print()
print("="*70)
print("TOP 50 PREDICTIONS (seeds excluded)")
print("="*70)
print(f"{'Rank':<5} {'Cand':<6} {'Freq':<5} {'Months':<7} {'2DP Matches':<25} {'Appeared In'}")
print("-"*70)

winner_rank = None
for i, (cand, info) in enumerate(ranked[:50]):
    is_winner = " ✅ WINNER!" if cand == actual_winner else ""
    # Show all months, not just first 3
    months_str = ', '.join(info['months_list'][:5])
    if len(info['months_list']) > 5:
        months_str += f"... (+{len(info['months_list'])-5})"
    print(f"#{i+1:<4} {cand:<6} {info['frequency']:<5} {info['unique_months']:<7} {str(sorted(info['shared_2dp'])):<25} {months_str}{is_winner}")
    
    if cand == actual_winner:
        winner_rank = i + 1

print()
print("="*70)

# Find winner's rank if not in top 50
if winner_rank is None:
    for i, (cand, info) in enumerate(ranked):
        if cand == actual_winner:
            winner_rank = i + 1
            break

if winner_rank:
    winner_info = filtered_candidates[actual_winner]
    print(f"WINNER 6899 RANK: #{winner_rank} out of {len(ranked)}")
    print(f"  Frequency: {winner_info['frequency']}")
    print(f"  Unique months: {winner_info['unique_months']}")
    print(f"  2DP matches: {sorted(winner_info['shared_2dp'])}")
    print(f"  Appeared in months: {winner_info['months_list']}")
else:
    print(f"WINNER 6899 NOT FOUND IN CANDIDATES!")
    print(f"  6899 2DP pairs: {sorted(get_2dp_pairs(actual_winner))}")
    print(f"  Seed 2DP pairs: {sorted(all_seed_2dp)}")
    overlap = get_2dp_pairs(actual_winner) & all_seed_2dp
    print(f"  Overlap: {overlap}")
    if not overlap:
        print("  -> No 2DP overlap with seeds, so filtered out!")
    elif actual_winner in seed_set:
        print("  -> Winner is a seed itself, so excluded!")

# ============================================================
# STEP 6: TOP 50 with HOT 2DP filter
# ============================================================
print()
print()
print("="*70)
print("TOP 50 PREDICTIONS - HOT 2DP FILTER (only candidates with 59/45/89/29/49)")
print("="*70)

# Sort HOT 2DP filtered candidates
ranked_hot = sorted(
    filtered_by_hot_2dp.items(),
    key=lambda x: (x[1]['frequency'], x[1]['unique_months'], len(x[1]['hot_2dp_matches'])),
    reverse=True
)

print(f"{'Rank':<5} {'Cand':<6} {'Freq':<5} {'Months':<7} {'HOT 2DP':<15} {'All 2DP':<20} {'Appeared In'}")
print("-"*90)

winner_rank_hot = None
for i, (cand, info) in enumerate(ranked_hot[:50]):
    is_winner = " ✅ WINNER!" if cand == actual_winner else ""
    months_str = ', '.join(info['months_list'][:4])
    if len(info['months_list']) > 4:
        months_str += f"... (+{len(info['months_list'])-4})"
    hot_matches = sorted(info['hot_2dp_matches'])
    all_matches = sorted(info['shared_2dp'])
    print(f"#{i+1:<4} {cand:<6} {info['frequency']:<5} {info['unique_months']:<7} {str(hot_matches):<15} {str(all_matches):<20} {months_str}{is_winner}")
    
    if cand == actual_winner:
        winner_rank_hot = i + 1

print()
print("="*70)

# Find winner's rank in HOT 2DP list
if winner_rank_hot is None:
    for i, (cand, info) in enumerate(ranked_hot):
        if cand == actual_winner:
            winner_rank_hot = i + 1
            break

if winner_rank_hot:
    winner_info_hot = filtered_by_hot_2dp[actual_winner]
    print(f"WINNER 6899 RANK (HOT 2DP filter): #{winner_rank_hot} out of {len(ranked_hot)}")
    print(f"  HOT 2DP matches: {sorted(winner_info_hot['hot_2dp_matches'])}")
else:
    print(f"WINNER 6899 NOT IN HOT 2DP CANDIDATES!")
    winner_2dp = get_2dp_pairs(actual_winner)
    hot_overlap = winner_2dp & hot_2dp_set
    print(f"  6899 2DP pairs: {sorted(winner_2dp)}")
    print(f"  HOT 2DPs: {sorted(hot_2dp_set)}")
    print(f"  Overlap with HOT: {hot_overlap}")
    if not hot_overlap:
        print("  -> 6899 does NOT contain any HOT 2DPs (59/45/89/29/49)!")
