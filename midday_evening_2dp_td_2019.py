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

# ============================================================
# ADVANCED CREATIVE 2DP ANALYSIS
# ============================================================
print()
print("="*100)
print("ADVANCED CREATIVE 2DP ANALYSIS")
print("="*100)

# ------------------------------------------------------------
# 5. 2DP CHAIN ANALYSIS
# If Midday has '89', find Evening numbers that have '89' AND another "hot" 2DP
# ------------------------------------------------------------
print()
print("5. 2DP CHAIN ANALYSIS")
print("   When 2DP matches, what OTHER 2DPs does the Evening winner have?")
print("-"*100)

# For each matching 2DP, track what other pairs appear with it in Evening
chain_analysis = defaultdict(lambda: defaultdict(int))

for r in results:
    if r['has_match']:
        for matching_pair in r['overlap']:
            # What other pairs does evening have?
            other_pairs = r['evening_2dp'] - {matching_pair}
            for other in other_pairs:
                chain_analysis[matching_pair][other] += 1

print(f"{'Matching 2DP':<15} {'Most Common Chain Partners (Evening also has...)'}")
print("-"*80)

# Show top chains for most common matching 2DPs
top_matching = sorted(pair_success.items(), key=lambda x: x[1]['hit'], reverse=True)[:10]
for pair, stats in top_matching:
    if stats['hit'] > 0:
        chains = chain_analysis[pair]
        top_chains = sorted(chains.items(), key=lambda x: x[1], reverse=True)[:5]
        chain_str = ', '.join([f"{p}({c})" for p, c in top_chains])
        print(f"{pair:<15} {chain_str}")

print()
print("   INSIGHT: Use this to narrow candidates - if Midday has '89',")
print("            prioritize Evening candidates with '89' + one of its common chain partners")
print()

# ------------------------------------------------------------
# 6. 2DP HEAT MAP - Track which 2DPs are "hot" this week/month
# ------------------------------------------------------------
print()
print("6. 2DP HEAT MAP - Weekly/Monthly hot 2DPs")
print("-"*100)

# Track 2DP appearances by month
monthly_2dp = defaultdict(lambda: defaultdict(int))

for r in results:
    month = r['date'][:7]  # YYYY-MM
    for pair in r['midday_2dp']:
        monthly_2dp[month][pair] += 1
    for pair in r['evening_2dp']:
        monthly_2dp[month][pair] += 1

print(f"{'Month':<10} {'Top 5 Hottest 2DPs (appeared most in Midday+Evening)'}")
print("-"*80)

for month in sorted(monthly_2dp.keys()):
    pairs = monthly_2dp[month]
    top5 = sorted(pairs.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_str = ', '.join([f"{p}({c})" for p, c in top5])
    print(f"{month:<10} {top5_str}")

print()

# Check if "hot" 2DPs from previous month predict next month
print("   Does last month's hottest 2DP appear in next month's winners?")
print("-"*50)

months = sorted(monthly_2dp.keys())
hot_carryover = 0
hot_total = 0

for i in range(len(months) - 1):
    prev_month = months[i]
    next_month = months[i + 1]
    
    # Get hottest 2DP from prev month
    hottest = sorted(monthly_2dp[prev_month].items(), key=lambda x: x[1], reverse=True)[0][0]
    
    # Check if it appeared in next month
    if hottest in monthly_2dp[next_month]:
        hot_carryover += 1
    hot_total += 1

print(f"   Hottest 2DP carries over to next month: {hot_carryover}/{hot_total} = {hot_carryover/hot_total*100:.1f}%")
print()

# ------------------------------------------------------------
# 7. 2DP + TD COMBO - Sweet spot analysis
# ------------------------------------------------------------
print()
print("7. 2DP + TD COMBO - Finding the 'sweet spot'")
print("-"*100)

# Analyze: When Evening winner has 2DP match, what's its TD distribution?
match_evening_tds = [r['evening_td'] for r in results if r['has_match']]
nomatch_evening_tds = [r['evening_td'] for r in results if not r['has_match']]

print("Evening winner TD when there IS a 2DP match:")
td_match_buckets = {'0': 0, '1-5': 0, '6-10': 0, '11-20': 0, '21-50': 0, '51+': 0}
for td in match_evening_tds:
    if td == 0:
        td_match_buckets['0'] += 1
    elif td <= 5:
        td_match_buckets['1-5'] += 1
    elif td <= 10:
        td_match_buckets['6-10'] += 1
    elif td <= 20:
        td_match_buckets['11-20'] += 1
    elif td <= 50:
        td_match_buckets['21-50'] += 1
    else:
        td_match_buckets['51+'] += 1

for bucket, count in td_match_buckets.items():
    if match_evening_tds:
        pct = count / len(match_evening_tds) * 100
        bar = '█' * int(pct / 2)
        print(f"  TD {bucket:>5}: {count:>3} ({pct:>5.1f}%) {bar}")

print()
print("Evening winner TD when there is NO 2DP match:")
td_nomatch_buckets = {'0': 0, '1-5': 0, '6-10': 0, '11-20': 0, '21-50': 0, '51+': 0}
for td in nomatch_evening_tds:
    if td == 0:
        td_nomatch_buckets['0'] += 1
    elif td <= 5:
        td_nomatch_buckets['1-5'] += 1
    elif td <= 10:
        td_nomatch_buckets['6-10'] += 1
    elif td <= 20:
        td_nomatch_buckets['11-20'] += 1
    elif td <= 50:
        td_nomatch_buckets['21-50'] += 1
    else:
        td_nomatch_buckets['51+'] += 1

for bucket, count in td_nomatch_buckets.items():
    if nomatch_evening_tds:
        pct = count / len(nomatch_evening_tds) * 100
        bar = '█' * int(pct / 2)
        print(f"  TD {bucket:>5}: {count:>3} ({pct:>5.1f}%) {bar}")

print()
print("   INSIGHT: The 'sweet spot' TD range for candidates")
print()

# ------------------------------------------------------------
# 8. 2DP VELOCITY - 2DPs appearing more frequently recently
# ------------------------------------------------------------
print()
print("8. 2DP VELOCITY - Which 2DPs are 'heating up'?")
print("-"*100)

# Compare first half vs second half of year
first_half = [r for r in results if r['date'] < '2019-07-01']
second_half = [r for r in results if r['date'] >= '2019-07-01']

first_half_2dp = defaultdict(int)
second_half_2dp = defaultdict(int)

for r in first_half:
    for pair in r['evening_2dp']:
        first_half_2dp[pair] += 1

for r in second_half:
    for pair in r['evening_2dp']:
        second_half_2dp[pair] += 1

# Calculate velocity (second half - first half)
velocity = {}
all_pairs = set(first_half_2dp.keys()) | set(second_half_2dp.keys())
for pair in all_pairs:
    h1 = first_half_2dp[pair]
    h2 = second_half_2dp[pair]
    velocity[pair] = h2 - h1

# Sort by velocity
heating_up = sorted(velocity.items(), key=lambda x: x[1], reverse=True)[:10]
cooling_down = sorted(velocity.items(), key=lambda x: x[1])[:10]

print("HEATING UP (appearing more in H2 vs H1):")
print(f"{'2DP':<6} {'H1':<5} {'H2':<5} {'Velocity':<10}")
print("-"*30)
for pair, vel in heating_up:
    h1 = first_half_2dp[pair]
    h2 = second_half_2dp[pair]
    print(f"{pair:<6} {h1:<5} {h2:<5} +{vel}")

print()
print("COOLING DOWN (appearing less in H2 vs H1):")
print(f"{'2DP':<6} {'H1':<5} {'H2':<5} {'Velocity':<10}")
print("-"*30)
for pair, vel in cooling_down:
    h1 = first_half_2dp[pair]
    h2 = second_half_2dp[pair]
    print(f"{pair:<6} {h1:<5} {h2:<5} {vel}")

print()

# Weekly velocity (last 7 days vs previous 7)
print("Weekly Velocity (rolling analysis - last 7 days of data):")
print("-"*50)

if len(results) >= 14:
    last_7 = results[-7:]
    prev_7 = results[-14:-7]
    
    last_7_2dp = defaultdict(int)
    prev_7_2dp = defaultdict(int)
    
    for r in last_7:
        for pair in r['evening_2dp']:
            last_7_2dp[pair] += 1
    
    for r in prev_7:
        for pair in r['evening_2dp']:
            prev_7_2dp[pair] += 1
    
    weekly_vel = {}
    all_weekly = set(last_7_2dp.keys()) | set(prev_7_2dp.keys())
    for pair in all_weekly:
        w1 = prev_7_2dp[pair]
        w2 = last_7_2dp[pair]
        weekly_vel[pair] = w2 - w1
    
    weekly_hot = sorted(weekly_vel.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"Hottest 2DPs in final week: {', '.join([f'{p}(+{v})' for p, v in weekly_hot if v > 0])}")

print()
print("="*100)
print("SUMMARY OF CREATIVE INSIGHTS")
print("="*100)
print("""
1. 2DP CHAIN: When you see a matching 2DP in Midday, look for its common 
   'chain partners' to narrow down Evening candidates.

2. 2DP HEAT MAP: Track monthly hot 2DPs - they often carry over.

3. 2DP + TD COMBO: Focus on candidates in the TD 'sweet spot' range.

4. 2DP VELOCITY: Prioritize 2DPs that are 'heating up' recently.

COMBINED STRATEGY:
- Start with Midday's 2DPs as JOP
- Filter to candidates with those 2DPs + their chain partners
- Prioritize candidates in TD sweet spot
- Boost candidates with 'heating up' 2DPs
""")
