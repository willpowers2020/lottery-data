#!/usr/bin/env python3
"""
Test True RBTL v2 — Matching Exact MLD Process
================================================
Seeds: 2398 1594 5489 0094 0201 9552 1704 1876 8975
All months with count >= 3 selected (like MLD blue checkboxes)
All numbers from those months = candidate pool

Target: 9869 on 2019-09-15 Evening

python3 test_true_rbtl_v2.py
"""

import requests

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

TARGET = "9869"
TARGET_NORM = "6899"


def sep(c="=", w=90):
    print(c * w)


def run(lookback_days=5, min_count=3, top_n=0):
    url = f"{BASE_URL}/api/rbtl/backtest-v2?db={DB_MODE}"
    payload = {
        "state": "Florida",
        "game_type": "pick4",
        "target_date": "2019-09-15",
        "target_tod": "evening",
        "lookback_days": lookback_days,
        "min_count": min_count,
        "top_n_clusters": top_n,  # 0 = all qualifying months
        "include_same_day": True,
        "suggested_limit": 200
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


def show(data):
    if not data:
        return

    sep()
    print(f"  TRUE RBTL v2 — Exact MLD Process")
    sep()
    print(f"  Target: {data['target_date']} {data['target_tod']}")
    print(f"  Lookback: {data['lookback_period']} ({data['lookback_days']}d)")
    print(f"  Data cutoff: {data.get('data_cutoff', '?')}")
    print(f"  Min count: >= {data.get('min_count', '?')}")
    print(f"  Months used: {data.get('selected_month_count', '?')} of {data.get('total_hot_months', '?')} total")

    print(f"\n  SEEDS ({data['seed_count']}): {', '.join(data['seed_values'])}")
    print(f"  Historical hits: {data['historical_hit_count']}")

    # Hot months
    months = data.get('top_months', [])
    print(f"\n  HOT MONTHS ({len(months)}):")
    print(f"  {'#':<4} {'Month':<10} {'Cnt':>4} {'Uniq':>5} {'Draws':>6} {'Rptd':>5}  {'Inputs':<35} {'R.count'}")
    print(f"  {'-'*100}")
    for m in months[:30]:  # Show first 30
        inputs = ' '.join(m.get('input_values', [])[:5])
        if len(m.get('input_values', [])) > 5:
            inputs += f" +{len(m['input_values'])-5}"
        r_count = m.get('repeated_count', 0)

        # Check if target is in this month's repeated
        has_target = False
        for v in m.get('repeated_values', []):
            if ''.join(sorted(v)) == TARGET_NORM:
                has_target = True
                break
        mark = " 🎯 ← TARGET HERE" if has_target else ""

        print(f"  {m['rank']:<4} {m['month']:<10} {m['count']:>4} {m['unique_seeds']:>5} {m['total_draws']:>6} {r_count:>5}  {inputs:<35} {r_count}{mark}")

    if len(months) > 30:
        print(f"  ... +{len(months)-30} more months")

    # Candidates
    print(f"\n  TOTAL CANDIDATES: {data['total_candidates']}")

    # Target
    print(f"\n  TARGET WINNER:")
    sep("-", 90)
    for w in data['winner_results']:
        st = "✅ FOUND" if w['found_in_candidates'] else "❌ MISS"
        rk = f"Rank #{w['rank']} of {w['total_candidates']}" if w['rank'] else "Not in candidates"
        ms = ', '.join(w.get('months', []))
        print(f"  {st}  {w['target_value']} (norm: {w['target_actual']}) {w['target_tod']}")
        print(f"         {rk} ({w['total_appearances']} appearances)")
        if ms:
            print(f"         Found in months: {ms}")
    sep("-", 90)
    print(f"  HIT RATE: {data['hit_rate']}%")

    # Show where target ranks
    for p in data.get('suggested_plays', []):
        if p['candidate'] == TARGET_NORM:
            print(f"\n  🎯 TARGET in suggested plays: Rank #{p['rank']}, in {p['month_count']} months: {', '.join(p.get('months', []))}")
            break

    sep()


def main():
    sep()
    print(f"  REVERSE ENGINEERING: {TARGET} (norm: {TARGET_NORM})")
    print(f"  Matching EXACT MLD process: all months with count >= 3")
    sep()

    # Test 1: Exact MLD match — all months with count >= 3
    print(f"\n  >>> Test 1: All months with count >= 3 (MLD default)...")
    data = run(lookback_days=5, min_count=3, top_n=0)
    show(data)

    # Test 2: Stricter — count >= 4
    print(f"\n  >>> Test 2: Count >= 4 (stricter)...")
    data2 = run(lookback_days=5, min_count=4, top_n=0)
    if data2:
        found = any(w['found_in_candidates'] for w in data2['winner_results'] if w['target_actual'] == TARGET_NORM)
        cands = data2['total_candidates']
        months = data2.get('selected_month_count', '?')
        print(f"  min_count>=4: {months} months, {cands} candidates, {'✅' if found else '❌'}")

    # Test 3: Even stricter — count >= 5
    print(f"\n  >>> Test 3: Count >= 5...")
    data3 = run(lookback_days=5, min_count=5, top_n=0)
    if data3:
        found = any(w['found_in_candidates'] for w in data3['winner_results'] if w['target_actual'] == TARGET_NORM)
        cands = data3['total_candidates']
        months = data3.get('selected_month_count', '?')
        print(f"  min_count>=5: {months} months, {cands} candidates, {'✅' if found else '❌'}")

    # Summary
    sep()
    print(f"  KEY QUESTION: With {data['total_candidates'] if data else '?'} candidates,")
    print(f"  is that comparable to MLD's 1,389 count?")
    print(f"  (MLD counted all permutations, we count unique normalized forms)")
    sep()


if __name__ == "__main__":
    main()
