#!/usr/bin/env python3
"""
Test True RBTL v2 (Monthly) - Reverse Engineer 9869 on 2019-09-15 Evening
==========================================================================
Uses independent calendar months (like the original MLD spreadsheet).

Run while your app is serving on localhost:5001:
    python3 test_true_rbtl_v2.py
"""

import requests
import json

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

TARGET_NUMBER = "9869"
TARGET_NORMALIZED = "6899"


def sep(char="=", width=90):
    print(char * width)


def run_test(lookback_days=5, top_n_months=5):
    """Run a single true RBTL backtest."""
    url = f"{BASE_URL}/api/rbtl/backtest-v2?db={DB_MODE}"
    payload = {
        "state": "Florida",
        "game_type": "pick4",
        "target_date": "2019-09-15",
        "target_tod": "evening",
        "lookback_days": lookback_days,
        "top_n_clusters": top_n_months,
        "include_same_day": True,
        "suggested_limit": 100
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code != 200:
            print(f"ERROR: HTTP {resp.status_code}")
            try:
                err = resp.json()
                print(f"  {err.get('error', resp.text[:300])}")
            except:
                print(f"  {resp.text[:300]}")
            return None
        return resp.json()
    except requests.exceptions.ConnectionError:
        print("ERROR: Connection refused - is the app running on localhost:5001?")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def display_results(data):
    if not data:
        return

    sep()
    print(f"  TRUE RBTL v2 — Monthly Grouping (like MLD)")
    sep()

    print(f"\n  Target: {data['target_date']} {data['target_tod']}")
    print(f"  Lookback: {data['lookback_period']} ({data['lookback_days']} days)")
    print(f"  Data cutoff: {data.get('data_cutoff', '?')} — {data.get('data_cutoff_note', '')}")
    print(f"  Top months used: {data.get('top_n_months', '?')}")

    print(f"\n  SEEDS ({data['seed_count']}): {', '.join(data['seed_values'])}")
    print(f"  Historical hits: {data['historical_hit_count']} | Total hot months: {data.get('total_hot_months', '?')}")

    top_months = data.get('top_months', [])
    print(f"\n  HOT MONTHS TABLE:")
    print(f"  {'#':<4} {'Month':<10} {'Count':>6} {'Uniq':>5} {'Draws':>6} {'Rptd':>5}  {'Inputs':<40} {'Repeated (first 8)'}")
    print(f"  {'-'*130}")

    for m in top_months:
        inputs = ' '.join(m.get('input_values', [])[:6])
        if len(m.get('input_values', [])) > 6:
            inputs += f" +{len(m['input_values'])-6}"
        repeated = ' '.join(m.get('repeated_values', [])[:8])
        r_count = m.get('repeated_count', 0)
        has_target = any(TARGET_NORMALIZED == ''.join(sorted(v)) for v in m.get('repeated_values', []))
        mark = " 🎯" if has_target else ""
        print(f"  {m['rank']:<4} {m['month']:<10} {m['count']:>6} {m['unique_seeds']:>5} {m['total_draws']:>6} {r_count:>5}  {inputs:<40} {repeated}{mark}")

    print(f"\n  Total candidates: {data['total_candidates']}")

    print(f"\n  TARGET WINNERS:")
    sep("-", 90)
    for w in data['winner_results']:
        status = "✅ FOUND" if w['found_in_candidates'] else "❌ MISS"
        rank_str = f"Rank #{w['rank']} of {w['total_candidates']}" if w['rank'] else "Not in candidates"
        months_str = ', '.join(w.get('months', []))
        print(f"  {status}  {w['target_value']} (norm: {w['target_actual']}) {w['target_tod']}")
        print(f"         {rank_str} ({w['total_appearances']} apps)")
        if months_str:
            print(f"         Found in: {months_str}")
    sep("-", 90)
    print(f"  HIT RATE: {data['hit_rate']}% ({data['winners_found']}/{data['target_winner_count']})")

    print(f"\n  TOP 30 PLAYS:")
    print(f"  {'Rank':<6} {'Cand':<10} {'#Mo':>4} {'Apps':>5} {'Months':<35} {'Seed':>5} {'Win':>4}")
    print(f"  {'-'*80}")
    for play in data['suggested_plays'][:30]:
        wm = "🎯" if play['is_target_winner'] else ""
        sm = "🌱" if play.get('is_seed') else ""
        ms = ', '.join(play.get('months', [])[:4])
        if len(play.get('months', [])) > 4:
            ms += f"+{len(play['months'])-4}"
        print(f"  {play['rank']:<6} {play['candidate']:<10} {play['month_count']:>4} {play['total_appearances']:>5} {ms:<35} {sm:>5} {wm:>4}")
    sep()
    return data


def main():
    sep()
    print(f"  REVERSE ENGINEERING: {TARGET_NUMBER} (norm: {TARGET_NORMALIZED})")
    print(f"  Monthly grouping — matching original MLD process")
    sep()

    configs = [
        (5, 5),
        (5, 10),
        (5, 15),
        (5, 20),
    ]

    best_rank = None
    best_label = None

    for lookback, top_n in configs:
        label = f"{lookback}d / top {top_n} months"
        print(f"\n  >>> Running: {label}...")
        data = run_test(lookback_days=lookback, top_n_months=top_n)
        if data:
            display_results(data)
            for w in data.get('winner_results', []):
                if w['target_actual'] == TARGET_NORMALIZED and w['rank']:
                    if best_rank is None or w['rank'] < best_rank:
                        best_rank = w['rank']
                        best_label = label

    print(f"\n{'='*90}")
    if best_rank:
        print(f"  🏆 BEST: {best_label} → {TARGET_NUMBER} at Rank #{best_rank}")
    else:
        print(f"  ❌ {TARGET_NUMBER} not found in any config")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
