#!/usr/bin/env python3
"""
🔗 Consecutive Pattern Analysis
=================================
Finds consecutive (streak) patterns across draws and tests if they predict next winner.

Patterns analyzed:
  - 1DP: same digit appears in N consecutive draws
  - 2DP: same pair appears in N consecutive draws  
  - 3DP: same triple appears in N consecutive draws
  - Sum: same digit sum appears in N consecutive draws
  - Sum Band: sum in same band (group of 5) for N consecutive draws
  - TD Band: winner TD in same band for N consecutive draws
  - Month: patterns by calendar month

Usage:
    python3 consecutive_analysis.py [--state Florida] [--start 2025-01-01] [--end 2026-02-20]
"""

import requests, json, argparse, sys, csv
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from itertools import combinations

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

def api(path, data=None):
    url = f"{BASE_URL}{path}?db={DB_MODE}"
    r = requests.post(url, json=data, timeout=120) if data else requests.get(url, timeout=120)
    r.raise_for_status()
    return r.json()

def digit_sum(n): return sum(int(c) for c in n)
def get_pairs(n):
    c = list(n)
    return {c[i]+c[j] for i in range(len(c)) for j in range(i+1, len(c))}
def get_triples(n):
    c = list(n)
    return {c[i]+c[j]+c[k] for i in range(len(c)) for j in range(i+1, len(c)) for k in range(j+1, len(c))}
def classify(n):
    counts = sorted(Counter(n).values(), reverse=True)
    if counts[0] == 4: return 'Q'
    if counts[0] == 3: return 'T'
    if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 'DD'
    if counts[0] == 2: return 'D'
    return 'S'
def sum_band(s): return f"{(s//5)*5}-{(s//5)*5+4}"
def td_band(t): return f"{(t//10)*10}-{(t//10)*10+9}"


def load_draws(state, game, start, end):
    """Load all draws in date range."""
    data = api('/api/draws/recent', {
        'state': state, 'game_type': game,
        'start_date': start, 'end_date': end
    })
    draws = data.get('draws', [])
    print(f"Loaded {len(draws)} draws from {start} to {end}")
    return draws


def load_td_map(state, game):
    """Pre-load TD map."""
    from itertools import combinations_with_replacement
    all_combos = [''.join(str(d) for d in c) for c in combinations_with_replacement(range(10), 4)]
    td_map = {}
    for i in range(0, len(all_combos), 500):
        chunk = all_combos[i:i+500]
        try:
            td = api('/api/td/lookup', {'candidates': chunk, 'state': state, 'game_type': game})
            td_map.update(td.get('td', {}))
        except: pass
    return td_map


def analyze_consecutive_patterns(draws, td_map):
    """
    For each draw, look at the N previous draws and find consecutive patterns.
    Then check if those patterns predict the current draw.
    """
    results = {
        '1dp_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
        '2dp_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
        '3dp_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
        'sum_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
        'sum_band_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
        'td_band_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
        'type_streak': defaultdict(lambda: {'predict': 0, 'total': 0, 'examples': []}),
    }
    
    # Group draws by date (there may be mid+eve on same date)
    by_date = defaultdict(list)
    for d in draws:
        by_date[d['date']].append(d)
    
    dates = sorted(by_date.keys())
    
    if len(dates) < 5:
        print("Not enough dates for analysis")
        return results
    
    # Build per-draw-slot feature vectors
    # Each "slot" = one draw (value, norm, digits, pairs, triples, sum, td, type, date, tod)
    slots = []
    for d in draws:
        norm = d['actual']
        td = td_map.get(norm, 0)
        slots.append({
            'date': d['date'], 'tod': d.get('tod', ''),
            'value': d['value'], 'norm': norm,
            'digits': set(norm),
            'pairs': get_pairs(norm),
            'triples': get_triples(norm),
            'sum': digit_sum(norm),
            'sum_band': sum_band(digit_sum(norm)),
            'td': td,
            'td_band': td_band(td),
            'type': classify(norm),
        })
    
    # For each draw (starting from index 2), look at streaks in previous draws
    for i in range(2, len(slots)):
        current = slots[i]
        
        # Look back up to 10 draws
        lookback = slots[max(0, i-10):i]
        lookback.reverse()  # most recent first
        
        # === 1DP Consecutive ===
        # For each digit 0-9, how many consecutive previous draws contain it?
        for digit in '0123456789':
            streak = 0
            for prev in lookback:
                if digit in prev['digits']:
                    streak += 1
                else:
                    break
            if streak >= 2:
                key = streak
                results['1dp_streak'][key]['total'] += 1
                if digit in current['digits']:
                    results['1dp_streak'][key]['predict'] += 1
                    if len(results['1dp_streak'][key]['examples']) < 3:
                        results['1dp_streak'][key]['examples'].append(
                            f"{current['date']} d:{digit} streak:{streak} → {current['value']}")
        
        # === 2DP Consecutive ===
        all_pairs_prev = set()
        for prev in lookback[:1]:
            all_pairs_prev = prev['pairs']
        
        for pair in all_pairs_prev:
            streak = 0
            for prev in lookback:
                if pair in prev['pairs']:
                    streak += 1
                else:
                    break
            if streak >= 2:
                key = streak
                results['2dp_streak'][key]['total'] += 1
                if pair in current['pairs']:
                    results['2dp_streak'][key]['predict'] += 1
                    if len(results['2dp_streak'][key]['examples']) < 3:
                        results['2dp_streak'][key]['examples'].append(
                            f"{current['date']} p:{pair} streak:{streak} → {current['value']}")
        
        # === 3DP Consecutive ===
        for triple in lookback[0]['triples']:
            streak = 0
            for prev in lookback:
                if triple in prev['triples']:
                    streak += 1
                else:
                    break
            if streak >= 2:
                key = streak
                results['3dp_streak'][key]['total'] += 1
                if triple in current['triples']:
                    results['3dp_streak'][key]['predict'] += 1
                    if len(results['3dp_streak'][key]['examples']) < 3:
                        results['3dp_streak'][key]['examples'].append(
                            f"{current['date']} t:{triple} streak:{streak} → {current['value']}")
        
        # === Sum Consecutive (exact) ===
        streak = 0
        prev_sum = lookback[0]['sum']
        for prev in lookback:
            if prev['sum'] == prev_sum:
                streak += 1
            else:
                break
        if streak >= 2:
            results['sum_streak'][streak]['total'] += 1
            if current['sum'] == prev_sum:
                results['sum_streak'][streak]['predict'] += 1
                if len(results['sum_streak'][streak]['examples']) < 3:
                    results['sum_streak'][streak]['examples'].append(
                        f"{current['date']} Σ{prev_sum} streak:{streak} → {current['value']}(Σ{current['sum']})")
        
        # === Sum Band Consecutive ===
        streak = 0
        prev_band = lookback[0]['sum_band']
        for prev in lookback:
            if prev['sum_band'] == prev_band:
                streak += 1
            else:
                break
        if streak >= 2:
            results['sum_band_streak'][streak]['total'] += 1
            if current['sum_band'] == prev_band:
                results['sum_band_streak'][streak]['predict'] += 1
                if len(results['sum_band_streak'][streak]['examples']) < 3:
                    results['sum_band_streak'][streak]['examples'].append(
                        f"{current['date']} band:{prev_band} streak:{streak} → Σ{current['sum']}({current['sum_band']})")
        
        # === TD Band Consecutive ===
        streak = 0
        prev_td_band = lookback[0]['td_band']
        for prev in lookback:
            if prev['td_band'] == prev_td_band:
                streak += 1
            else:
                break
        if streak >= 2:
            results['td_band_streak'][streak]['total'] += 1
            if current['td_band'] == prev_td_band:
                results['td_band_streak'][streak]['predict'] += 1
                if len(results['td_band_streak'][streak]['examples']) < 3:
                    results['td_band_streak'][streak]['examples'].append(
                        f"{current['date']} tdband:{prev_td_band} streak:{streak} → TD{current['td']}({current['td_band']})")
        
        # === Type Consecutive ===
        streak = 0
        prev_type = lookback[0]['type']
        for prev in lookback:
            if prev['type'] == prev_type:
                streak += 1
            else:
                break
        if streak >= 2:
            results['type_streak'][streak]['total'] += 1
            if current['type'] == prev_type:
                results['type_streak'][streak]['predict'] += 1
                if len(results['type_streak'][streak]['examples']) < 3:
                    results['type_streak'][streak]['examples'].append(
                        f"{current['date']} type:{prev_type} streak:{streak} → {current['value']}({current['type']})")
    
    return results


def analyze_monthly_patterns(draws, td_map):
    """Analyze patterns by calendar month."""
    monthly = defaultdict(lambda: {
        'draws': 0, 'sums': [], 'tds': [], 'types': Counter(),
        'digits': Counter(), 'pairs': Counter()
    })
    
    for d in draws:
        dt = datetime.strptime(d['date'], '%Y-%m-%d') if isinstance(d['date'], str) else d['date']
        month_key = dt.strftime('%Y-%m')
        month_name = dt.strftime('%b')
        norm = d['actual']
        td = td_map.get(norm, 0)
        
        m = monthly[month_key]
        m['draws'] += 1
        m['month_name'] = month_name
        m['sums'].append(digit_sum(norm))
        m['tds'].append(td)
        m['types'][classify(norm)] += 1
        for c in set(norm):
            m['digits'][c] += 1
        for p in get_pairs(norm):
            m['pairs'][p] += 1
    
    return monthly


def print_results(results, monthly, draws, td_map):
    """Print analysis results."""
    
    print(f"\n{'='*80}")
    print(f"🔗 CONSECUTIVE PATTERN ANALYSIS")
    print(f"{'='*80}\n")
    
    categories = [
        ('1dp_streak', '1DP Digit Streaks', 'Same digit in N consecutive draws → appears in next?'),
        ('2dp_streak', '2DP Pair Streaks', 'Same pair in N consecutive draws → appears in next?'),
        ('3dp_streak', '3DP Triple Streaks', 'Same triple in N consecutive draws → appears in next?'),
        ('sum_streak', 'Exact Sum Streaks', 'Same digit sum in N consecutive draws → repeats?'),
        ('sum_band_streak', 'Sum Band Streaks', 'Sum in same band (5-wide) for N consecutive draws → stays?'),
        ('td_band_streak', 'TD Band Streaks', 'Winner TD in same band (10-wide) for N consecutive draws → stays?'),
        ('type_streak', 'Type Streaks', 'Same type (S/D/DD/T/Q) in N consecutive draws → repeats?'),
    ]
    
    for cat_key, cat_name, cat_desc in categories:
        data = results[cat_key]
        if not data:
            continue
        
        print(f"\n{'─'*60}")
        print(f"📊 {cat_name}")
        print(f"   {cat_desc}")
        print(f"{'─'*60}")
        
        print(f"  {'Streak':<10} {'Occurrences':>12} {'Predicted':>10} {'Rate':>8} {'Signal':<10}")
        print(f"  {'-'*55}")
        
        for streak_len in sorted(data.keys()):
            d = data[streak_len]
            total = d['total']
            pred = d['predict']
            rate = round(pred / total * 100, 1) if total > 0 else 0
            
            # Signal strength: compare to baseline
            # 1DP baseline: ~65% (most digits appear often)
            # 2DP baseline: ~30%
            # Sum baseline: ~5% (exact match)
            # Type baseline: ~40% (S and D dominate)
            baseline = {
                '1dp_streak': 65, '2dp_streak': 30, '3dp_streak': 15,
                'sum_streak': 5, 'sum_band_streak': 30,
                'td_band_streak': 25, 'type_streak': 40,
            }.get(cat_key, 30)
            
            signal = '🔥 HOT' if rate > baseline * 1.3 else ('❄️ COLD' if rate < baseline * 0.7 else '➡️ avg')
            if total < 10:
                signal = '⚠️ low n'
            
            print(f"  {streak_len:<10} {total:>12} {pred:>10} {rate:>7.1f}% {signal:<10}")
            
            # Show examples
            for ex in d['examples'][:2]:
                print(f"              └ {ex}")
    
    # === Monthly Analysis ===
    print(f"\n{'='*80}")
    print(f"📅 MONTHLY PATTERNS")
    print(f"{'='*80}\n")
    
    print(f"  {'Month':<10} {'Draws':>6} {'Avg Σ':>7} {'Avg TD':>7} {'Top Type':>10} {'Top Digits':>15} {'Top Pairs':>15}")
    print(f"  {'-'*75}")
    
    for mk in sorted(monthly.keys()):
        m = monthly[mk]
        avg_s = round(sum(m['sums'])/len(m['sums']), 1) if m['sums'] else 0
        avg_td = round(sum(m['tds'])/len(m['tds']), 1) if m['tds'] else 0
        top_type = m['types'].most_common(1)[0][0] if m['types'] else '-'
        top_digits = ','.join([d for d, c in m['digits'].most_common(3)])
        top_pairs = ','.join([p for p, c in m['pairs'].most_common(3)])
        
        print(f"  {mk:<10} {m['draws']:>6} {avg_s:>7} {avg_td:>7} {top_type:>10} {top_digits:>15} {top_pairs:>15}")
    
    # === Cross-Month Digit Trends ===
    print(f"\n{'─'*60}")
    print(f"📊 Digit Frequency by Month (% of draws containing digit)")
    print(f"{'─'*60}")
    
    months = sorted(monthly.keys())[-6:]  # Last 6 months
    print(f"  {'Digit':<7}", end='')
    for mk in months:
        print(f"  {mk:>8}", end='')
    print(f"  {'Trend':>8}")
    print(f"  {'-'*65}")
    
    for digit in '0123456789':
        print(f"  {digit:<7}", end='')
        rates = []
        for mk in months:
            m = monthly[mk]
            pct = round(m['digits'].get(digit, 0) / m['draws'] * 100) if m['draws'] > 0 else 0
            rates.append(pct)
            print(f"  {pct:>7}%", end='')
        
        # Simple trend: last 3 vs first 3
        if len(rates) >= 4:
            recent = sum(rates[-3:]) / 3
            earlier = sum(rates[:3]) / 3
            if recent > earlier * 1.2:
                trend = '📈'
            elif recent < earlier * 0.8:
                trend = '📉'
            else:
                trend = '➡️'
        else:
            trend = '—'
        print(f"  {trend:>6}")
    
    # === Consecutive Pair Analysis (which pairs streak most?) ===
    print(f"\n{'─'*60}")
    print(f"📊 Most Streaky 2DP Pairs (consecutive draw appearances)")
    print(f"{'─'*60}")
    
    # Build pair streak history
    pair_streaks = defaultdict(list)
    slots = []
    for d in draws:
        slots.append({'date': d['date'], 'pairs': get_pairs(d['actual'])})
    
    for pair_str in [f"{a}{b}" for a in range(10) for b in range(a, 10)]:
        current_streak = 0
        for slot in slots:
            if pair_str in slot['pairs']:
                current_streak += 1
            else:
                if current_streak >= 2:
                    pair_streaks[pair_str].append(current_streak)
                current_streak = 0
        if current_streak >= 2:
            pair_streaks[pair_str].append(current_streak)
    
    # Sort by total streak events
    sorted_pairs = sorted(pair_streaks.items(), 
                          key=lambda x: (-max(x[1]), -len(x[1])))
    
    print(f"  {'Pair':<6} {'Max Streak':>10} {'Streak Events':>14} {'Avg Streak':>10} {'Streaks'}")
    print(f"  {'-'*65}")
    for pair, streaks in sorted_pairs[:20]:
        print(f"  {pair:<6} {max(streaks):>10} {len(streaks):>14} {sum(streaks)/len(streaks):>10.1f} {streaks[:8]}")
    
    # === Summary & Strategy Insights ===
    print(f"\n{'='*80}")
    print(f"💡 STRATEGY INSIGHTS")
    print(f"{'='*80}\n")
    
    # Find strongest signals
    insights = []
    
    for cat_key, cat_name, _ in categories:
        data = results[cat_key]
        for streak_len, d in data.items():
            if d['total'] >= 10:
                rate = d['predict'] / d['total'] * 100
                baseline = {
                    '1dp_streak': 65, '2dp_streak': 30, '3dp_streak': 15,
                    'sum_streak': 5, 'sum_band_streak': 30,
                    'td_band_streak': 25, 'type_streak': 40,
                }.get(cat_key, 30)
                lift = rate / baseline if baseline > 0 else 1
                if lift > 1.2:
                    insights.append((cat_name, streak_len, rate, d['total'], lift))
    
    insights.sort(key=lambda x: -x[4])
    
    if insights:
        print("  Strongest consecutive signals (>20% above baseline):\n")
        for cat_name, streak, rate, n, lift in insights[:10]:
            print(f"  ✅ {cat_name} streak={streak}: {rate:.1f}% prediction rate ({n} occurrences, {lift:.2f}x baseline)")
    else:
        print("  No strong consecutive signals found above baseline.")
    
    print(f"\n  Key takeaways:")
    
    # 1DP insight
    d1 = results['1dp_streak']
    if 3 in d1 and d1[3]['total'] >= 5:
        r = d1[3]['predict'] / d1[3]['total'] * 100
        print(f"  • 1DP 3-streak: {r:.0f}% of the time, a digit in 3 straight draws appears in the 4th")
    
    # Sum band insight
    dsb = results['sum_band_streak']
    if 2 in dsb and dsb[2]['total'] >= 10:
        r = dsb[2]['predict'] / dsb[2]['total'] * 100
        print(f"  • Sum Band 2-streak: {r:.0f}% of the time, sum stays in same band for a 3rd draw")
    
    # Type insight
    dt = results['type_streak']
    if 2 in dt and dt[2]['total'] >= 10:
        r = dt[2]['predict'] / dt[2]['total'] * 100
        print(f"  • Type 2-streak: {r:.0f}% of the time, same type (S/D/etc) repeats a 3rd time")
    
    # TD band insight
    dtd = results['td_band_streak']
    if 2 in dtd and dtd[2]['total'] >= 10:
        r = dtd[2]['predict'] / dtd[2]['total'] * 100
        print(f"  • TD Band 2-streak: {r:.0f}% of the time, winner TD stays in same 10-wide band")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='🔗 Consecutive Pattern Analysis')
    p.add_argument('--start', default='2025-01-01', help='Start date')
    p.add_argument('--end', default='2026-02-20', help='End date')
    p.add_argument('--state', default='Florida')
    p.add_argument('--game', default='pick4')
    p.add_argument('--url', default='http://localhost:5001')
    args = p.parse_args()
    BASE_URL = args.url
    
    try:
        requests.get(f"{BASE_URL}/api/rbtl/data-stats/Florida/pick4?db={DB_MODE}", timeout=5)
        print("✅ Connected")
    except:
        print("❌ Flask not running"); sys.exit(1)
    
    print("📈 Loading TD map...")
    td_map = load_td_map(args.state, args.game)
    print(f"✅ TD loaded: {len(td_map)} entries")
    
    print(f"\n📊 Loading draws {args.start} → {args.end}...")
    draws = load_draws(args.state, args.game, args.start, args.end)
    
    print("🔗 Analyzing consecutive patterns...")
    results = analyze_consecutive_patterns(draws, td_map)
    
    print("📅 Analyzing monthly patterns...")
    monthly = analyze_monthly_patterns(draws, td_map)
    
    print_results(results, monthly, draws, td_map)
