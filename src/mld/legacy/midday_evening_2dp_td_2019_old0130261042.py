#!/usr/bin/env python3
"""
Show all 2019 Midday → Evening 2DP matches with Times Drawn (TD)

For each day in 2019, show:
- Midday draw + TD (how many times it appeared historically)
- Evening draw + TD
- 2DP overlap (if any)
"""

import requests
from itertools import combinations
from collections import defaultdict
from datetime import datetime, timedelta
import time

# Configuration
BASE_URL = "http://localhost:5001"
STATE = "Florida"
GAME_TYPE = "pick4"
START_DATE = "2019-01-01"
END_DATE = "2019-12-31"

def get_2dp_pairs(num):
    """Get all 2-digit pairs from a 4-digit number (sorted)"""
    return set([''.join(sorted(p)) for p in combinations(str(num).zfill(4), 2)])

print("="*100)
print("2019 MIDDAY → EVENING 2DP ANALYSIS WITH TIMES DRAWN (TD)")
print("="*100)
print()

# ============================================================
# STEP 1: Build historical TD lookup (all draws before 2019)
# ============================================================
print("Step 1: Building historical TD lookup (pre-2019)...")

resp = requests.post(f"{BASE_URL}/api/rbtl/backtest", json={
    "state": STATE,
    "game_type": GAME_TYPE,
    "target_date": "2019-01-01",
    "target_tod": "midday",
    "include_same_day": False,
    "lookback_days": 10000,  # Get all history
    "dp_size": 2,
    "min_seeds_for_hot": 1,
    "max_hot_months": 0
}, timeout=60)

data = resp.json()
all_details = data.get('hot_month_candidate_details', [])

# Count historical occurrences (before 2019)
historical_td = defaultdict(int)
for detail in all_details:
    if detail['date'] < '2019-01-01':
        historical_td[detail['actual']] += 1

print(f"  Loaded {len(historical_td)} unique numbers from history")
print()

# ============================================================
# STEP 2: Fetch 2019 data
# ============================================================
print("Step 2: Fetching 2019 Midday/Evening data...")
print("-"*100)

results = []
start_time = time.time()

current_date = datetime.strptime(START_DATE, "%Y-%m-%d")
end_date = datetime.strptime(END_DATE, "%Y-%m-%d")
total_days = (end_date - current_date).days + 1
processed = 0

# Also track TD as we go through 2019 (cumulative)
running_td = historical_td.copy()

while current_date <= end_date:
    date_str = current_date.strftime("%Y-%m-%d")
    processed += 1
    
    if processed % 50 == 0:
        elapsed = time.time() - start_time
        print(f"  Processing {date_str}... ({processed}/{total_days})")
    
    try:
        # Get Midday
        resp_midday = requests.post(f"{BASE_URL}/api/rbtl/backtest", json={
            "state": STATE,
            "game_type": GAME_TYPE,
            "target_date": date_str,
            "target_tod": "midday",
            "include_same_day": False,
            "lookback_days": 1,
            "dp_size": 2,
            "min_seeds_for_hot": 2,
            "max_hot_months": 0
        }, timeout=30)
        
        if resp_midday.status_code != 200:
            current_date += timedelta(days=1)
            continue
        
        data_midday = resp_midday.json()
        midday_winners = data_midday.get('target_winners', [])
        
        midday_actual = None
        midday_value = None
        for w in midday_winners:
            if w.get('tod', '').lower() == 'midday':
                midday_actual = w.get('actual')
                midday_value = w.get('value')
                break
        
        # Get Evening
        resp_evening = requests.post(f"{BASE_URL}/api/rbtl/backtest", json={
            "state": STATE,
            "game_type": GAME_TYPE,
            "target_date": date_str,
            "target_tod": "evening",
            "include_same_day": False,
            "lookback_days": 1,
            "dp_size": 2,
            "min_seeds_for_hot": 2,
            "max_hot_months": 0
        }, timeout=30)
        
        if resp_evening.status_code != 200:
            current_date += timedelta(days=1)
            continue
        
        data_evening = resp_evening.json()
        evening_winners = data_evening.get('target_winners', [])
        
        evening_actual = None
        evening_value = None
        for w in evening_winners:
            if w.get('tod', '').lower() == 'evening':
                evening_actual = w.get('actual')
                evening_value = w.get('value')
                break
        
        if midday_actual and evening_actual:
            # Get TD BEFORE this draw (what we would have known)
            midday_td = running_td[midday_actual]
            
            # Update running TD with midday
            running_td[midday_actual] += 1
            
            # Get evening TD (after midday added)
            evening_td = running_td[evening_actual]
            
            # Update running TD with evening
            running_td[evening_actual] += 1
            
            midday_2dp = get_2dp_pairs(midday_actual)
            evening_2dp = get_2dp_pairs(evening_actual)
            overlap = midday_2dp & evening_2dp
            
            results.append({
                'date': date_str,
                'midday_value': midday_value,
                'midday_actual': midday_actual,
                'midday_td': midday_td,
                'evening_value': evening_value,
                'evening_actual': evening_actual,
                'evening_td': evening_td,
                'midday_2dp': midday_2dp,
                'evening_2dp': evening_2dp,
                'overlap': overlap,
                'has_match': len(overlap) > 0
            })
        
    except Exception as e:
        print(f"  Error on {date_str}: {e}")
    
    current_date += timedelta(days=1)

elapsed = time.time() - start_time
print()
print(f"Completed in {elapsed:.1f} seconds")
print()

# ============================================================
# SHOW ALL RESULTS
# ============================================================
print("="*100)
print(f"{'Date':<12} {'Midday':<7} {'Sorted':<7} {'TD':<4} {'Evening':<8} {'Sorted':<7} {'TD':<4} {'2DP Overlap':<15} {'Match'}")
print("="*100)

matches = 0
for r in results:
    overlap_str = ','.join(sorted(r['overlap'])) if r['overlap'] else '-'
    match_str = '✅' if r['has_match'] else '❌'
    if r['has_match']:
        matches += 1
    
    print(f"{r['date']:<12} {r['midday_value']:<7} {r['midday_actual']:<7} {r['midday_td']:<4} {r['evening_value']:<8} {r['evening_actual']:<7} {r['evening_td']:<4} {overlap_str:<15} {match_str}")

print()
print("="*100)
print("SUMMARY")
print("="*100)
print(f"Total days: {len(results)}")
print(f"Days with 2DP match: {matches}")
print(f"Days without match: {len(results) - matches}")
print(f"Match rate: {matches/len(results)*100:.1f}%")
print()

# ============================================================
# TD ANALYSIS
# ============================================================
print("="*100)
print("TD (TIMES DRAWN) ANALYSIS")
print("="*100)
print()

# Analyze TD patterns
midday_tds = [r['midday_td'] for r in results]
evening_tds = [r['evening_td'] for r in results]

print(f"Midday TD stats:")
print(f"  Min: {min(midday_tds)}, Max: {max(midday_tds)}, Avg: {sum(midday_tds)/len(midday_tds):.1f}")
print()
print(f"Evening TD stats:")
print(f"  Min: {min(evening_tds)}, Max: {max(evening_tds)}, Avg: {sum(evening_tds)/len(evening_tds):.1f}")
print()

# TD buckets
print("Evening winner TD distribution:")
td_buckets = {'0': 0, '1-5': 0, '6-10': 0, '11-20': 0, '21-50': 0, '51+': 0}
for td in evening_tds:
    if td == 0:
        td_buckets['0'] += 1
    elif td <= 5:
        td_buckets['1-5'] += 1
    elif td <= 10:
        td_buckets['6-10'] += 1
    elif td <= 20:
        td_buckets['11-20'] += 1
    elif td <= 50:
        td_buckets['21-50'] += 1
    else:
        td_buckets['51+'] += 1

for bucket, count in td_buckets.items():
    pct = count / len(evening_tds) * 100
    bar = '█' * int(pct / 2)
    print(f"  TD {bucket:>5}: {count:>3} ({pct:>5.1f}%) {bar}")

print()

# ============================================================
# CREATIVE 2DP ANALYSIS
# ============================================================
print("="*100)
print("CREATIVE 2DP PATTERNS")
print("="*100)
print()

# 1. Which 2DPs from Midday most often appear in Evening?
print("1. PREDICTIVE 2DPs: Which Midday 2DPs most often appear in Evening winner?")
print("-"*50)

pair_success = defaultdict(lambda: {'total': 0, 'hit': 0})
for r in results:
    for pair in r['midday_2dp']:
        pair_success[pair]['total'] += 1
        if pair in r['overlap']:
            pair_success[pair]['hit'] += 1

# Sort by hit rate
pair_stats = []
for pair, stats in pair_success.items():
    if stats['total'] >= 10:  # Minimum appearances
        hit_rate = stats['hit'] / stats['total'] * 100
        pair_stats.append((pair, stats['hit'], stats['total'], hit_rate))

pair_stats.sort(key=lambda x: x[3], reverse=True)

print(f"{'2DP':<6} {'Hits':<6} {'Total':<6} {'Hit Rate':<10}")
print("-"*30)
for pair, hits, total, rate in pair_stats[:20]:
    print(f"{pair:<6} {hits:<6} {total:<6} {rate:.1f}%")

print()

# 2. TD correlation with 2DP match
print("2. TD CORRELATION: Do high-TD middays predict better?")
print("-"*50)

low_td_match = sum(1 for r in results if r['midday_td'] <= 10 and r['has_match'])
low_td_total = sum(1 for r in results if r['midday_td'] <= 10)

high_td_match = sum(1 for r in results if r['midday_td'] > 10 and r['has_match'])
high_td_total = sum(1 for r in results if r['midday_td'] > 10)

print(f"Midday TD ≤ 10: {low_td_match}/{low_td_total} = {low_td_match/low_td_total*100:.1f}% match rate")
print(f"Midday TD > 10: {high_td_match}/{high_td_total} = {high_td_match/high_td_total*100:.1f}% match rate")
print()

# 3. Consecutive 2DP patterns
print("3. CONSECUTIVE PATTERNS: When 2DP matches, does it repeat next day?")
print("-"*50)

consecutive_match = 0
after_match_total = 0
for i in range(len(results) - 1):
    if results[i]['has_match']:
        after_match_total += 1
        if results[i+1]['has_match']:
            consecutive_match += 1

print(f"After a match day, next day also matches: {consecutive_match}/{after_match_total} = {consecutive_match/after_match_total*100:.1f}%")
print()

# 4. Show misses
print("="*100)
print("MISSES (No 2DP overlap) - First 20")
print("="*100)
miss_count = 0
for r in results:
    if not r['has_match']:
        miss_count += 1
        if miss_count <= 20:
            print(f"{r['date']}: Midday={r['midday_value']}({r['midday_actual']}) TD={r['midday_td']} → Evening={r['evening_value']}({r['evening_actual']}) TD={r['evening_td']}")
            print(f"           Midday 2DP:  {sorted(r['midday_2dp'])}")
            print(f"           Evening 2DP: {sorted(r['evening_2dp'])}")
            print()
