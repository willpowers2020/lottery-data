"""
RBTL Multi-State Cluster Predictor
====================================
Generates pick4 playlists using cluster-based backtesting
for ALL states that have pick4 data.

Usage:
  python3 cluster_predictor.py predict --tod evening
  python3 cluster_predictor.py predict --tod midday
  python3 cluster_predictor.py predict --tod both
  python3 cluster_predictor.py check
  python3 cluster_predictor.py report
  python3 cluster_predictor.py run --tod evening   # check + predict

Cron:
  30 11 * * * cd /path/to/app && python3 cluster_predictor.py run --tod midday
  0  18 * * * cd /path/to/app && python3 cluster_predictor.py run --tod evening
"""

import requests, json, sys, os, argparse
from datetime import datetime, timedelta
from pathlib import Path

# ============ DEFAULTS ============
DEFAULTS = {
    "BASE_URL": os.environ.get("PREDICTOR_URL", "http://localhost:5001"),
    "DB_MODE": os.environ.get("PREDICTOR_DB", "mongo_v2"),
    "GAME_TYPE": os.environ.get("PREDICTOR_GAME", "pick4"),
    "PW_DAYS": int(os.environ.get("PREDICTOR_PW_DAYS", "5")),
    "MAX_PLAYLIST": int(os.environ.get("PREDICTOR_MAX_LIST", "100")),
    "PAYOUT": int(os.environ.get("PREDICTOR_PAYOUT", "5000")),
    "COST_PER_PLAY": float(os.environ.get("PREDICTOR_COST", "1.00")),
    "LOG_FILE": os.environ.get("PREDICTOR_LOG", "cluster_predictions.json"),
}

# Strategies to try (tightest first)
# Each cluster+mc combo tries dp=2 first (tighter), then dp=0 (wider net)
STRATEGIES = [
    # Tightest: cluster_15 mc≥3
    {"grouping": "cluster_15", "min_count": 3, "dp_size": 2},
    {"grouping": "cluster_15", "min_count": 3, "dp_size": 0},
    # cluster_30 mc≥3
    {"grouping": "cluster_30", "min_count": 3, "dp_size": 2},
    {"grouping": "cluster_30", "min_count": 3, "dp_size": 0},
    # cluster_15 mc≥2
    {"grouping": "cluster_15", "min_count": 2, "dp_size": 2},
    {"grouping": "cluster_15", "min_count": 2, "dp_size": 0},
    # cluster_30 mc≥2
    {"grouping": "cluster_30", "min_count": 2, "dp_size": 2},
    {"grouping": "cluster_30", "min_count": 2, "dp_size": 0},
    # cluster_60 mc≥3
    {"grouping": "cluster_60", "min_count": 3, "dp_size": 2},
    {"grouping": "cluster_60", "min_count": 3, "dp_size": 0},
    # cluster_60 mc≥2
    {"grouping": "cluster_60", "min_count": 2, "dp_size": 2},
    {"grouping": "cluster_60", "min_count": 2, "dp_size": 0},
    # cluster_year mc≥3 (Focus profile — year-based grouping)
    {"grouping": "cluster_year", "min_count": 3, "dp_size": 2},
    {"grouping": "cluster_year", "min_count": 3, "dp_size": 0},
    # cluster_year mc≥2
    {"grouping": "cluster_year", "min_count": 2, "dp_size": 2},
    {"grouping": "cluster_year", "min_count": 2, "dp_size": 0},
    # Widest fallbacks
    {"grouping": "cluster_30", "min_count": 1, "dp_size": 2},
    {"grouping": "cluster_30", "min_count": 1, "dp_size": 0},
]


def api_url(path):
    base = DEFAULTS["BASE_URL"]
    db = DEFAULTS["DB_MODE"]
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"


def load_log():
    lf = DEFAULTS["LOG_FILE"]
    if os.path.exists(lf):
        with open(lf, "r") as f:
            return json.load(f)
    return {"predictions": [], "results": []}


def save_log(data):
    with open(DEFAULTS["LOG_FILE"], "w") as f:
        json.dump(data, f, indent=2)


def get_all_states():
    """Fetch all states that have pick4 data."""
    game = DEFAULTS["GAME_TYPE"]
    try:
        r = requests.get(api_url(f"/api/prediction/{game}/states"), timeout=15)
        states = r.json()
        if isinstance(states, list):
            return states
    except Exception as e:
        print(f"  ❌ Failed to fetch states: {e}")
    return []


def get_recent_draws(state, target_date, tod):
    """Fetch recent draws for seed selection."""
    pw_days = DEFAULTS["PW_DAYS"]
    td = datetime.strptime(target_date, "%Y-%m-%d")
    start_date = (td - timedelta(days=pw_days)).strftime("%Y-%m-%d")

    r = requests.post(api_url("/api/draws/recent"), json={
        "state": state,
        "game_type": DEFAULTS["GAME_TYPE"],
        "start_date": start_date,
        "end_date": target_date,
    }, timeout=15)
    data = r.json()
    draws = data.get("draws", [])

    if not draws:
        return []

    # Suppress target draw
    tod_lower = tod.lower()
    filtered = []
    for d in draws:
        if d["date"] != target_date:
            filtered.append(d)
        else:
            dtod = (d.get("tod") or "").lower()
            if tod_lower == "evening" and dtod == "midday":
                filtered.append(d)

    tod_ord = {"evening": 2, "night": 2, "midday": 1, "day": 1}
    filtered.sort(key=lambda d: (d["date"], tod_ord.get((d.get("tod") or "").lower(), 0)), reverse=True)
    return filtered


def run_backtest(state, target_date, tod, strategy):
    """Run a single backtest."""
    body = {
        "state": state,
        "game_type": DEFAULTS["GAME_TYPE"],
        "target_date": target_date,
        "target_tod": tod,
        "lookback_days": 0,
        "min_count": strategy["min_count"],
        "dp_size": strategy["dp_size"],
        "dp_seed_mode": "last",
        "suggested_limit": 999,
        "include_same_day": True,
        "look_forward_days": 0,
        "grouping": strategy["grouping"],
    }

    try:
        r = requests.post(api_url("/api/rbtl/backtest-v2"), json=body, timeout=60)
        data = r.json()
        if data.get("error"):
            return None, data["error"]
        return data, None
    except Exception as e:
        return None, str(e)


def get_actual_winner(state, target_date, tod):
    """Fetch the actual drawn number."""
    r = requests.post(api_url("/api/draws/recent"), json={
        "state": state,
        "game_type": DEFAULTS["GAME_TYPE"],
        "start_date": target_date,
        "end_date": target_date,
    }, timeout=15)
    data = r.json()
    draws = data.get("draws", [])

    tod_lower = tod.lower()
    for d in draws:
        dtod = (d.get("tod") or "").lower()
        if dtod == tod_lower:
            return {
                "actual": d.get("actual", ""),
                "value": d.get("value", ""),
                "date": d["date"],
                "tod": d.get("tod", ""),
            }
    return None


def predict_for_state(state, target_date, tod, verbose=True):
    """Generate prediction for one state. Returns prediction dict or None."""
    max_list = DEFAULTS["MAX_PLAYLIST"]

    # Get seeds
    draws = get_recent_draws(state, target_date, tod)
    if not draws:
        if verbose:
            print(f"    ⏭️  No recent draws — skipping")
        return None

    seed = draws[0]
    seed_val = seed.get("actual") or seed.get("value", "?")

    # Try strategies
    best_result = None
    attempts = []

    for strat in STRATEGIES:
        data, err = run_backtest(state, target_date, tod, strat)
        if err:
            attempts.append({"strategy": strat, "error": err})
            continue

        plays = data.get("suggested_plays", [])
        total = len(plays)
        seeds = data.get("seed_values", [])
        clusters = data.get("top_months", [])

        attempts.append({
            "strategy": strat,
            "total_candidates": total,
        })

        if 0 < total <= max_list:
            if best_result is None or total < best_result["total_candidates"]:
                candidates = []
                for p in plays:
                    candidates.append({
                        "candidate": p["candidate"],
                        "total_appearances": p.get("total_appearances", 0),
                        "month_count": p.get("month_count", 0),
                    })
                best_result = {
                    "strategy": strat,
                    "total_candidates": total,
                    "candidates": candidates,
                    "seed_values": seeds,
                    "top_clusters": [{"label": m["month"], "count": m["count"]} for m in clusters[:3]],
                }

    if best_result is None:
        if verbose:
            # Show what we got
            sizes = [a.get("total_candidates", "err") for a in attempts if not a.get("error")]
            print(f"    ⏭️  No list ≤{max_list} (sizes: {sizes[:4]})")
        return None

    strat = best_result["strategy"]
    cands = best_result["candidates"]
    cost = len(cands) * DEFAULTS["COST_PER_PLAY"]

    prediction = {
        "date": target_date,
        "tod": tod,
        "state": state,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "strategy": strat,
        "seed_values": best_result["seed_values"],
        "seed_draw": f"{seed['date']} {seed.get('tod','')} → {seed_val}",
        "total_candidates": len(cands),
        "cost": cost,
        "candidates": [c["candidate"] for c in cands],
        "top_clusters": best_result["top_clusters"],
    }

    if verbose:
        label = f"{strat['grouping']} mc≥{strat['min_count']} dp={strat['dp_size']}"
        print(f"    ✅ {len(cands)} candidates via {label} | seed: {seed_val} | cost: ${cost:.0f}")

    return prediction


def cmd_predict(args):
    """Generate predictions for all states."""
    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    tods = ["evening", "midday"] if args.tod == "both" else [args.tod]
    max_list = DEFAULTS["MAX_PLAYLIST"]

    print(f"\n{'=' * 70}")
    print(f"  🔮 MULTI-STATE CLUSTER PREDICTOR")
    print(f"  {target_date} | {DEFAULTS['GAME_TYPE']} | Max playlist: {max_list}")
    print(f"{'=' * 70}")

    # Get all states
    print(f"\n  ⏳ Fetching available states...")
    states = get_all_states()
    if not states:
        print("  ❌ No states found")
        return

    print(f"  📋 {len(states)} states with {DEFAULTS['GAME_TYPE']} data")

    log = load_log()
    total_predictions = 0
    total_skipped = 0
    total_cost = 0

    for tod in tods:
        print(f"\n  {'─' * 66}")
        print(f"  ⏰ {tod.upper()} DRAW")
        print(f"  {'─' * 66}")

        for state in sorted(states):
            # Check if we already have a prediction for this state+date+tod
            existing = [p for p in log["predictions"]
                       if p["date"] == target_date and p["tod"] == tod
                       and p.get("state") == state and p["status"] != "skipped"]
            if existing:
                print(f"  {state:<22} ⏭️  Already predicted ({existing[0]['total_candidates']} cands)")
                continue

            sys.stdout.write(f"  {state:<22} ")
            sys.stdout.flush()

            try:
                pred = predict_for_state(state, target_date, tod, verbose=True)
            except Exception as e:
                print(f"  ❌ Error: {e}")
                pred = None

            if pred:
                log["predictions"].append(pred)
                total_predictions += 1
                total_cost += pred["cost"]
            else:
                # Log the skip
                log["predictions"].append({
                    "date": target_date,
                    "tod": tod,
                    "state": state,
                    "timestamp": datetime.now().isoformat(),
                    "status": "skipped",
                })
                total_skipped += 1

    save_log(log)

    # Summary
    print(f"\n  {'=' * 66}")
    print(f"  📊 SUMMARY")
    print(f"  {'=' * 66}")
    print(f"  Predictions generated: {total_predictions}")
    print(f"  States skipped:        {total_skipped}")
    print(f"  Total cost if played:  ${total_cost:,.0f}")
    print(f"  Potential per win:     ${DEFAULTS['PAYOUT']:,}")
    print(f"  Break-even needs:      {total_cost / DEFAULTS['PAYOUT']:.1f} wins" if total_cost > 0 else "")
    print(f"\n  💾 Saved to {DEFAULTS['LOG_FILE']}")

    # Also save a summary text file
    summary_file = f"predictions_{target_date}.txt"
    with open(summary_file, "w") as f:
        f.write(f"# RBTL Multi-State Cluster Predictions\n")
        f.write(f"# {target_date} | {DEFAULTS['GAME_TYPE']}\n")
        f.write(f"# {total_predictions} predictions | ${total_cost:,.0f} total cost\n")
        f.write(f"#\n")

        for tod in tods:
            f.write(f"\n{'='*60}\n")
            f.write(f"{tod.upper()} DRAW\n")
            f.write(f"{'='*60}\n\n")

            tod_preds = [p for p in log["predictions"]
                        if p["date"] == target_date and p["tod"] == tod
                        and p.get("status") == "pending"]

            for p in sorted(tod_preds, key=lambda x: x.get("state", "")):
                state = p.get("state", "?")
                strat = p.get("strategy", {})
                cands = p.get("candidates", [])
                label = f"{strat.get('grouping','?')} mc≥{strat.get('min_count','?')}"
                f.write(f"\n--- {state} ({len(cands)} candidates, {label}) ---\n")
                for c in cands:
                    f.write(f"{c}\n")

    print(f"  📄 Number lists saved to {summary_file}")


def cmd_check(args):
    """Check results for all pending predictions."""
    log = load_log()
    pending = [p for p in log["predictions"] if p.get("status") == "pending"]

    if not pending:
        print("  No pending predictions to check.")
        return

    print(f"\n{'=' * 70}")
    print(f"  🔍 CHECKING {len(pending)} PENDING PREDICTIONS")
    print(f"{'=' * 70}")

    hits = 0
    misses = 0
    errors = 0
    total_cost = 0
    total_revenue = 0

    # Group by date+tod for cleaner output
    from collections import defaultdict
    groups = defaultdict(list)
    for p in pending:
        groups[(p["date"], p["tod"])].append(p)

    for (pdate, ptod), preds in sorted(groups.items()):
        print(f"\n  📅 {pdate} {ptod.upper()}")

        for pred in sorted(preds, key=lambda x: x.get("state", "")):
            state = pred.get("state", "?")
            cands = pred.get("candidates", [])
            cost = pred.get("cost", len(cands))

            try:
                winner = get_actual_winner(state, pdate, ptod)
            except Exception as e:
                print(f"    {state:<22} ⚠️  Error fetching: {e}")
                errors += 1
                continue

            if winner is None:
                print(f"    {state:<22} ⏳ Draw not yet available")
                continue

            actual = winner["actual"]
            actual_norm = "".join(sorted(actual.replace("-", "")))
            hit = actual_norm in cands

            pred["status"] = "hit" if hit else "miss"
            pred["winner_actual"] = actual
            pred["winner_norm"] = actual_norm
            pred["payout"] = DEFAULTS["PAYOUT"] if hit else 0
            pred["profit"] = pred["payout"] - cost
            pred["checked_at"] = datetime.now().isoformat()

            total_cost += cost

            if hit:
                rank = cands.index(actual_norm) + 1
                pred["winner_rank"] = rank
                hits += 1
                total_revenue += DEFAULTS["PAYOUT"]
                print(f"    {state:<22} 🏆 HIT! {actual} (#{rank}/{len(cands)}) "
                      f"+${DEFAULTS['PAYOUT'] - cost:,.0f}")
            else:
                misses += 1
                print(f"    {state:<22} ❌ {actual} not in {len(cands)} cands | -${cost:.0f}")

            # Log result
            log["results"].append({
                "date": pdate, "tod": ptod, "state": state,
                "winner": actual, "hit": hit,
                "rank": pred.get("winner_rank"),
                "candidates": len(cands),
                "strategy": pred.get("strategy", {}),
                "cost": cost,
                "payout": pred["payout"],
                "profit": pred["profit"],
            })

    save_log(log)

    profit = total_revenue - total_cost
    print(f"\n  {'=' * 66}")
    print(f"  Results: {hits} hits, {misses} misses, {errors} errors")
    print(f"  Cost: ${total_cost:,.0f} | Revenue: ${total_revenue:,.0f} | P/L: ${profit:>+,.0f}")
    if total_cost > 0:
        print(f"  ROI: {profit/total_cost*100:.0f}%")


def cmd_report(args):
    """Show full prediction history and P/L."""
    log = load_log()
    results = log.get("results", [])
    predictions = log.get("predictions", [])

    total_preds = len([p for p in predictions if p.get("status") != "skipped"])
    pending = len([p for p in predictions if p.get("status") == "pending"])
    skipped = len([p for p in predictions if p.get("status") == "skipped"])

    print(f"\n{'=' * 70}")
    print(f"  📊 MULTI-STATE PREDICTION REPORT")
    print(f"{'=' * 70}")
    print(f"\n  Total predictions: {total_preds} | Pending: {pending} | Skipped: {skipped}")
    print(f"  Checked results: {len(results)}")

    if not results:
        print("\n  No checked results yet.")
        return

    hits = [r for r in results if r.get("hit")]
    total_cost = sum(r.get("cost", 0) for r in results)
    total_revenue = sum(r.get("payout", 0) for r in results)
    profit = total_revenue - total_cost

    print(f"\n  Overall: {len(hits)} hits / {len(results)} checked ({len(hits)/len(results)*100:.1f}%)")
    print(f"  Cost: ${total_cost:>10,.0f}")
    print(f"  Revenue: ${total_revenue:>10,.0f}")
    print(f"  Profit: ${profit:>+10,.0f}")
    if total_cost > 0:
        print(f"  ROI: {profit/total_cost*100:>9.0f}%")

    # Per-state breakdown
    from collections import defaultdict
    state_stats = defaultdict(lambda: {"plays": 0, "hits": 0, "cost": 0, "revenue": 0})

    for r in results:
        st = r.get("state", "?")
        state_stats[st]["plays"] += 1
        state_stats[st]["cost"] += r.get("cost", 0)
        if r.get("hit"):
            state_stats[st]["hits"] += 1
            state_stats[st]["revenue"] += r.get("payout", 0)

    print(f"\n  {'State':<22}{'Plays':<8}{'Hits':<7}{'Hit%':<8}{'Cost':<10}{'Rev':<10}{'P/L'}")
    print("  " + "-" * 70)

    for state in sorted(state_stats.keys()):
        s = state_stats[state]
        pl = s["revenue"] - s["cost"]
        pct = s["hits"] / s["plays"] * 100 if s["plays"] > 0 else 0
        print(f"  {state:<22}{s['plays']:<8}{s['hits']:<7}{pct:>5.1f}%  "
              f"${s['cost']:>7,.0f}  ${s['revenue']:>7,.0f}  ${pl:>+8,.0f}")

    # Per-date breakdown
    print(f"\n  {'Date':<12}{'TOD':<9}{'States':<9}{'Hits':<7}{'Cost':<10}{'Rev':<10}{'P/L'}")
    print("  " + "-" * 65)

    date_stats = defaultdict(lambda: {"plays": 0, "hits": 0, "cost": 0, "revenue": 0})
    for r in results:
        key = f"{r['date']} {r['tod']}"
        date_stats[key]["plays"] += 1
        date_stats[key]["cost"] += r.get("cost", 0)
        if r.get("hit"):
            date_stats[key]["hits"] += 1
            date_stats[key]["revenue"] += r.get("payout", 0)

    running = 0
    for key in sorted(date_stats.keys()):
        s = date_stats[key]
        pl = s["revenue"] - s["cost"]
        running += pl
        parts = key.split(" ", 1)
        print(f"  {parts[0]:<12}{parts[1] if len(parts)>1 else '':<9}"
              f"{s['plays']:<9}{s['hits']:<7}${s['cost']:>7,.0f}  "
              f"${s['revenue']:>7,.0f}  ${pl:>+8,.0f}")

    print(f"\n  Running total: ${running:>+,.0f}")

    # Hit details
    if hits:
        print(f"\n  🏆 HITS:")
        for r in sorted(hits, key=lambda x: x["date"]):
            print(f"    {r['date']} {r['tod']:<9} {r.get('state','?'):<20} "
                  f"{r['winner']} (#{r.get('rank','?')}/{r['candidates']}) "
                  f"+${r.get('profit',0):,.0f}")


def cmd_run(args):
    """Full cycle: check old + predict new."""
    print("  📋 Step 1: Checking pending predictions...")
    cmd_check(args)
    print(f"\n  📋 Step 2: Generating new predictions...")
    cmd_predict(args)


def main():
    parser = argparse.ArgumentParser(description="RBTL Multi-State Cluster Predictor")
    sub = parser.add_subparsers(dest="command")

    for cmd_name in ["predict", "check", "report", "run"]:
        p = sub.add_parser(cmd_name)
        p.add_argument("--date", help="Target date (YYYY-MM-DD)", default=None)
        p.add_argument("--tod", help="evening / midday / both", default="evening")

    args = parser.parse_args()

    cmds = {"predict": cmd_predict, "check": cmd_check, "report": cmd_report, "run": cmd_run}
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()
        print("\n  Quick start:")
        print("    python3 cluster_predictor.py predict --tod both")
        print("    python3 cluster_predictor.py check")
        print("    python3 cluster_predictor.py report")
        print("    python3 cluster_predictor.py run --tod evening")


if __name__ == "__main__":
    main()
