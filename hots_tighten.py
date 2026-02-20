#!/usr/bin/env python3
"""
🌶️ Hots Strategy Tightening Analysis
======================================
Tests many parameter combinations to find the sweet spot:
  - Minimize candidate count
  - Maximize hit rate
  - Find the Pareto frontier

Usage:
    python3 hots_tighten.py [--start 2026-01-01] [--end 2026-02-20]
"""

import requests
import json
import argparse
import csv
import sys
from datetime import datetime, timedelta
from itertools import combinations_with_replacement
from collections import Counter

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

def api(path, data=None):
    url = f"{BASE_URL}{path}?db={DB_MODE}"
    if data:
        r = requests.post(url, json=data, timeout=60)
    else:
        r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()

def get_sorted_combos(digits, n=4):
    return [''.join(str(d) for d in c) for c in combinations_with_replacement(sorted(digits), n)]

def digit_sum(norm):
    return sum(int(c) for c in norm)

def get_2dp_pairs(norm):
    chars = list(norm)
    pairs = set()
    for i in range(len(chars)):
        for j in range(i+1, len(chars)):
            pairs.add(chars[i] + chars[j])
    return pairs

def classify_type(norm):
    counts = sorted(Counter(norm).values(), reverse=True)
    if counts[0] == 4: return 'Q'
    if counts[0] == 3: return 'T'
    if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 'DD'
    if counts[0] == 2: return 'D'
    return 'S'

def generate_candidates(digits, sum_min, sum_max, td_map, td_min=0, td_max=999, 
                         require_2dp=None, type_filter=None):
    """Generate candidates with all filters."""
    cands = []
    for combo in combinations_with_replacement(sorted(digits), 4):
        norm = ''.join(str(d) for d in combo)
        ds = digit_sum(norm)
        if ds < sum_min or ds > sum_max:
            continue
        td = td_map.get(norm, 0)
        if td < td_min or td > td_max:
            continue
        if require_2dp:
            pairs = get_2dp_pairs(norm)
            if not any(p in pairs for p in require_2dp):
                continue
        if type_filter:
            ct = classify_type(norm)
            if ct not in type_filter:
                continue
        cands.append(norm)
    return cands

def analyze_seeds(seed_values, td_map):
    """Extract hot properties from seeds."""
    digits = Counter()
    pairs = Counter()
    sums = []
    tds = []
    
    for val in seed_values:
        norm = ''.join(sorted(val))
        chars = list(norm)
        sums.append(digit_sum(norm))
        tds.append(td_map.get(norm, 0))
        for c in set(chars):
            digits[c] += 1
        for p in get_2dp_pairs(norm):
            pairs[p] += 1
    
    hot_digits = [int(d) for d in digits.keys()]
    tds_nz = [t for t in tds if t > 0]
    
    # Top pairs by frequency
    top_pairs = [p for p, c in pairs.most_common(10)]
    
    return {
        'hot_digits': hot_digits,
        'sum_min': min(sums) if sums else 10,
        'sum_max': max(sums) if sums else 26,
        'sum_avg': sum(sums)/len(sums) if sums else 18,
        'sum_med': sorted(sums)[len(sums)//2] if sums else 18,
        'td_min': min(tds_nz) if tds_nz else 10,
        'td_max': max(tds_nz) if tds_nz else 50,
        'td_avg': sum(tds_nz)/len(tds_nz) if tds_nz else 30,
        'top_pairs': top_pairs,
    }


# ── Strategy Parameter Grid ────────────────────────────────────────────────

def build_strategies():
    """Build grid of parameter combos to test."""
    strategies = {}
    
    # === SUM PADDING variants ===
    for s_pad in [0, 1, 2, 3, 5]:
        # === TD PADDING variants ===
        for t_pad in [0, 2, 5]:
            key = f"sum±{s_pad}_td±{t_pad}"
            strategies[key] = {
                'name': f"Σ±{s_pad} TD±{t_pad}",
                'sum_pad': s_pad, 'td_pad': t_pad,
                'digits': 'hot', 'type_filter': None, 'pairs': None,
            }
            
            # With type filters
            for tf, tf_name in [({'S','D'}, 'SD'), ({'D'}, 'D'), ({'S'}, 'S')]:
                key2 = f"sum±{s_pad}_td±{t_pad}_{tf_name}"
                strategies[key2] = {
                    'name': f"Σ±{s_pad} TD±{t_pad} {tf_name}",
                    'sum_pad': s_pad, 'td_pad': t_pad,
                    'digits': 'hot', 'type_filter': tf, 'pairs': None,
                }
    
    # === Tight sum around median/avg ===
    for window in [3, 5, 7]:
        key = f"sum_med±{window//2}_td±2"
        strategies[key] = {
            'name': f"Σ med±{window//2} TD±2",
            'sum_pad': None, 'sum_window_med': window,
            'td_pad': 2, 'digits': 'hot', 'type_filter': None, 'pairs': None,
        }
        # SD variant
        key2 = f"sum_med±{window//2}_td±2_SD"
        strategies[key2] = {
            'name': f"Σ med±{window//2} TD±2 SD",
            'sum_pad': None, 'sum_window_med': window,
            'td_pad': 2, 'digits': 'hot', 'type_filter': {'S','D'}, 'pairs': None,
        }
    
    # === All digits variants (sum+TD does the work) ===
    for s_pad in [1, 2]:
        for t_pad in [0, 2]:
            key = f"alldig_sum±{s_pad}_td±{t_pad}"
            strategies[key] = {
                'name': f"All10 Σ±{s_pad} TD±{t_pad}",
                'sum_pad': s_pad, 'td_pad': t_pad,
                'digits': 'all', 'type_filter': None, 'pairs': None,
            }
            key2 = f"alldig_sum±{s_pad}_td±{t_pad}_SD"
            strategies[key2] = {
                'name': f"All10 Σ±{s_pad} TD±{t_pad} SD",
                'sum_pad': s_pad, 'td_pad': t_pad,
                'digits': 'all', 'type_filter': {'S','D'}, 'pairs': None,
            }
    
    # === With top 2DP pair requirement ===
    for s_pad in [2, 3]:
        key = f"sum±{s_pad}_td±2_top3pair"
        strategies[key] = {
            'name': f"Σ±{s_pad} TD±2 +top3pair",
            'sum_pad': s_pad, 'td_pad': 2,
            'digits': 'hot', 'type_filter': None, 'pairs': 'top3',
        }
    
    return strategies


# ── Main ────────────────────────────────────────────────────────────────────

def run_tighten(state, game_type, start_date, end_date, pw_days=5):
    print(f"\n{'='*80}")
    print(f"🌶️  HOTS TIGHTENING ANALYSIS")
    print(f"{'='*80}")
    print(f"State: {state} | Game: {game_type} | Dates: {start_date} → {end_date}")
    print(f"{'='*80}\n")
    
    # Pre-load TD map
    print("📈 Pre-loading TD map...")
    all_combos = get_sorted_combos(list(range(10)), 4)
    td_map = {}
    for i in range(0, len(all_combos), 500):
        chunk = all_combos[i:i+500]
        try:
            td_data = api('/api/td/lookup', {'candidates': chunk, 'state': state, 'game_type': game_type})
            td_map.update(td_data.get('td', {}))
        except Exception as e:
            print(f"  ⚠️  TD error: {e}")
    print(f"✅ TD loaded: {len(td_map)} entries (max TD: {max(td_map.values()) if td_map else 0})\n")
    
    strategies = build_strategies()
    print(f"Testing {len(strategies)} parameter combos...\n")
    
    # Initialize results
    results = {k: {'hits': 0, 'winners': 0, 'total_cands': 0, 'dates': 0} for k in strategies}
    
    # Track per-date for miss analysis
    miss_details = []
    
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    date_count = 0
    
    while current <= end:
        target_date = current.strftime('%Y-%m-%d')
        seed_start = (current - timedelta(days=pw_days)).strftime('%Y-%m-%d')
        seed_end = (current - timedelta(days=1)).strftime('%Y-%m-%d')
        
        try:
            seeds_data = api('/api/draws/recent', {
                'state': state, 'game_type': game_type,
                'start_date': seed_start, 'end_date': seed_end
            })
            winner_data = api('/api/draws/recent', {
                'state': state, 'game_type': game_type,
                'start_date': target_date, 'end_date': target_date
            })
        except:
            current += timedelta(days=1)
            continue
        
        seeds = seeds_data.get('draws', [])
        winners = winner_data.get('draws', [])
        
        if len(seeds) < 2 or not winners:
            current += timedelta(days=1)
            continue
        
        date_count += 1
        seed_values = [s['value'] for s in seeds]
        analysis = analyze_seeds(seed_values, td_map)
        
        winner_norms = [w['actual'] for w in winners]
        
        sys.stdout.write(f"\r  [{date_count}] {target_date} | Seeds: {len(seeds)} | Winners: {len(winners)}")
        sys.stdout.flush()
        
        for strat_key, strat in strategies.items():
            # Digits
            if strat['digits'] == 'all':
                digits = list(range(10))
            else:
                digits = analysis['hot_digits']
            
            # Sum range
            if strat.get('sum_window_med'):
                w = strat['sum_window_med']
                med = analysis['sum_med']
                s_min = max(0, int(med - w//2))
                s_max = min(36, int(med + w//2))
            else:
                s_pad = strat['sum_pad']
                s_min = max(0, analysis['sum_min'] - s_pad)
                s_max = min(36, analysis['sum_max'] + s_pad)
            
            # TD range
            t_pad = strat.get('td_pad', 0)
            if t_pad is not None:
                t_min = max(0, analysis['td_min'] - t_pad)
                t_max = analysis['td_max'] + t_pad
            else:
                t_min, t_max = 0, 999
            
            # Pairs
            req_pairs = None
            if strat['pairs'] == 'top3':
                req_pairs = analysis['top_pairs'][:3]
            
            # Type filter
            tf = strat.get('type_filter')
            
            # Generate
            cands = generate_candidates(digits, s_min, s_max, td_map, t_min, t_max,
                                        require_2dp=req_pairs, type_filter=tf)
            
            cand_set = set(cands)
            hits = sum(1 for w in winner_norms if w in cand_set)
            
            results[strat_key]['hits'] += hits
            results[strat_key]['winners'] += len(winners)
            results[strat_key]['total_cands'] += len(cands)
            results[strat_key]['dates'] += 1
        
        # Track misses for best strategy analysis later
        for w in winners:
            w_norm = w['actual']
            w_sum = digit_sum(w_norm)
            w_td = td_map.get(w_norm, 0)
            w_type = classify_type(w_norm)
            # Check against baseline (sum±2, td±2)
            s_min_base = max(0, analysis['sum_min'] - 2)
            s_max_base = min(36, analysis['sum_max'] + 2)
            t_min_base = max(0, analysis['td_min'] - 2)
            t_max_base = analysis['td_max'] + 2
            
            in_sum = s_min_base <= w_sum <= s_max_base
            in_td = t_min_base <= w_td <= t_max_base
            in_digits = all(int(c) in analysis['hot_digits'] for c in w_norm)
            
            if not (in_sum and in_td and in_digits):
                miss_details.append({
                    'date': target_date, 'winner': w['value'], 'norm': w_norm,
                    'type': w_type, 'sum': w_sum, 'td': w_td,
                    'seed_sum_range': f"{analysis['sum_min']}-{analysis['sum_max']}",
                    'seed_td_range': f"{analysis['td_min']}-{analysis['td_max']}",
                    'miss_sum': not in_sum, 'miss_td': not in_td, 'miss_digits': not in_digits,
                })
        
        current += timedelta(days=1)
    
    # ── Results ─────────────────────────────────────────────────────────────
    print(f"\n\n{'='*80}")
    print(f"📊 RESULTS — {date_count} dates, {results[list(results.keys())[0]]['winners']} winners")
    print(f"{'='*80}\n")
    
    # Sort by hit rate desc, then by avg cands asc
    sorted_strats = sorted(results.items(), 
                            key=lambda x: (-x[1]['hits']/max(x[1]['winners'],1), 
                                          x[1]['total_cands']/max(x[1]['dates'],1)))
    
    print(f"{'Strategy':<32} {'Rate':>7} {'Hits':>10} {'Avg Cands':>10} {'$/Draw':>8} {'ROI':>8}")
    print(f"{'-'*85}")
    
    for strat_key, r in sorted_strats:
        rate = round(r['hits'] / r['winners'] * 100, 1) if r['winners'] > 0 else 0
        avg_cands = round(r['total_cands'] / r['dates']) if r['dates'] > 0 else 0
        cost_per_draw = avg_cands  # $1 per box play
        # Expected value: hit_rate * $200 payout - cost
        expected_per_draw = (rate/100) * 200 - cost_per_draw
        roi = round(expected_per_draw / cost_per_draw * 100) if cost_per_draw > 0 else 0
        
        flag = ''
        if rate >= 70 and avg_cands <= 200: flag = ' 💎'
        elif rate >= 60 and avg_cands <= 150: flag = ' 💎'
        elif rate >= 50 and avg_cands <= 100: flag = ' 💎'
        elif rate >= 80: flag = ' ⭐'
        
        # Skip very low performers
        if rate < 10 and avg_cands > 50:
            continue
        
        strat_name = strategies[strat_key]['name']
        print(f"{strat_name:<32} {rate:>6.1f}% {r['hits']:>4}/{r['winners']:<4} {avg_cands:>10} ${cost_per_draw:>6} {roi:>6}%{flag}")
    
    # ── Pareto Frontier ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"💎 PARETO FRONTIER (best rate for each candidate count tier)")
    print(f"{'='*80}\n")
    
    tiers = [
        (0, 50, "Under 50"),
        (51, 100, "51-100"),
        (101, 150, "101-150"),
        (151, 200, "151-200"),
        (201, 300, "201-300"),
        (301, 500, "301-500"),
        (501, 999, "500+"),
    ]
    
    print(f"{'Tier':<15} {'Best Strategy':<32} {'Rate':>7} {'Avg Cands':>10}")
    print(f"{'-'*70}")
    
    for lo, hi, label in tiers:
        best = None
        best_rate = 0
        for strat_key, r in results.items():
            avg_c = r['total_cands'] / r['dates'] if r['dates'] > 0 else 0
            rate = r['hits'] / r['winners'] * 100 if r['winners'] > 0 else 0
            if lo <= avg_c <= hi and rate > best_rate:
                best_rate = rate
                best = (strat_key, r, avg_c)
        if best:
            sk, r, ac = best
            print(f"{label:<15} {strategies[sk]['name']:<32} {best_rate:>6.1f}% {int(ac):>10}")
        else:
            print(f"{label:<15} {'—':<32}")
    
    # ── Miss Analysis ───────────────────────────────────────────────────────
    if miss_details:
        print(f"\n{'='*80}")
        print(f"❌ MISS ANALYSIS (Hot Σ±2 TD±2 misses)")
        print(f"{'='*80}\n")
        
        sum_misses = sum(1 for m in miss_details if m['miss_sum'])
        td_misses = sum(1 for m in miss_details if m['miss_td'])
        digit_misses = sum(1 for m in miss_details if m['miss_digits'])
        
        print(f"Total misses: {len(miss_details)}")
        print(f"  Sum out of range:    {sum_misses} ({round(sum_misses/len(miss_details)*100)}%)")
        print(f"  TD out of range:     {td_misses} ({round(td_misses/len(miss_details)*100)}%)")
        print(f"  Digit not in seeds:  {digit_misses} ({round(digit_misses/len(miss_details)*100)}%)")
        
        print(f"\n{'Date':<12} {'Winner':<10} {'Type':<4} {'Σ':>4} {'TD':>4} {'Seed Σ':>10} {'Seed TD':>10} {'Why Missed':<20}")
        print(f"{'-'*80}")
        for m in miss_details[:30]:
            why = []
            if m['miss_sum']: why.append(f"Σ{m['sum']} outside")
            if m['miss_td']: why.append(f"TD{m['td']} outside")
            if m['miss_digits']: why.append('digit miss')
            print(f"{m['date']:<12} {m['winner']:<10} {m['type']:<4} {m['sum']:>4} {m['td']:>4} {m['seed_sum_range']:>10} {m['seed_td_range']:>10} {', '.join(why):<20}")
    
    # ── Save CSV ────────────────────────────────────────────────────────────
    csv_path = f"hots_tighten_{state.lower()}_{start_date}_to_{end_date}.csv"
    rows = []
    for strat_key, r in sorted_strats:
        avg_c = round(r['total_cands'] / r['dates']) if r['dates'] > 0 else 0
        rate = round(r['hits'] / r['winners'] * 100, 1) if r['winners'] > 0 else 0
        rows.append({
            'strategy': strategies[strat_key]['name'],
            'hit_rate': rate,
            'hits': r['hits'],
            'winners': r['winners'],
            'avg_cands': avg_c,
            'cost_per_draw': avg_c,
            'ev_per_draw': round((rate/100)*200 - avg_c, 1),
        })
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n📄 Results saved to: {csv_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='🌶️ Hots Tightening Analysis')
    parser.add_argument('--start', default='2026-01-01')
    parser.add_argument('--end', default='2026-02-20')
    parser.add_argument('--state', default='Florida')
    parser.add_argument('--game', default='pick4')
    parser.add_argument('--pw', type=int, default=5)
    parser.add_argument('--url', default='http://localhost:5001')
    args = parser.parse_args()
    BASE_URL = args.url
    
    print(f"Connecting to {BASE_URL}...")
    try:
        r = requests.get(f"{BASE_URL}/api/rbtl/data-stats/Florida/pick4?db={DB_MODE}", timeout=5)
        print(f"✅ Connected")
    except:
        print(f"❌ Cannot connect. Is Flask running?")
        sys.exit(1)
    
    run_tighten(args.state, args.game, args.start, args.end, args.pw)
