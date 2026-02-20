#!/usr/bin/env python3
"""
Show all 2019 Midday → Evening 2DP matches

For each day in 2019, show:
- Midday draw
- Evening draw  
- 2DP overlap (if any)
"""

import requests
from itertools import combinations
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

print("="*80)
print("2019 MIDDAY → EVENING 2DP ANALYSIS")
print("="*80)
print()
print("Fetching data...")
print("-"*80)

results = []
start_time = time.time()

current_date = datetime.strptime(START_DATE, "%Y-%m-%d")
end_date = datetime.strptime(END_DATE, "%Y-%m-%d")
total_days = (end_date - current_date).days + 1
processed = 0

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
            midday_2dp = get_2dp_pairs(midday_actual)
            evening_2dp = get_2dp_pairs(evening_actual)
            overlap = midday_2dp & evening_2dp
            
            results.append({
                'date': date_str,
                'midday_value': midday_value,
                'midday_actual': midday_actual,
                'evening_value': evening_value,
                'evening_actual': evening_actual,
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
print("="*80)
print(f"{'Date':<12} {'Midday':<8} {'(sorted)':<8} {'Evening':<8} {'(sorted)':<8} {'2DP Overlap':<20} {'Match'}")
print("="*80)

matches = 0
for r in results:
    overlap_str = ','.join(sorted(r['overlap'])) if r['overlap'] else '-'
    match_str = '✅' if r['has_match'] else '❌'
    if r['has_match']:
        matches += 1
    
    print(f"{r['date']:<12} {r['midday_value']:<8} {r['midday_actual']:<8} {r['evening_value']:<8} {r['evening_actual']:<8} {overlap_str:<20} {match_str}")

print()
print("="*80)
print("SUMMARY")
print("="*80)
print(f"Total days: {len(results)}")
print(f"Days with 2DP match: {matches}")
print(f"Days without match: {len(results) - matches}")
print(f"Match rate: {matches/len(results)*100:.1f}%")
print()

# Show misses
print("="*80)
print("MISSES (No 2DP overlap)")
print("="*80)
for r in results:
    if not r['has_match']:
        print(f"{r['date']}: Midday={r['midday_value']}({r['midday_actual']}) → Evening={r['evening_value']}({r['evening_actual']})")
        print(f"           Midday 2DP:  {sorted(r['midday_2dp'])}")
        print(f"           Evening 2DP: {sorted(r['evening_2dp'])}")
        print()
