"""
2026 Cluster Effectiveness Report (Detailed)
==============================================
Tests whether cluster grouping finds winners that monthly grouping misses.
Shows full cluster details, winner info, seeds, and filter reasons.

Run:  python3 cluster_report_2026.py
"""

import requests, json, sys, csv
from datetime import datetime, timedelta

def prompt(msg, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{msg}{suffix}: ").strip()
    return val if val else default

def api_url(base, path, db):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

def run_backtest(base, db, body):
    try:
        r = requests.post(api_url(base, "/api/rbtl/backtest-v2", db), json=body, timeout=60)
        data = r.json()
        if data.get("error"):
            return None, data["error"]
        return data, None
    except Exception as e:
        return None, str(e)

def main():
    print("=" * 70)
    print("  📊 2026 CLUSTER EFFECTIVENESS REPORT (Detailed)")
    print("=" * 70)
    print()

    # --- Connection ---
    base = prompt("Flask app URL", "http://localhost:5001")
    db = prompt("DB mode", "mongo_v2")

    # --- Game setup ---
    print()
    state = prompt("State (full name)", "Florida")
    game_type = prompt("Game type (pick3 / pick4)", "pick4")
    start_date = prompt("Report start date", "2026-01-01")
    end_date = prompt("Report end date", "2026-02-18")
    tod_filter = prompt("TOD to test (evening / midday / both)", "both")
    profile = prompt("Profile: 1=Sniper, 2=WideNet, 3=Shadow", "1")
    pw_days = int(prompt("Past window days for seeds", "5"))

    # Profile config
    if profile == "1":
        dp_size = 2
        seed_count = 1
        lookback = 0
        profile_name = "Sniper"
    elif profile == "2":
        dp_size = 2
        seed_count = 99
        lookback = None
        profile_name = "Wide Net"
    elif profile == "3":
        dp_size = 0
        seed_count = 2
        lookback = -1
        profile_name = "Shadow"
    else:
        dp_size = 2
        seed_count = 1
        lookback = 0
        profile_name = "Custom"

    # Which groupings and min_counts to test
    # Focus on the most useful combos
    GROUPINGS = ["monthly", "cluster_15", "cluster_30", "cluster_60"]
    MIN_COUNTS = [1, 2, 3]

    tods_to_test = ["evening", "midday"] if tod_filter == "both" else [tod_filter]

    # --- Get all draws in range to use as targets ---
    print(f"\n⏳ Loading all draws from {start_date} to {end_date}...")
    try:
        r = requests.post(api_url(base, "/api/draws/recent", db), json={
            "state": state, "game_type": game_type,
            "start_date": start_date, "end_date": end_date
        }, timeout=15)
        all_draws = r.json().get("draws", [])
    except Exception as e:
        print(f"❌ Failed: {e}")
        return

    if not all_draws:
        print("❌ No draws found in range")
        return

    # Filter to requested TODs
    targets = []
    for d in all_draws:
        dtod = (d.get("tod") or "").lower()
        if dtod in tods_to_test:
            targets.append(d)

    targets.sort(key=lambda d: (d["date"], d.get("tod", "")))
    print(f"📋 Found {len(targets)} target draws to test")
    print(f"   Profile: {profile_name} | DP: {dp_size} | Seed window: {pw_days} days")

    # --- Run backtests ---
    # For the detailed report, we run cluster_30 at mc≥1,2,3 for each target
    # plus monthly at mc≥1 for comparison
    # This gives us the full picture without 1000+ API calls
    DETAIL_GROUPINGS = ["monthly", "cluster_30"]
    DETAIL_MCS = [1, 2, 3]

    all_results = []       # for aggregate stats (all combos)
    detail_results = []    # for detailed per-draw report

    total_tests = len(targets) * len(GROUPINGS) * len(MIN_COUNTS)
    test_num = 0

    print(f"\n{'=' * 70}")
    print(f"⏳ Running {total_tests} backtests...")
    print("=" * 70)

    for ti, target in enumerate(targets):
        tdate = target["date"]
        ttod = (target.get("tod") or "").lower()
        tactual = target.get("actual", "?")

        draw_detail = {
            "date": tdate,
            "tod": ttod,
            "actual": tactual,
            "results": {}
        }

        for grouping in GROUPINGS:
            for mc in MIN_COUNTS:
                test_num += 1
                sys.stdout.write(f"\r  [{test_num}/{total_tests}] {tdate} {ttod} {grouping} mc≥{mc}...          ")
                sys.stdout.flush()

                body = {
                    "state": state,
                    "game_type": game_type,
                    "target_date": tdate,
                    "target_tod": ttod,
                    "lookback_days": lookback if lookback is not None else pw_days,
                    "min_count": mc,
                    "dp_size": dp_size,
                    "dp_seed_mode": "last",
                    "suggested_limit": 999,
                    "include_same_day": True,
                    "look_forward_days": 0,
                    "grouping": grouping,
                }

                data, err = run_backtest(base, db, body)

                result = {
                    "date": tdate, "tod": ttod, "actual": tactual,
                    "grouping": grouping, "min_count": mc,
                }

                if err or data is None:
                    result["found"] = False
                    result["error"] = err or "no data"
                    all_results.append(result)
                    draw_detail["results"][(grouping, mc)] = result
                    continue

                plays = data.get("suggested_plays", [])
                winners = data.get("target_winners", [])
                winner_results = data.get("winner_results", [])
                top_months = data.get("top_months", [])
                seed_values = data.get("seed_values", [])
                seed_actuals = data.get("seed_actuals", [])

                # Extract cluster/month details
                clusters_info = []
                for m in top_months:
                    clusters_info.append({
                        "label": m.get("month", "?"),
                        "count": m.get("count", 0),
                    })

                # Find winner in candidates
                winner_found = False
                winner_info = {}
                for wr in winner_results:
                    if wr.get("found_in_candidates"):
                        winner_found = True
                        winner_info = {
                            "rank": wr.get("rank", 0),
                            "total_candidates": wr.get("total_candidates", len(plays)),
                            "total_appearances": wr.get("total_appearances", 0),
                            "months": wr.get("months", []),
                            "dp_pairs": wr.get("dp_shared_pairs", []),
                            "value": wr.get("target_value", ""),
                            "actual": wr.get("target_actual", ""),
                        }
                        break
                    else:
                        winner_info = {
                            "filter_reason": wr.get("filter_reason", ""),
                            "months": wr.get("months", []),
                            "total_appearances": wr.get("total_appearances", 0),
                            "value": wr.get("target_value", ""),
                            "actual": wr.get("target_actual", ""),
                        }

                # Also check suggested_plays directly (fallback)
                if not winner_found:
                    for w in winners:
                        wval = w.get("value", "")
                        wnorm = "".join(sorted(wval.replace("-", "")))
                        for idx, p in enumerate(plays):
                            if p["candidate"] == wnorm:
                                winner_found = True
                                winner_info = {
                                    "rank": idx + 1,
                                    "total_candidates": len(plays),
                                    "total_appearances": p.get("total_appearances", 0),
                                    "months": p.get("months", []),
                                    "dp_pairs": p.get("dp_shared_pairs", []),
                                    "value": wval,
                                    "actual": w.get("actual", wval),
                                }
                                break
                        if winner_found:
                            break

                result["found"] = winner_found
                result["winner"] = winner_info
                result["seeds"] = seed_values
                result["seed_actuals"] = seed_actuals
                result["clusters"] = clusters_info
                result["total_candidates"] = len(plays)
                result["hot_groups"] = len(top_months)
                result["total_hot_groups"] = data.get("total_hot_months", 0)

                if winner_found:
                    result["rank"] = winner_info.get("rank", 0)
                    result["total_hits"] = winner_info.get("total_appearances", 0)
                    result["winner_groups"] = winner_info.get("months", [])

                all_results.append(result)
                draw_detail["results"][(grouping, mc)] = result

        detail_results.append(draw_detail)

    print(f"\r  ✅ Completed {test_num} backtests across {len(targets)} draws                         ")

    # ===========================
    # AGGREGATE STATS
    # ===========================
    print("\n" + "=" * 70)
    print("  📈 AGGREGATE RESULTS")
    print("=" * 70)

    print(f"\n  {'Grouping':<14}{'mc':<6}{'Hit Rate':<14}{'Avg Rank':<12}{'Avg List':<12}{'Best Rank':<12}")
    print("  " + "-" * 68)

    best_combo = None
    best_score = 999999

    for grouping in GROUPINGS:
        for mc in MIN_COUNTS:
            subset = [r for r in all_results if r["grouping"] == grouping and r["min_count"] == mc]
            hits = [r for r in subset if r.get("found")]
            total = len(subset)
            errors = len([r for r in subset if r.get("error")])

            if total - errors == 0:
                continue

            hit_rate = len(hits) / (total - errors) * 100
            avg_rank = sum(r["rank"] for r in hits) / len(hits) if hits else 0
            avg_list = sum(r.get("total_candidates", 0) for r in hits) / len(hits) if hits else 0
            best_rank = min(r["rank"] for r in hits) if hits else 0

            print(f"  {grouping:<14}≥{mc:<5}{hit_rate:>5.1f}% ({len(hits)}/{total-errors})"
                  f"{'':>2}{avg_rank:>6.1f}{'':>5}{avg_list:>6.0f}{'':>7}#{best_rank}")

            if hits:
                score = (100 - hit_rate) * 10 + avg_rank + avg_list * 0.1
                if score < best_score:
                    best_score = score
                    best_combo = (grouping, mc, hit_rate, avg_rank, avg_list, len(hits))

    if best_combo:
        print(f"\n  🏆 BEST COMBO: {best_combo[0]} at mc≥{best_combo[1]}")
        print(f"     Hit rate: {best_combo[2]:.1f}%, Avg rank: {best_combo[3]:.1f}, Avg list: {best_combo[4]:.0f}")

    # ===========================
    # HEAD-TO-HEAD
    # ===========================
    print("\n" + "=" * 70)
    print("  🥊 CLUSTER vs MONTHLY HEAD-TO-HEAD")
    print("=" * 70)

    for mc in [2, 3]:
        monthly_found = 0
        cluster_found = 0
        cluster_only = 0
        monthly_only = 0
        both_found = 0
        cluster_better_rank = 0

        for target in targets:
            tdate = target["date"]
            ttod = (target.get("tod") or "").lower()

            m_result = next((r for r in all_results if r["date"] == tdate and r["tod"] == ttod
                           and r["grouping"] == "monthly" and r["min_count"] == mc), None)
            m_found = m_result and m_result.get("found", False)
            if m_found:
                monthly_found += 1

            c_results = [r for r in all_results if r["date"] == tdate and r["tod"] == ttod
                        and r["grouping"].startswith("cluster") and r["min_count"] == mc
                        and r.get("found")]
            c_found = len(c_results) > 0
            if c_found:
                cluster_found += 1

            if c_found and not m_found:
                cluster_only += 1
            elif m_found and not c_found:
                monthly_only += 1
            elif m_found and c_found:
                both_found += 1
                best_c = min(c_results, key=lambda r: r["rank"])
                if best_c["rank"] < m_result["rank"]:
                    cluster_better_rank += 1

        print(f"\n  At mc≥{mc}:")
        print(f"    Monthly finds winner:  {monthly_found}/{len(targets)} draws")
        print(f"    Cluster finds winner:  {cluster_found}/{len(targets)} draws")
        print(f"    Cluster SAVES winner:  {cluster_only} draws")
        print(f"    Monthly SAVES winner:  {monthly_only} draws")
        print(f"    Both find, cluster ranks higher: {cluster_better_rank}/{both_found}")

    # ===========================
    # DETAILED PER-DRAW REPORT
    # ===========================
    print("\n" + "=" * 70)
    print("  📋 DETAILED PER-DRAW REPORT")
    print("  Showing cluster_30 results with full details")
    print("=" * 70)

    for dd in detail_results:
        tdate = dd["date"]
        ttod = dd["tod"]
        tactual = dd["actual"]

        # Get the best cluster_30 result (highest mc where winner found)
        best_c30 = None
        for mc in reversed(DETAIL_MCS):
            r = dd["results"].get(("cluster_30", mc))
            if r and r.get("found"):
                best_c30 = r
                break

        # Also get monthly mc≥1 for comparison
        monthly_r = dd["results"].get(("monthly", 1))

        # Also get cluster_30 mc≥1 for full cluster info
        c30_base = dd["results"].get(("cluster_30", 1))

        print(f"\n  {'─' * 66}")
        print(f"  📅 {tdate} {ttod.upper()}")
        print(f"  🏆 Winner: {tactual}")

        # Seeds
        if c30_base and c30_base.get("seeds"):
            seed_str = ", ".join(c30_base["seeds"])
            print(f"  🌱 Seeds: {seed_str}")

        # Monthly result
        if monthly_r:
            if monthly_r.get("found"):
                w = monthly_r["winner"]
                print(f"  📅 Monthly mc≥1: ✅ rank #{w.get('rank','?')}/{monthly_r.get('total_candidates','?')}, "
                      f"hits={w.get('total_appearances','?')}, "
                      f"in groups: {', '.join(w.get('months', []))}")
            else:
                print(f"  📅 Monthly mc≥1: ❌ not in {monthly_r.get('total_candidates','?')} candidates")

        # Cluster results at each mc
        for mc in DETAIL_MCS:
            r = dd["results"].get(("cluster_30", mc))
            if not r:
                continue
            if r.get("found"):
                w = r["winner"]
                grps = w.get("months", [])
                print(f"  🔷 cluster_30 mc≥{mc}: ✅ rank #{w.get('rank','?')}/{r.get('total_candidates','?')}, "
                      f"hits={w.get('total_appearances','?')}, "
                      f"in {len(grps)} cluster(s)")
                for g in grps:
                    print(f"       └─ {g}")
            else:
                reason = ""
                if r.get("winner") and r["winner"].get("filter_reason"):
                    reason = f" — {r['winner']['filter_reason']}"
                print(f"  🔷 cluster_30 mc≥{mc}: ❌ ({r.get('total_candidates','?')} candidates){reason}")

        # Show cluster landscape
        if c30_base and c30_base.get("clusters"):
            clusters = c30_base["clusters"]
            if clusters:
                top5 = sorted(clusters, key=lambda c: c["count"], reverse=True)[:5]
                labels = [f"{c['label']} ({c['count']} hits)" for c in top5]
                print(f"  🔥 Top clusters (mc≥1): {', '.join(labels)}")
                print(f"     {c30_base.get('hot_groups',0)} qualified / {c30_base.get('total_hot_groups',0)} total hot clusters")

    # ===========================
    # HIGHLIGHT: BEST FINDS
    # ===========================
    print("\n" + "=" * 70)
    print("  ⭐ TOP 10 BEST CLUSTER FINDS (smallest list with winner)")
    print("=" * 70)

    cluster_hits = [r for r in all_results
                   if r.get("found") and r["grouping"].startswith("cluster") and r["min_count"] >= 2]
    cluster_hits.sort(key=lambda r: (r.get("total_candidates", 9999), r.get("rank", 9999)))

    print(f"\n  {'Date':<12}{'TOD':<8}{'Winner':<8}{'Grouping':<14}{'mc':<5}{'Rank':<8}{'List':<8}{'Hits'}")
    print("  " + "-" * 70)
    for r in cluster_hits[:10]:
        w = r.get("winner", {})
        print(f"  {r['date']:<12}{r['tod']:<8}{r['actual']:<8}{r['grouping']:<14}≥{r['min_count']:<4}"
              f"#{r.get('rank','?'):<7}{r.get('total_candidates','?'):<8}{r.get('total_hits','?')}")

    # --- Save CSV ---
    csv_path = "cluster_report_2026.csv"
    with open(csv_path, "w", newline="") as f:
        fieldnames = [
            "date", "tod", "actual", "grouping", "min_count",
            "found", "rank", "total_candidates", "total_hits",
            "winner_groups", "seeds", "clusters", "hot_groups",
            "total_hot_groups", "filter_reason", "error"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            row = {}
            for k in fieldnames:
                val = r.get(k, "")
                if isinstance(val, list):
                    if val and isinstance(val[0], dict):
                        val = "; ".join(f"{c.get('label','?')}({c.get('count',0)})" for c in val)
                    else:
                        val = "; ".join(str(v) for v in val)
                row[k] = val
            # Get filter reason from winner dict if present
            if not row.get("filter_reason") and r.get("winner") and isinstance(r["winner"], dict):
                row["filter_reason"] = r["winner"].get("filter_reason", "")
            writer.writerow(row)

    print(f"\n\n💾 Detailed results saved to: {csv_path}")
    print("=" * 70)
    print("  Done! 🎉")
    print("=" * 70)


if __name__ == "__main__":
    main()
