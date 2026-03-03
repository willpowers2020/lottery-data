"""
Cluster Year Debug Script
===========================
Tests cluster_year grouping against Win #2 scenario
and compares to what MLD produces.

Run: python3 test_cluster_year.py
"""

import requests, json, sys

def prompt(msg, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{msg}{suffix}: ").strip()
    return val if val else default

def api_url(base, path, db):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

def main():
    print("=" * 70)
    print("  🔬 CLUSTER_YEAR DEBUG — Win #2 Scenario")
    print("=" * 70)

    base = prompt("Flask app URL", "http://localhost:5001")
    db = prompt("DB mode", "mongo_v2")

    # Win #2 params
    target_date = "2019-10-09"
    target_tod = "midday"
    state = "Florida"
    game_type = "pick4"

    # Test all groupings
    GROUPINGS = ["monthly", "cluster_30", "cluster_60", "cluster_year"]
    MIN_COUNTS = [1, 2, 3]
    DP_SIZES = [0, 2]

    print(f"\n  Target: {state} {game_type} {target_date} {target_tod}")
    print(f"  Profile: Shadow (lookback=-1, 2 seeds)")
    print()

    results = []

    for grouping in GROUPINGS:
        print(f"  --- {grouping.upper()} ---")
        for mc in MIN_COUNTS:
            for dp in DP_SIZES:
                body = {
                    "state": state,
                    "game_type": game_type,
                    "target_date": target_date,
                    "target_tod": target_tod,
                    "lookback_days": -1,  # Shadow mode (mid+eve)
                    "min_count": mc,
                    "dp_size": dp,
                    "dp_seed_mode": "last",
                    "suggested_limit": 999,
                    "include_same_day": True,
                    "look_forward_days": 0,
                    "grouping": grouping,
                }

                try:
                    r = requests.post(api_url(base, "/api/rbtl/backtest-v2", db),
                                     json=body, timeout=60)
                    data = r.json()

                    if data.get("error"):
                        print(f"    mc≥{mc} dp={dp}: ERROR — {data['error']}")
                        continue

                    plays = data.get("suggested_plays", [])
                    winners = data.get("target_winners", [])
                    winner_results = data.get("winner_results", [])
                    top_months = data.get("top_months", [])
                    seeds = data.get("seed_values", [])
                    hot_count = data.get("selected_month_count", 0)
                    total_hot = data.get("total_hot_months", 0)
                    pre_dp = data.get("total_candidates_pre_dp", 0)
                    actual_grouping = data.get("grouping", "?")

                    # Find winner
                    winner_found = False
                    winner_rank = 0
                    for wr in winner_results:
                        if wr.get("found_in_candidates"):
                            winner_found = True
                            winner_rank = wr.get("rank", 0)

                    status = f"✅ #{winner_rank}" if winner_found else "❌"
                    print(f"    mc≥{mc} dp={dp}: {status} | {len(plays)} candidates "
                          f"(pre-DP: {pre_dp}) | {hot_count}/{total_hot} hot groups | "
                          f"grouping={actual_grouping}")

                    # Show hot groups for cluster_year
                    if grouping == "cluster_year" and mc == 2 and dp == 0:
                        print(f"\n    📋 DETAIL for cluster_year mc≥2 dp=0:")
                        print(f"    Seeds: {seeds}")
                        print(f"    Hot years ({len(top_months)}):")
                        for m in top_months[:10]:
                            print(f"      {m.get('month', '?')}: count={m.get('count', 0)}, "
                                  f"inputs={m.get('input_values', [])[:5]}")

                        if winner_results:
                            wr = winner_results[0]
                            print(f"\n    Winner: {wr.get('target_actual', '?')}")
                            print(f"    Found: {wr.get('found_in_candidates', False)}")
                            print(f"    Rank: {wr.get('rank', 'N/A')}")
                            print(f"    In groups: {wr.get('months', [])}")
                            print(f"    Filter reason: {wr.get('filter_reason', 'N/A')}")
                            print(f"    Total appearances: {wr.get('total_appearances', 0)}")
                        print()

                    # Also show detail for monthly mc≥1 dp=0
                    if grouping == "monthly" and mc == 1 and dp == 0:
                        print(f"\n    📋 DETAIL for monthly mc≥1 dp=0:")
                        print(f"    Seeds: {seeds}")
                        print(f"    Hot months ({len(top_months)}):")
                        for m in top_months[:10]:
                            print(f"      {m.get('month', '?')}: count={m.get('count', 0)}")

                        if winner_results:
                            wr = winner_results[0]
                            print(f"\n    Winner: {wr.get('target_actual', '?')}")
                            print(f"    Found: {wr.get('found_in_candidates', False)}")
                            print(f"    In months: {wr.get('months', [])}")
                            print(f"    Filter reason: {wr.get('filter_reason', 'N/A')}")
                        print()

                    results.append({
                        "grouping": grouping, "mc": mc, "dp": dp,
                        "found": winner_found, "rank": winner_rank,
                        "candidates": len(plays), "pre_dp": pre_dp,
                        "hot_groups": hot_count,
                    })

                except Exception as e:
                    print(f"    mc≥{mc} dp={dp}: EXCEPTION — {e}")

    # Summary comparison
    print("\n" + "=" * 70)
    print("  📊 SUMMARY — Smallest playable lists with winner")
    print("=" * 70)

    found = [r for r in results if r["found"]]
    found.sort(key=lambda r: r["candidates"])

    if found:
        print(f"\n  {'Grouping':<16}{'mc':<6}{'DP':<5}{'Rank':<8}{'List':<8}{'Cost'}")
        print("  " + "-" * 50)
        for r in found[:15]:
            print(f"  {r['grouping']:<16}≥{r['mc']:<5}{r['dp']:<5}#{r['rank']:<7}"
                  f"{r['candidates']:<8}${r['candidates']}")
    else:
        print("\n  ❌ Winner not found in any combination!")

    # Key insight
    print("\n" + "=" * 70)
    print("  💡 ANALYSIS")
    print("=" * 70)

    cy_results = [r for r in results if r["grouping"] == "cluster_year"]
    m_results = [r for r in results if r["grouping"] == "monthly"]

    cy_found = [r for r in cy_results if r["found"]]
    m_found = [r for r in m_results if r["found"]]

    if cy_found:
        best_cy = min(cy_found, key=lambda r: r["candidates"])
        print(f"\n  Best cluster_year: {best_cy['candidates']} candidates "
              f"(mc≥{best_cy['mc']}, dp={best_cy['dp']}, rank #{best_cy['rank']})")
    else:
        print("\n  ❌ cluster_year never found the winner")
        # Check if it's a DP filter issue
        cy_no_dp = [r for r in cy_results if r["dp"] == 0]
        if cy_no_dp:
            print(f"    Even without DP filter, best was {cy_no_dp[0]['candidates']} candidates")

    if m_found:
        best_m = min(m_found, key=lambda r: r["candidates"])
        print(f"  Best monthly: {best_m['candidates']} candidates "
              f"(mc≥{best_m['mc']}, dp={best_m['dp']}, rank #{best_m['rank']})")

    print(f"\n  MLD manual selection gave 22 candidates")
    print(f"  (by selecting ONLY 2013-03 + 2013-10 from the Hots tab)")

    if cy_found and cy_found[0]["candidates"] > 22:
        print(f"\n  ⚠️  cluster_year gives more candidates because it pulls ALL draws")
        print(f"  from the entire year, not just the months with seed hits.")
        print(f"  MLD's 22 = intersection of 'Repeated' numbers from those 2 months only.")
        print(f"\n  Possible fix: Instead of pulling ALL draws from the year,")
        print(f"  only pull draws from the SPECIFIC MONTHS that had seed hits")
        print(f"  within the qualifying year. This would match MLD behavior.")

    print(f"\n  Done! 🎉")


if __name__ == "__main__":
    main()
