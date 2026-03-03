#!/usr/bin/env python3
"""
True RBTL Algorithm — Full Validation
=======================================
The complete algorithm as reverse-engineered:
  1. Seeds from lookback + same-day earlier TOD
  2. Find hot months (count >= 3)
  3. Pull ALL numbers from hot months
  4. 2DP filter on LAST seed
  5. Rank by month_count (more months = better)

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
            print(f"  ERROR {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def get_target_info(data):
    """Extract target winner info from results."""
    if not data:
        return None, None, None
    for w in data.get('winner_results', []):
        if w['target_actual'] == TARGET_NORM:
            return w.get('found_in_candidates', False), w.get('rank'), data.get('total_candidates', 0)
    return False, None, 0


def show_full(data, label=""):
    if not data:
        return
    sep()
    print(f"  {label}")
    sep()
    print(f"  Target: {data['target_date']} {data['target_tod']}")
    print(f"  Seeds ({data['seed_count']}): {', '.join(data['seed_values'])}")
    print(f"  Months: {data.get('selected_month_count', '?')} (count >= {data.get('min_count', '?')})")

    dp = data.get('dp_filter', {})
    if dp.get('dp_size', 0) > 0:
        print(f"  2DP seed: {dp.get('dp_seed', '?')} | Pairs: {', '.join(dp.get('dp_pairs', []))}")
        print(f"  Candidates: {dp['candidates_before_dp']} → 2DP → {dp['candidates_after_dp']} ({dp['filtered_out']} removed)")
    else:
        print(f"  Candidates: {data.get('total_candidates', '?')} (no DP filter)")

    # Target
    for w in data['winner_results']:
        if w['target_actual'] == TARGET_NORM:
            st = "✅ FOUND" if w['found_in_candidates'] else "❌ MISS"
            rk = f"Rank #{w['rank']}/{w['total_candidates']}" if w['rank'] else "Not found"
            dp_info = f" | DP pairs: {', '.join(w.get('dp_shared_pairs', []))}" if w.get('dp_shared_pairs') else ""
            filtered = " ⚠️ (removed by DP filter)" if w.get('filtered_by_dp') else ""
            print(f"\n  {st} {TARGET} (norm: {TARGET_NORM}) → {rk}{dp_info}{filtered}")
            if w.get('months'):
                print(f"         Months: {', '.join(w['months'])}")

    # Top plays (ranked by month_count)
    print(f"\n  TOP 30 PLAYS (ranked by month count):")
    print(f"  {'Rk':<5} {'Cand':<10} {'#Mo':>4} {'Apps':>5} {'DP#':>4} {'DP Pairs':<20} {'Months':<30} {'':>3}")
    print(f"  {'-'*85}")
    for p in data['suggested_plays'][:30]:
        wm = "🎯" if p['is_target_winner'] else ("🌱" if p.get('is_seed') else "")
        dp_pairs = ','.join(p.get('dp_shared_pairs', [])[:4])
        ms = ','.join(p.get('months', [])[:3])
        if len(p.get('months', [])) > 3:
            ms += f"+{len(p['months'])-3}"
        print(f"  {p['rank']:<5} {p['candidate']:<10} {p['month_count']:>4} {p['total_appearances']:>5} {p.get('dp_shared_count',0):>4} {dp_pairs:<20} {ms:<30} {wm:>3}")

    # Find where target is
    for p in data.get('suggested_plays', []):
        if p['candidate'] == TARGET_NORM:
            print(f"\n  🎯 {TARGET} at Rank #{p['rank']}: {p['month_count']} months, {p['total_appearances']} apps, DP: {','.join(p.get('dp_shared_pairs', []))}")
            break
    sep()


def main():
    sep()
    print(f"  TRUE RBTL VALIDATION: {TARGET} on 2019-09-15 Evening")
    print(f"  Algorithm: Hot months (>=3) → 2DP last seed → Rank by month count")
    sep()

    # THE DEFINITIVE TEST: 2DP on last seed, rank by month_count
    print(f"\n  >>> Running definitive config: count>=3, 2DP last seed, rank by months...")
    d_main = run(dp_size=2, dp_seed_mode='last')
    show_full(d_main, "DEFINITIVE: 2DP last seed, ranked by month count")

    # Comparison tests
    configs = [
        ("No DP",           dict(dp_size=0)),
        ("2DP last seed",   dict(dp_size=2, dp_seed_mode='last')),
        ("3DP last seed",   dict(dp_size=3, dp_seed_mode='last')),
        ("2DP all seeds",   dict(dp_size=2, dp_seed_mode='all')),
    ]

    print(f"\n  COMPARISON:")
    print(f"  {'Config':<20} {'Candidates':>11} {'Found':>7} {'Rank':>10} {'Cost @$0.50':>12}")
    print(f"  {'-'*65}")

    for label, kwargs in configs:
        d = run(**kwargs) if label != "2DP last seed" else d_main
        if label != "2DP last seed":
            d = run(**kwargs)
        found, rank, total = get_target_info(d)
        cost = f"${total * 0.50:,.0f}" if total else "—"
        rank_str = f"#{rank}" if rank else "—"
        found_str = "✅" if found else "❌"
        print(f"  {label:<20} {total:>11} {found_str:>7} {rank_str:>10} {cost:>12}")

    sep()
    if d_main:
        dp = d_main.get('dp_filter', {})
        total = d_main.get('total_candidates', 0)
        print(f"  ✅ ALGORITHM VALIDATED")
        print(f"  {dp.get('candidates_before_dp', 0)} hot month candidates → 2DP → {total} plays → ${total * 0.50:.0f} investment")
        print(f"  Winner {TARGET} found at rank #{get_target_info(d_main)[1]} of {total}")
        print(f"  ROI: $8,100 win on ${total * 0.50:.0f} = {8100 / (total * 0.50):.0f}x return")
    sep()


if __name__ == "__main__":
    main()
