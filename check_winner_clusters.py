"""
Winner Cluster Survival Check (Interactive)
=============================================
Tests whether cluster grouping finds winners that monthly grouping misses.

Run:  python check_winner_clusters.py
"""

import requests, json, sys
from datetime import datetime, timedelta

def prompt(msg, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{msg}{suffix}: ").strip()
    return val if val else default

def main():
    print("=" * 60)
    print("  🔍 WINNER CLUSTER SURVIVAL CHECK")
    print("=" * 60)
    print()

    # --- Connection ---
    base = prompt("Flask app URL", "http://localhost:5001")
    db = prompt("DB mode", "mongo_v2")

    def api(path):
        sep = "&" if "?" in path else "?"
        return f"{base}{path}{sep}db={db}"

    # --- Game setup ---
    print()
    state = prompt("State (full name)", "Florida")
    game_type = prompt("Game type (pick3 / pick4)", "pick4")
    target_date = prompt("Target date (YYYY-MM-DD)", "2019-09-15")
    target_tod = prompt("Target TOD (evening / midday / all)", "evening")
    pw_days = int(prompt("Past window days (how far back for seeds)", "5"))

    # --- Load recent draws ---
    print("\n⏳ Loading recent draws...")
    td = datetime.strptime(target_date, "%Y-%m-%d")
    start_date = (td - timedelta(days=pw_days)).strftime("%Y-%m-%d")

    try:
        r = requests.post(api("/api/draws/recent"), json={
            "state": state, "game_type": game_type,
            "start_date": start_date, "end_date": target_date
        }, timeout=15)
        draws_data = r.json()
    except Exception as e:
        print(f"❌ Failed to load draws: {e}")
        return

    if draws_data.get("error"):
        print(f"❌ API error: {draws_data['error']}")
        return

    draws = draws_data.get("draws", [])
    if not draws:
        print("❌ No draws found in range")
        return

    # Suppress target draw (like the UI does)
    # Note: API returns capitalized TOD ("Evening", "Midday") so compare lowercase
    target_tod_lower = target_tod.lower()
    filtered_draws = []
    for d in draws:
        if d["date"] != target_date:
            filtered_draws.append(d)
        else:
            dtod = (d.get("tod") or "").lower()
            if target_tod_lower and target_tod_lower != "all":
                if target_tod_lower == "midday":
                    continue  # suppress midday target
                if target_tod_lower == "evening":
                    if dtod == "midday":
                        filtered_draws.append(d)  # keep midday, suppress evening
                    # else suppress evening

    # Sort: most recent first
    tod_ord = {"evening": 2, "night": 2, "midday": 1, "day": 1}
    filtered_draws.sort(key=lambda d: (d["date"], tod_ord.get((d.get("tod") or "").lower(), 0)), reverse=True)

    print(f"\n📋 Available seeds ({len(filtered_draws)} draws):")
    for i, d in enumerate(filtered_draws):
        val = d.get("actual") or d.get("value", "?")
        tod = d.get("tod", "")
        print(f"  [{i}] {d['date']} {tod:<8} → {val}")

    # Show the suppressed target (winner)
    for d in draws:
        if d["date"] == target_date and (d.get("tod") or "").lower() == target_tod_lower:
            print(f"\n  🏆 Target (suppressed): {d['date']} {d.get('tod','')} → {d.get('actual','?')}")
            break

    # --- Profile selection ---
    print("\n📦 Profiles:")
    print("  [1] Sniper   — 1 seed (most recent), dp_size=2, lookback=0")
    print("  [2] Wide Net — all seeds, dp_size=2")
    print("  [3] Shadow   — 2 seeds (same day mid+eve), dp_size=0")
    print("  [4] Custom   — you pick")

    profile = prompt("\nSelect profile", "1")

    if profile == "1":
        seed_indices = [0]
        dp_size = 2
        lookback = 0
    elif profile == "2":
        seed_indices = list(range(len(filtered_draws)))
        dp_size = 2
        lookback = None  # calculate
    elif profile == "3":
        seed_indices = [0, 1] if len(filtered_draws) >= 2 else [0]
        dp_size = 0
        lookback = -1
    else:
        sel = prompt("Seed indices (comma-separated, e.g. 0,1,2)", "0")
        seed_indices = [int(x.strip()) for x in sel.split(",")]
        dp_size = int(prompt("DP size (0/2/3)", "2"))
        lookback = None

    # Calculate lookback if not set
    if lookback is None:
        if len(seed_indices) == 1:
            lookback = 0
        else:
            dates = [datetime.strptime(filtered_draws[i]["date"], "%Y-%m-%d") for i in seed_indices]
            earliest = min(dates)
            unique_dates = set(d.strftime("%Y-%m-%d") for d in dates)
            if len(unique_dates) == 1 and len(seed_indices) <= 3:
                lookback = -1
            else:
                lookback = (td - earliest).days

    selected_seeds = [filtered_draws[i] for i in seed_indices]
    print(f"\n🎯 Using {len(selected_seeds)} seed(s), lookback={lookback}, dp_size={dp_size}")
    for s in selected_seeds:
        print(f"   {s['date']} {s.get('tod','')} → {s.get('actual') or s.get('value','?')}")

    # --- Run backtests ---
    GROUPINGS = ["monthly", "cluster_15", "cluster_30", "cluster_60"]
    MIN_COUNTS = [1, 2, 3, 4, 5]

    results = {}

    total = len(GROUPINGS) * len(MIN_COUNTS)
    print(f"\n{'=' * 60}")
    print(f"⏳ Running {total} backtests...")
    print("=" * 60)

    count = 0
    for grouping in GROUPINGS:
        print(f"\n  --- {grouping.upper()} ---")
        for mc in MIN_COUNTS:
            count += 1
            body = {
                "state": state,
                "game_type": game_type,
                "target_date": target_date,
                "target_tod": target_tod,
                "lookback_days": lookback,
                "min_count": mc,
                "dp_size": dp_size,
                "dp_seed_mode": "last",
                "suggested_limit": 999,
                "include_same_day": True,
                "look_forward_days": 0,
                "grouping": grouping,
            }
            sys.stdout.write(f"\r  [{count}/{total}] {grouping} mc≥{mc}...")
            sys.stdout.flush()
            try:
                r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
                data = r.json()
                if data.get("error"):
                    print(f"\n  {grouping} mc≥{mc}: API error — {data['error']}")
                    results[(grouping, mc)] = {"error": True}
                    continue
            except Exception as e:
                print(f"\n  {grouping} mc≥{mc}: Request error — {e}")
                results[(grouping, mc)] = {"error": True}
                continue

            plays = data.get("suggested_plays", [])
            winners = data.get("target_winners", [])
            hot_groups = data.get("selected_month_count", 0)

            # Find winners in candidate list
            winner_info = []
            for w in winners:
                wval = w.get("value", "")
                wnorm = "".join(sorted(wval.replace("-", "")))
                for idx, p in enumerate(plays):
                    if p["candidate"] == wnorm:
                        winner_info.append({
                            "value": wval,
                            "norm": wnorm,
                            "rank": idx + 1,
                            "total_appearances": p.get("total_appearances", 0),
                            "month_count": p.get("month_count", 0),
                            "months": p.get("months", []),
                        })
                        break

            results[(grouping, mc)] = {
                "found": len(winner_info) > 0,
                "winners": winner_info,
                "total_candidates": len(plays),
                "hot_groups": hot_groups,
            }

            status = "✅" if winner_info else "❌"
            detail = ""
            if winner_info:
                w = winner_info[0]
                detail = f"rank #{w['rank']}/{len(plays)}, hits={w['total_appearances']}, in {w['month_count']} grp(s)"
            print(f"\r  {grouping:<12} mc≥{mc}: {status} {detail}                    ")

    # --- Summary Table ---
    print("\n" + "=" * 70)
    print("  SUMMARY TABLE — Winner found at each grouping × min_count?")
    print("=" * 70)

    header = f"  {'Grouping':<14}" + "".join([f"{'mc≥'+str(mc):<14}" for mc in MIN_COUNTS])
    print(header)
    print("  " + "-" * (14 + 14 * len(MIN_COUNTS)))

    for grouping in GROUPINGS:
        row = f"  {grouping:<14}"
        for mc in MIN_COUNTS:
            r = results.get((grouping, mc), {})
            if r.get("error"):
                cell = "ERR"
            elif r.get("found"):
                w = r["winners"][0]
                cell = f"✅ #{w['rank']} ({w['total_appearances']}h)"
            else:
                cell = "❌"
            row += f"{cell:<14}"
        print(row)

    # --- Key insight ---
    print("\n" + "=" * 70)
    print("  KEY INSIGHT — Does clustering save the winner?")
    print("=" * 70)

    for mc_test in [2, 3, 4, 5]:
        monthly_r = results.get(("monthly", mc_test), {})
        for cg in ["cluster_15", "cluster_30", "cluster_60"]:
            cg_r = results.get((cg, mc_test), {})
            if not monthly_r.get("found") and cg_r.get("found"):
                w = cg_r["winners"][0]
                print(f"  🎯 At mc≥{mc_test}: {cg} KEEPS winner (#{w['rank']}, {w['total_appearances']} hits)")
                print(f"     while monthly DROPS it!")
            elif monthly_r.get("found") and cg_r.get("found"):
                wm = monthly_r["winners"][0]
                wc = cg_r["winners"][0]
                if wc["rank"] < wm["rank"]:
                    print(f"  📈 At mc≥{mc_test}: {cg} ranks winner HIGHER (#{wc['rank']}) vs monthly (#{wm['rank']})")

    # --- Detailed winner breakdown ---
    print("\n" + "=" * 70)
    print("  WINNER DETAIL PER GROUPING (at mc≥1)")
    print("=" * 70)
    for grouping in GROUPINGS:
        r = results.get((grouping, 1), {})
        if r.get("found"):
            w = r["winners"][0]
            print(f"\n  {grouping}: rank #{w['rank']}/{r['total_candidates']}, total_hits={w['total_appearances']}")
            print(f"    In {w['month_count']} group(s): {', '.join(w['months'])}")
            if w["month_count"] == 1 and w["total_appearances"] >= 3:
                print(f"    → ✅ All {w['total_appearances']} hits concentrated in 1 group — survives mc≥3!")
            elif w["total_appearances"] >= 3 and w["month_count"] > 1:
                print(f"    → ⚠️  {w['total_appearances']} hits spread across {w['month_count']} groups")
            elif w["total_appearances"] < 3:
                print(f"    → ℹ️  Only {w['total_appearances']} total hits — won't survive mc≥3 regardless")
        else:
            print(f"\n  {grouping}: winner NOT in candidates even at mc≥1")

    print("\n" + "=" * 70)
    print("  Done! 🎉")
    print("=" * 70)


if __name__ == "__main__":
    main()
