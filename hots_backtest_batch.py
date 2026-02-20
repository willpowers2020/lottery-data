#!/usr/bin/env python3
"""
🌶️ Hots Strategy Batch Backtest
================================
Tests the Hots strategy across multiple dates and parameter combos.
Calls the local Flask API for seeds, winners, and TD lookups.

Usage:
    python3 hots_backtest_batch.py [--start 2026-01-01] [--end 2026-02-20] [--state Florida] [--game pick4]

Output:
    - Console summary with hit rates per strategy
    - CSV file with detailed results per date
"""

import requests
import json
import argparse
import csv
import sys
from datetime import datetime, timedelta
from itertools import combinations_with_replacement
from collections import Counter

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

def api(path, data=None):
    """Call local Flask API."""
    url = f"{BASE_URL}{path}?db={DB_MODE}"
    try:
        if data:
            r = requests.post(url, json=data, timeout=60)
        else:
            r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(f"Cannot connect to {BASE_URL}. Is Flask running?")


# ── Hots Candidate Generator ───────────────────────────────────────────────

def get_sorted_combos(digits, num_digits=4):
    """Generate all sorted combinations with repetition from given digits."""
    return [''.join(str(d) for d in combo) 
            for combo in combinations_with_replacement(sorted(digits), num_digits)]

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

def generate_hots_candidates(digits, sum_min, sum_max, require_2dp=None, td_map=None, td_min=0, td_max=999):
    """Generate Hots candidates from parameters."""
    all_combos = get_sorted_combos(digits, 4)
    candidates = []
    
    for norm in all_combos:
        ds = digit_sum(norm)
        if ds < sum_min or ds > sum_max:
            continue
        
        # 2DP OR filter
        if require_2dp:
            pairs = get_2dp_pairs(norm)
            if not any(p in pairs for p in require_2dp):
                continue
        
        # TD filter
        if td_map and (td_min > 0 or td_max < 999):
            td = td_map.get(norm, 0)
            if td < td_min or td > td_max:
                continue
        
        candidates.append(norm)
    
    return candidates


# ── Seed Analysis ──────────────────────────────────────────────────────────

def analyze_seeds(seed_values):
    """Extract hot digits, sums, pairs from seed values."""
    digits = Counter()
    pairs = Counter()
    sums = []
    
    for val in seed_values:
        norm = ''.join(sorted(val))
        chars = list(norm)
        
        # Digit sum
        sums.append(digit_sum(norm))
        
        # Unique digits per seed
        for c in set(chars):
            digits[c] += 1
        
        # 2DP pairs
        for p in get_2dp_pairs(norm):
            pairs[p] += 1
    
    # Hot digits = any digit that appears in seeds
    hot_digits = [int(d) for d in digits.keys()]
    
    # Sum range
    sum_min = min(sums) if sums else 10
    sum_max = max(sums) if sums else 26
    
    # Hot pairs (freq >= 2)
    hot_pairs = [p for p, c in pairs.most_common() if c >= 2]
    
    # Cold pairs (freq == 1, from cold bands)
    band_totals = {}
    for p, c in pairs.items():
        band = int(p[0])
        band_totals[band] = band_totals.get(band, 0) + c
    if band_totals:
        sorted_bands = sorted(band_totals.values())
        cold_thresh = sorted_bands[len(sorted_bands)//3] if len(sorted_bands) > 2 else 0
        cold_pairs = []
        for p, c in pairs.items():
            band = int(p[0])
            if band_totals[band] <= cold_thresh:
                cold_pairs.append(p)
    else:
        cold_pairs = []
    
    return {
        'hot_digits': hot_digits,
        'sum_min': sum_min,
        'sum_max': sum_max,
        'sums': sums,
        'hot_pairs': hot_pairs,
        'cold_pairs': cold_pairs,
        'pairs': dict(pairs),
    }


# ── Strategy Definitions ───────────────────────────────────────────────────

STRATEGIES = {
    'hot_sum_td': {
        'name': '🔥 Hot Σ+TD',
        'desc': 'Hot sum range ±2, TD range ±2, all hot digits',
        'sum_pad': 2,
        'td_mode': 'hot',  # use seed TD range ±2
        'pairs': None,
    },
    'cold_sum_td': {
        'name': '❄️ Cold Σ+TD', 
        'desc': 'Wide sum range ±6, low TD (below seed min)',
        'sum_pad': 6,
        'td_mode': 'cold',  # 0 to seed_td_min - 1
        'pairs': None,
    },
    'hot_all': {
        'name': '🔥 Hot (All)',
        'desc': 'Hot sum ±2, hot TD ±2, top 3 hot 2DP pairs',
        'sum_pad': 2,
        'td_mode': 'hot',
        'pairs': 'hot',
    },
    'cold_all': {
        'name': '❄️ Cold (All)',
        'desc': 'Wide sum ±6, low TD, cold 2DP pairs',
        'sum_pad': 6,
        'td_mode': 'cold',
        'pairs': 'cold',
    },
    'hot_sum_cold_2dp': {
        'name': '🔥Σ + ❄️2DP',
        'desc': 'Hot sum ±2, any TD, cold 2DP pairs',
        'sum_pad': 2,
        'td_mode': None,
        'pairs': 'cold',
    },
    'all_digits_hot_sum_td': {
        'name': 'All Digits + Hot Σ+TD',
        'desc': 'All 10 digits, hot sum ±2, hot TD ±2',
        'sum_pad': 2,
        'td_mode': 'hot',
        'pairs': None,
        'all_digits': True,
    },
}


# ── Main Backtest Loop ─────────────────────────────────────────────────────

def run_batch(state, game_type, start_date, end_date, pw_days=5):
    """Run Hots backtest across date range."""
    
    print(f"\n{'='*70}")
    print(f"🌶️  HOTS BATCH BACKTEST")
    print(f"{'='*70}")
    print(f"State: {state} | Game: {game_type} | Dates: {start_date} → {end_date}")
    print(f"Lookback: {pw_days} days | Strategies: {len(STRATEGIES)}")
    print(f"{'='*70}\n")
    
    # Pre-load ALL TDs for every possible 4-digit combo in one shot
    print("📈 Pre-loading TD map (this may take a moment)...")
    all_combos = get_sorted_combos(list(range(10)), 4)
    td_map = {}
    for i in range(0, len(all_combos), 500):
        chunk = all_combos[i:i+500]
        try:
            td_data = api('/api/td/lookup', {
                'candidates': chunk, 'state': state, 'game_type': game_type
            })
            td_map.update(td_data.get('td', {}))
        except Exception as e:
            print(f"  ⚠️  TD fetch error at batch {i}: {e}")
    print(f"✅ TD map loaded: {len(td_map)} entries (max TD: {max(td_map.values()) if td_map else 0})")
    
    # Initialize results tracking
    results = {name: {'hits': 0, 'misses': 0, 'total_cands': 0, 'dates': 0, 'winners': 0,
                       'type_hits': {'S':0,'D':0,'DD':0,'T':0,'Q':0}} 
               for name in STRATEGIES}
    
    detailed_rows = []
    
    # Get all draw dates in range by fetching draws
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    date_count = 0
    
    while current <= end:
        target_date = current.strftime('%Y-%m-%d')
        
        # Get seeds: draws from BEFORE target date
        seed_start = (current - timedelta(days=pw_days)).strftime('%Y-%m-%d')
        seed_end = (current - timedelta(days=1)).strftime('%Y-%m-%d')  # day before target
        
        try:
            seed_data = api('/api/draws/recent', {
                'state': state, 'game_type': game_type,
                'start_date': seed_start, 'end_date': seed_end
            })
        except Exception as e:
            if date_count == 0:
                print(f"  ⚠️  API error on {target_date}: {e}")
            current += timedelta(days=1)
            continue
        
        seeds = seed_data.get('draws', [])
        
        # Get target winners: draws ON the target date
        try:
            winner_data = api('/api/draws/recent', {
                'state': state, 'game_type': game_type,
                'start_date': target_date, 'end_date': target_date
            })
        except Exception as e:
            current += timedelta(days=1)
            continue
        
        target_winners = winner_data.get('draws', [])
        
        if len(seeds) < 2 or not target_winners:
            current += timedelta(days=1)
            continue
        
        date_count += 1
        seed_values = [s['value'] for s in seeds]
        seed_norms = [s['actual'] for s in seeds]
        
        # Analyze seeds
        analysis = analyze_seeds(seed_values)
        
        # Get seed TD range from pre-loaded map
        seed_tds = [td_map.get(n, 0) for n in set(seed_norms)]
        seed_tds_nonzero = [t for t in seed_tds if t > 0]
        
        if seed_tds_nonzero:
            seed_td_min = min(seed_tds_nonzero)
            seed_td_max = max(seed_tds_nonzero)
        else:
            seed_td_min, seed_td_max = 10, 50
        
        # Print progress
        winner_strs = [f"{w['value']}({w.get('tod','')[:1]})" for w in target_winners]
        sys.stdout.write(f"\r  [{date_count}] {target_date} | Seeds: {len(seeds)} | Winners: {', '.join(winner_strs)}")
        sys.stdout.flush()
        
        # Test each strategy
        row = {
            'date': target_date,
            'seeds': len(seeds),
            'seed_values': '|'.join(seed_values[:5]),
            'winners': '|'.join([w['actual'] for w in target_winners]),
            'winner_values': '|'.join([w['value'] for w in target_winners]),
            'sum_min': analysis['sum_min'],
            'sum_max': analysis['sum_max'],
            'td_min': seed_td_min,
            'td_max': seed_td_max,
        }
        
        for strat_key, strat in STRATEGIES.items():
            # Determine digits
            if strat.get('all_digits'):
                digits = list(range(10))
            else:
                digits = analysis['hot_digits']
            
            # Sum range
            s_pad = strat['sum_pad']
            s_min = max(0, analysis['sum_min'] - s_pad)
            s_max = min(36, analysis['sum_max'] + s_pad)
            
            # TD range
            if strat['td_mode'] == 'hot':
                t_min = max(0, seed_td_min - 2)
                t_max = seed_td_max + 2
            elif strat['td_mode'] == 'cold':
                t_min = 0
                t_max = max(seed_td_min - 1, 10)
            else:
                t_min, t_max = 0, 999
            
            # 2DP pairs
            if strat['pairs'] == 'hot':
                req_pairs = analysis['hot_pairs'][:3] if analysis['hot_pairs'] else None
            elif strat['pairs'] == 'cold':
                req_pairs = analysis['cold_pairs'][:3] if analysis['cold_pairs'] else None
            else:
                req_pairs = None
            
            # Generate candidates
            cands = generate_hots_candidates(
                digits, s_min, s_max, 
                require_2dp=req_pairs if req_pairs else None,
                td_map=td_map, td_min=t_min, td_max=t_max
            )
            
            # Check winners
            cand_set = set(cands)
            hits = 0
            for w in target_winners:
                w_norm = w['actual']
                if w_norm in cand_set:
                    hits += 1
                    w_type = classify_type(w_norm)
                    results[strat_key]['type_hits'][w_type] += 1
            
            results[strat_key]['dates'] += 1
            results[strat_key]['winners'] += len(target_winners)
            results[strat_key]['hits'] += hits
            results[strat_key]['misses'] += len(target_winners) - hits
            results[strat_key]['total_cands'] += len(cands)
            
            row[f'{strat_key}_cands'] = len(cands)
            row[f'{strat_key}_hits'] = hits
            row[f'{strat_key}_of'] = len(target_winners)
        
        detailed_rows.append(row)
        current += timedelta(days=1)
    
    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print(f"📊 RESULTS SUMMARY — {date_count} draw dates tested")
    print(f"{'='*70}\n")
    
    print(f"{'Strategy':<25} {'Hit Rate':>10} {'Hits':>6} {'Total':>6} {'Avg Cands':>10} {'S':>4} {'D':>4} {'DD':>4} {'T':>4} {'Q':>4}")
    print(f"{'-'*85}")
    
    best_rate = 0
    best_strat = ''
    
    for strat_key, strat in STRATEGIES.items():
        r = results[strat_key]
        rate = round(r['hits'] / r['winners'] * 100, 1) if r['winners'] > 0 else 0
        avg_cands = round(r['total_cands'] / r['dates']) if r['dates'] > 0 else 0
        th = r['type_hits']
        
        marker = ' ⭐' if rate > best_rate else ''
        if rate > best_rate:
            best_rate = rate
            best_strat = strat['name']
        
        print(f"{strat['name']:<25} {rate:>9.1f}% {r['hits']:>6}/{r['winners']:<6} {avg_cands:>10} {th['S']:>4} {th['D']:>4} {th['DD']:>4} {th['T']:>4} {th['Q']:>4}{marker}")
    
    print(f"\n🏆 Best: {best_strat} at {best_rate}% hit rate")
    
    # ── Also compute combined strategies ────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"📊 COMBINED STRATEGY ANALYSIS")
    print(f"{'='*70}\n")
    
    # Check: hot OR cold catch
    hot_cold_hits = 0
    for row in detailed_rows:
        total_w = row.get('hot_sum_td_of', 0)
        hot_h = row.get('hot_sum_td_hits', 0)
        cold_h = row.get('cold_sum_td_hits', 0)
        hot_cold_hits += min(hot_h + cold_h, total_w)  # cap at total winners
    
    total_winners = results['hot_sum_td']['winners']
    if total_winners > 0:
        print(f"🔥+❄️ Hot Σ+TD OR Cold Σ+TD:  {hot_cold_hits}/{total_winners} = {round(hot_cold_hits/total_winners*100,1)}%")
    
    hot_all_cold_all_hits = 0
    for row in detailed_rows:
        total_w = row.get('hot_all_of', 0)
        h1 = row.get('hot_all_hits', 0)
        h2 = row.get('cold_all_hits', 0)
        hot_all_cold_all_hits += min(h1 + h2, total_w)
    
    if total_winners > 0:
        print(f"🔥+❄️ Hot All OR Cold All:     {hot_all_cold_all_hits}/{total_winners} = {round(hot_all_cold_all_hits/total_winners*100,1)}%")
    
    # Any strategy catch
    any_hits = 0
    for row in detailed_rows:
        total_w = row.get('hot_sum_td_of', 0)
        caught = 0
        for sk in STRATEGIES:
            caught = max(caught, row.get(f'{sk}_hits', 0))
        any_hits += min(caught, total_w)
    
    if total_winners > 0:
        print(f"🌶️  ANY Hots strategy:          {any_hits}/{total_winners} = {round(any_hits/total_winners*100,1)}%")
    
    # ── Save CSV ────────────────────────────────────────────────────────────
    csv_path = f"hots_backtest_{state.lower()}_{start_date}_to_{end_date}.csv"
    if detailed_rows:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=detailed_rows[0].keys())
            writer.writeheader()
            writer.writerows(detailed_rows)
        print(f"\n📄 Detailed results saved to: {csv_path}")
    
    return results, detailed_rows


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='🌶️ Hots Strategy Batch Backtest')
    parser.add_argument('--start', default='2026-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', default='2026-02-20', help='End date (YYYY-MM-DD)')
    parser.add_argument('--state', default='Florida', help='State name')
    parser.add_argument('--game', default='pick4', help='Game type')
    parser.add_argument('--pw', type=int, default=5, help='Lookback days for seeds')
    parser.add_argument('--url', default='http://localhost:5001', help='Flask API URL')
    
    args = parser.parse_args()
    BASE_URL = args.url
    
    # Test connectivity
    print(f"Connecting to {BASE_URL}...")
    try:
        r = requests.get(f"{BASE_URL}/api/rbtl/data-stats/Florida/pick4?db={DB_MODE}", timeout=5)
        if r.status_code == 200:
            stats = r.json()
            print(f"✅ Connected — {stats.get('total_draws', '?')} draws available")
        else:
            print(f"⚠️  API returned {r.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to Flask API at {BASE_URL}")
        print(f"   Make sure Flask is running: python3 app.py")
        print(f"   Error: {e}")
        sys.exit(1)
    
    run_batch(args.state, args.game, args.start, args.end, args.pw)
