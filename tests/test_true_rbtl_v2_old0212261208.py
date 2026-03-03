#!/usr/bin/env python3
"""
Test True RBTL v2 + 2DP Filter
================================
Step 1: Get seeds from lookback
Step 2: Find all historical months where seed perms appeared
Step 3: Select all months with count >= 3
Step 4: Pull ALL numbers from those months (622 candidates)
Step 5: Filter by 2DP match with LAST seed (8975) ← THE KEY FILTER

python3 test_true_rbtl_v2.py
"""

import requests

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

TARGET = "9869"
TARGET_NORM = "6899"


def sep(c="=", w=90):
    print(c * w)


def run(lookback_days=5, min_count=3, top_n=0, dp_size=0, dp_seed_mode='last'):
    url = f"{BASE_URL}/api/rbtl/backtest-v2?db={DB_MODE}"
    payload = {
        "state": "Florida",
        "game_type": "pick4",
        "target_date": "2019-09-15",
        "target_tod": "evening",
        "lookback_days": lookback_days,
        "min_count": min_count,
        "top_n_clusters": top_n,
        "dp_size": dp_size,
        "dp_seed_mode": dp_seed_mode,
        "include_same_day": True,
        "suggested_limit": 300
    }
    try:
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code != 200:
            print(f"  ERROR {r.status_code}: {r.text[:300]}")
            return None
        return r.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def show(data, label=""):
    if not data:
        return

    sep()
    print(f"  {label}")
    sep()
    print(f"  Target: {data['target_date']} {data['target_tod']}")
    print(f"  Seeds ({data['seed_count']}): {', '.join(data['seed_values'])}")
    print(f"  Min count: >= {data.get('min_count', '?')} | Months used: {data.get('selected_month_count', '?')}")

    # DP filter info
    dp = data.get('dp_filter', {})
    if dp.get('dp_size', 0) > 0:
        print(f"\n  2DP FILTER:")
        print(f"    DP seed: {dp.get('dp_seed', '?')} (mode: {dp.get('dp_seed_mode', '?')})")
        print(f"    DP pairs: {', '.join(dp.get('dp_pairs', []))}")
        print(f"    Before DP: {dp.get('candidates_before_dp', '?')} candidates")
        print(f"    After DP:  {dp.get('candidates_after_dp', '?')} candidates")
        print(f"    Filtered out: {dp.get('filtered_out', '?')}")
    else:
        print(f"\n  No DP filter applied")
        print(f"  Total candidates: {data.get('total_candidates_pre_dp', data.get('total_candidates', '?'))}")

    print(f"\n  FINAL CANDIDATE COUNT: {data['total_candidates']}")

    # Target
    print(f"\n  TARGET WINNER:")
    sep("-", 90)
    for w in data['winner_results']:
        st = "✅ FOUND" if w['found_in_candidates'] else "❌ MISS"
        rk = f"Rank #{w['rank']} of {w['total_candidates']}" if w['rank'] else "Not in candidates"
        ms = ', '.join(w.get('months', []))
        print(f"  {st}  {w['target_value']} (norm: {w['target_actual']}) {w['target_tod']}")
        print(f"         {rk} ({w['total_appearances']} apps)")
        if ms:
            print(f"         Months: {ms}")
    sep("-", 90)
    print(f"  HIT RATE: {data['hit_rate']}%")

    # Find target in suggested plays
    for p in data.get('suggested_plays', []):
        if p['candidate'] == TARGET_NORM:
            dp_pairs = ', '.join(p.get('dp_shared_pairs', []))
            print(f"\n  🎯 TARGET: Rank #{p['rank']}, {p['month_count']} months, "
                  f"{p.get('dp_shared_count', 0)} DP pairs ({dp_pairs})")
            break

    # Top plays
    print(f"\n  TOP 30 PLAYS:")
    print(f"  {'Rk':<5} {'Cand':<10} {'DPn':>4} {'#Mo':>4} {'Apps':>5} {'DP Pairs':<25} {'Months':<30} {'W':>3}")
    print(f"  {'-'*90}")
    for p in data['suggested_plays'][:30]:
        wm = "🎯" if p['is_target_winner'] else ""
        sm = "🌱" if p.get('is_seed') else ""
        dp_pairs = ','.join(p.get('dp_shared_pairs', [])[:4])
        ms = ','.join(p.get('months', [])[:3])
        if len(p.get('months', [])) > 3:
            ms += f"+{len(p['months'])-3}"
        label = wm or sm
        print(f"  {p['rank']:<5} {p['candidate']:<10} {p.get('dp_shared_count',0):>4} {p['month_count']:>4} {p['total_appearances']:>5} {dp_pairs:<25} {ms:<30} {label:>3}")

    sep()


def main():
    sep()
    print(f"  REVERSE ENGINEERING: {TARGET} (norm: {TARGET_NORM})")
    sep()

    # Test 1: No DP filter (baseline)
    print(f"\n  >>> Test 1: No DP filter (all 622 candidates)...")
    d1 = run(dp_size=0)
    if d1:
        found = any(w['found_in_candidates'] for w in d1['winner_results'] if w['target_actual'] == TARGET_NORM)
        rank = next((w['rank'] for w in d1['winner_results'] if w['target_actual'] == TARGET_NORM), None)
        total = d1['total_candidates']
        print(f"  No DP: {total} candidates, {'✅' if found else '❌'} Rank #{rank}")

    # Test 2: 2DP on LAST seed only
    print(f"\n  >>> Test 2: 2DP filter on LAST seed (8975)...")
    d2 = run(dp_size=2, dp_seed_mode='last')
    show(d2, "2DP on LAST seed (8975)")

    # Test 3: 3DP on last seed
    print(f"\n  >>> Test 3: 3DP filter on LAST seed...")
    d3 = run(dp_size=3, dp_seed_mode='last')
    if d3:
        found = any(w['found_in_candidates'] for w in d3['winner_results'] if w['target_actual'] == TARGET_NORM)
        rank = next((w['rank'] for w in d3['winner_results'] if w['target_actual'] == TARGET_NORM), None)
        total = d3['total_candidates']
        print(f"  3DP last: {total} candidates, {'✅' if found else '❌'} {f'Rank #{rank}' if rank else ''}")

    # Test 4: 2DP on ALL seeds
    print(f"\n  >>> Test 4: 2DP on ALL seeds...")
    d4 = run(dp_size=2, dp_seed_mode='all')
    if d4:
        found = any(w['found_in_candidates'] for w in d4['winner_results'] if w['target_actual'] == TARGET_NORM)
        rank = next((w['rank'] for w in d4['winner_results'] if w['target_actual'] == TARGET_NORM), None)
        total = d4['total_candidates']
        print(f"  2DP all: {total} candidates, {'✅' if found else '❌'} {f'Rank #{rank}' if rank else ''}")

    # Summary
    print(f"\n")
    sep()
    print(f"  SUMMARY: Candidate pool reduction")
    sep()
    tests = [
        ("No DP filter", d1),
        ("2DP last seed", d2),
        ("3DP last seed", d3),
        ("2DP all seeds", d4),
    ]
    print(f"  {'Config':<20} {'Candidates':>12} {'Found?':>8} {'Rank':>8}")
    print(f"  {'-'*55}")
    for label, d in tests:
        if d:
            found = any(w['found_in_candidates'] for w in d['winner_results'] if w['target_actual'] == TARGET_NORM)
            rank = next((w['rank'] for w in d['winner_results'] if w['target_actual'] == TARGET_NORM and w['rank']), '-')
            print(f"  {label:<20} {d['total_candidates']:>12} {'✅':>8} #{rank}" if found else
                  f"  {label:<20} {d['total_candidates']:>12} {'❌':>8} {'—':>8}")
    sep()


if __name__ == "__main__":
    main()
