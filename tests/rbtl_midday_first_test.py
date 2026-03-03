#!/usr/bin/env python3
"""
RBTL Midday-First Approach - Full Year Test

New Algorithm:
1. Get Midday 2DPs (6 pairs from midday draw)
2. Generate ALL 4-digit numbers containing each Midday 2DP
3. Filter to numbers that appeared in Hot Months (RBTL frequency)
4. Rank by frequency
5. Check if Evening winner is in Top N

Test: Full year 2019, Evening draws only
"""

import requests
from itertools import combinations, product
from collections import defaultdict
from datetime import datetime, timedelta
import time

# Configuration
BASE_URL = "http://localhost:5001"
STATE = "Florida"
GAME_TYPE = "pick4"
START_DATE = "2019-01-01"
END_DATE = "2019-12-31"
LOOKBACK_DAYS = 5
MIN_SEEDS_FOR_HOT = 2

def get_2dp_pairs(num):
    """Get all 2-digit pairs from a 4-digit number (sorted)"""
    return set([''.join(sorted(p)) for p in combinations(str(num).zfill(4), 2)])

def generate_numbers_with_pair(pair):
    """Generate all 4-digit sorted numbers containing a specific 2DP pair"""
    d1, d2 = pair[0], pair[1]
    numbers = set()
    
    # Generate all 4-digit combinations that include both digits
    for d3 in '0123456789':
        for d4 in '0123456789':
            digits = [d1, d2, d3, d4]
            sorted_num = ''.join(sorted(digits))
            numbers.add(sorted_num)
    
    return numbers

def sort_number(num):
    """Sort digits of a number"""
    return ''.join(sorted(str(num).zfill(4)))

print("="*70)
print("RBTL MIDDAY-FIRST APPROACH - FULL YEAR TEST 2019")
print("="*70)
print()
print("Algorithm:")
print("  1. Get Midday draw → extract 6 2DP pairs")
print("  2. Generate all numbers containing each Midday 2DP")
print("  3. Filter to numbers in Hot Months (from 5-day seeds)")
print("  4. Rank by RBTL frequency")
print("  5. Check if Evening winner is in Top N")
print()
print("Running... (this may take several minutes)")
print("-"*70)

# Track results
results = []
start_time = time.time()

# Iterate through each day of 2019
current_date = datetime.strptime(START_DATE, "%Y-%m-%d")
end_date = datetime.strptime(END_DATE, "%Y-%m-%d")
total_days = (end_date - current_date).days + 1
processed = 0

while current_date <= end_date:
    date_str = current_date.strftime("%Y-%m-%d")
    processed += 1
    
    if processed % 30 == 0:
        elapsed = time.time() - start_time
        print(f"  Processing {date_str}... ({processed}/{total_days}, {elapsed:.1f}s elapsed)")
    
    try:
        # STEP 1: Get Midday draw for this date
        # We need to call the API for Midday first
        resp_midday = requests.post(f"{BASE_URL}/api/rbtl/backtest", json={
            "state": STATE,
            "game_type": GAME_TYPE,
            "target_date": date_str,
            "target_tod": "midday",
            "include_same_day": False,
            "lookback_days": LOOKBACK_DAYS,
            "dp_size": 2,
            "min_seeds_for_hot": MIN_SEEDS_FOR_HOT,
            "max_hot_months": 0
        }, timeout=30)
        
        if resp_midday.status_code != 200:
            current_date += timedelta(days=1)
            continue
        
        data_midday = resp_midday.json()
        
        # Get Midday winner
        midday_winners = data_midday.get('target_winners', [])
        midday_seed = None
        for w in midday_winners:
            if w.get('tod', '').lower() == 'midday':
                midday_seed = w.get('actual')
                break
        
        if not midday_seed:
            current_date += timedelta(days=1)
            continue
        
        # STEP 2: Get Evening data (with Midday included as seed)
        resp = requests.post(f"{BASE_URL}/api/rbtl/backtest", json={
            "state": STATE,
            "game_type": GAME_TYPE,
            "target_date": date_str,
            "target_tod": "evening",
            "include_same_day": True,
            "lookback_days": LOOKBACK_DAYS,
            "dp_size": 2,
            "min_seeds_for_hot": MIN_SEEDS_FOR_HOT,
            "max_hot_months": 0
        }, timeout=30)
        
        if resp.status_code != 200:
            current_date += timedelta(days=1)
            continue
        
        data = resp.json()
        
        seed_perms = set(data.get('seed_perms', []))
        
        # Get Evening winner
        winners = data.get('target_winners', [])
        evening_winner = None
        for w in winners:
            if w.get('tod', '').lower() == 'evening':
                evening_winner = w.get('actual')
                break
        
        if not evening_winner:
            current_date += timedelta(days=1)
            continue
        
        # STEP 3: Get Midday 2DPs
        midday_2dps = get_2dp_pairs(midday_seed)
        
        # STEP 4: Generate all numbers containing Midday 2DPs
        midday_candidates = set()
        for pair in midday_2dps:
            midday_candidates.update(generate_numbers_with_pair(pair))
        
        # Remove seeds from candidates
        midday_candidates -= seed_perms
        
        # STEP 5: Get Hot Month candidates and their frequencies
        all_details = data.get('hot_month_candidate_details', [])
        
        # Count frequency for each candidate
        candidate_freq = defaultdict(int)
        candidate_months = defaultdict(set)
        for detail in all_details:
            cand = detail['actual']
            candidate_freq[cand] += 1
            candidate_months[cand].add(detail['month'])
        
        # STEP 6: Filter to Midday 2DP candidates that appear in Hot Months
        final_candidates = {}
        for cand in midday_candidates:
            if cand in candidate_freq:
                final_candidates[cand] = {
                    'frequency': candidate_freq[cand],
                    'unique_months': len(candidate_months[cand])
                }
        
        # Rank by frequency
        ranked = sorted(
            final_candidates.items(),
            key=lambda x: (x[1]['frequency'], x[1]['unique_months']),
            reverse=True
        )
        
        # Find winner rank
        winner_rank = None
        for i, (cand, info) in enumerate(ranked):
            if cand == evening_winner:
                winner_rank = i + 1
                break
        
        # Check if winner has Midday 2DP match
        winner_2dps = get_2dp_pairs(evening_winner)
        has_midday_match = bool(winner_2dps & midday_2dps)
        
        results.append({
            'date': date_str,
            'midday': midday_seed,
            'evening': evening_winner,
            'midday_2dps': midday_2dps,
            'has_midday_match': has_midday_match,
            'total_candidates': len(final_candidates),
            'winner_rank': winner_rank,
            'in_top_10': winner_rank is not None and winner_rank <= 10,
            'in_top_20': winner_rank is not None and winner_rank <= 20,
            'in_top_50': winner_rank is not None and winner_rank <= 50,
            'in_top_100': winner_rank is not None and winner_rank <= 100,
            'in_candidates': winner_rank is not None
        })
        
    except Exception as e:
        print(f"  Error on {date_str}: {e}")
    
    current_date += timedelta(days=1)

elapsed = time.time() - start_time
print()
print(f"Completed in {elapsed:.1f} seconds")
print()

# ============================================================
# RESULTS SUMMARY
# ============================================================
print("="*70)
print("RESULTS SUMMARY")
print("="*70)
print()

total = len(results)
if total == 0:
    print("No results collected! Check API connection.")
    exit(1)

has_midday_match = sum(1 for r in results if r['has_midday_match'])
in_candidates = sum(1 for r in results if r['in_candidates'])
in_top_10 = sum(1 for r in results if r['in_top_10'])
in_top_20 = sum(1 for r in results if r['in_top_20'])
in_top_50 = sum(1 for r in results if r['in_top_50'])
in_top_100 = sum(1 for r in results if r['in_top_100'])

print(f"Total Evening draws tested: {total}")
print()
print(f"Evening winner has Midday 2DP match: {has_midday_match}/{total} = {has_midday_match/total*100:.1f}%")
print(f"Evening winner in candidates (Midday 2DP + Hot Months): {in_candidates}/{total} = {in_candidates/total*100:.1f}%")
print()
print("HIT RATES:")
print(f"  Top 10:  {in_top_10}/{total} = {in_top_10/total*100:.1f}%")
print(f"  Top 20:  {in_top_20}/{total} = {in_top_20/total*100:.1f}%")
print(f"  Top 50:  {in_top_50}/{total} = {in_top_50/total*100:.1f}%")
print(f"  Top 100: {in_top_100}/{total} = {in_top_100/total*100:.1f}%")
print()

# Average candidate pool size
avg_candidates = sum(r['total_candidates'] for r in results) / total
print(f"Average candidate pool size: {avg_candidates:.0f}")
print()

# Show some examples
print("="*70)
print("SAMPLE HITS (Top 10)")
print("="*70)
hits = [r for r in results if r['in_top_10']][:10]
for r in hits:
    print(f"  {r['date']}: Midday={r['midday']} → Evening={r['evening']} (Rank #{r['winner_rank']}, Pool={r['total_candidates']})")

print()
print("="*70)
print("SAMPLE MISSES (not in candidates)")
print("="*70)
misses = [r for r in results if not r['in_candidates']][:10]
for r in misses:
    overlap = r['midday_2dps'] & get_2dp_pairs(r['evening'])
    print(f"  {r['date']}: Midday={r['midday']} → Evening={r['evening']}")
    print(f"           Midday 2DPs: {sorted(r['midday_2dps'])}")
    print(f"           Evening 2DPs: {sorted(get_2dp_pairs(r['evening']))}")
    print(f"           Overlap: {overlap if overlap else 'NONE'}")
    print()
