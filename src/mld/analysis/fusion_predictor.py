"""
🎯 FUSION PREDICTOR — 50 Candidates Per Cycle
================================================
Combines multiple RBTL strategies + Truth Table + Prior Winners
to produce a tight 50-candidate list that covers the next 1-3 draws.

Architecture:
  1. Run multiple RBTL strategies (Shadow, Focus, MLD, cluster variants)
  2. Generate Truth Table from the last 1-3 draws (not just one)
  3. Score each candidate by HOW MANY strategies agree
  4. Take top 50 by consensus score

The more strategies agree on a number, the higher its signal.

Usage:
  python3 fusion_predictor.py
  python3 fusion_predictor.py --date 2024-07-17 --tod midday --state Florida
"""

import requests
import json
import sys
import argparse
from collections import defaultdict
import itertools


# ======================== CONFIG ========================

DEFAULTS = {
    "BASE_URL": "http://localhost:5001",
    "DB": "mongo_v2",
    "STATE": "Florida",
    "GAME": "pick4",
    "TARGET_LIMIT": 50,
}


# ======================== TRUTH TABLE ========================

def generate_tt(seed_value):
    """Generate 81 ±1 digit combos, return set of normalized (sorted) forms."""
    digits = list(str(seed_value).zfill(4))
    options = [
        [d, str((int(d)+1) % 10), str((int(d)-1) % 10)]
        for d in digits
    ]
    combos = [''.join(c) for c in itertools.product(*options)]
    return set(''.join(sorted(c)) for c in combos)


# ======================== RBTL STRATEGIES ========================

RBTL_STRATEGIES = [
    # name, weight, params
    {
        "name": "Shadow (monthly mc≥2)",
        "weight": 3,
        "params": {"grouping": "monthly", "min_count": 2, "dp_size": 0,
                   "exclude_non_dupes": True}
    },
    {
        "name": "Sniper (monthly mc≥1 2DP)",
        "weight": 2,
        "params": {"grouping": "monthly", "min_count": 1, "dp_size": 2,
                   "exclude_non_dupes": False}
    },
    {
        "name": "Focus (CY mc≥2, top 20)",
        "weight": 2,
        "params": {"grouping": "cluster_year", "min_count": 2, "dp_size": 0,
                   "exclude_non_dupes": True}
    },
    {
        "name": "MLD (CY mc≥2 dupes)",
        "weight": 3,
        "params": {"grouping": "cluster_year", "min_count": 2, "dp_size": 0,
                   "duplicates_only": True}
    },
    {
        "name": "Cluster30 mc≥2",
        "weight": 1,
        "params": {"grouping": "cluster_30", "min_count": 2, "dp_size": 0,
                   "exclude_non_dupes": True}
    },
    {
        "name": "Cluster30 mc≥2 2DP",
        "weight": 2,
        "params": {"grouping": "cluster_30", "min_count": 2, "dp_size": 2,
                   "exclude_non_dupes": False}
    },
]


# ======================== API ========================

def api_url(base, path, db):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"


def fetch_recent_draws(base, db, state, game, start, end):
    """Fetch draws in a date range."""
    r = requests.post(
        api_url(base, "/api/draws/recent", db),
        json={"state": state, "game_type": game,
              "start_date": start, "end_date": end},
        timeout=30
    )
    return r.json().get("draws", [])


def run_rbtl(base, db, state, game, target_date, target_tod, strategy_params):
    """Run one RBTL backtest strategy, return list of candidate normalized values."""
    body = {
        "state": state, "game_type": game,
        "target_date": target_date, "target_tod": target_tod,
        "lookback_days": -1,
        "min_count": strategy_params.get("min_count", 2),
        "dp_size": strategy_params.get("dp_size", 0),
        "dp_seed_mode": "last",
        "suggested_limit": 999,
        "include_same_day": True,
        "look_forward_days": 0,
        "grouping": strategy_params.get("grouping", "monthly"),
        "duplicates_only": strategy_params.get("duplicates_only", False),
        "truth_table_seed": "",  # TT applied separately in fusion
    }
    if strategy_params.get("exclude_non_dupes"):
        body["exclude_non_dupes"] = True

    r = requests.post(
        api_url(base, "/api/rbtl/backtest-v2", db),
        json=body, timeout=60
    )
    data = r.json()
    if data.get("error"):
        return [], data.get("error")

    plays = data.get("suggested_plays", [])
    # Return candidates with their rank info
    results = []
    for p in plays:
        results.append({
            "candidate": p["candidate"],
            "rank": p.get("rank", 999),
            "total_appearances": p.get("total_appearances", 0),
            "month_count": p.get("month_count", 0),
        })
    return results, None


# ======================== FUSION SCORING ========================

def fusion_score(candidate_scores, target_n=50):
    """
    Score candidates by multi-strategy consensus.

    Scoring:
      - Each strategy that includes a candidate adds its weight
      - Higher rank within a strategy adds bonus points
      - Truth Table match adds weight
      - Prior winner (PW) TT match adds extra weight
      - Candidates appearing in more strategies get priority

    Returns sorted list of top N candidates with scores.
    """
    # candidate_scores: {normalized: {strategies: [...], tt_hits: int, rank_sum: float, ...}}

    scored = []
    for cand, info in candidate_scores.items():
        n_strategies = len(info["strategies"])
        total_weight = info["total_weight"]
        tt_bonus = info.get("tt_bonus", 0)
        pw_tt_bonus = info.get("pw_tt_bonus", 0)

        # Rank bonus: top-10 in any strategy = extra points
        rank_bonus = 0
        for s in info["strategies"]:
            r = s.get("rank", 999)
            if r <= 5:
                rank_bonus += 3
            elif r <= 10:
                rank_bonus += 2
            elif r <= 20:
                rank_bonus += 1
            elif r <= 50:
                rank_bonus += 0.5

        # Final score
        score = (
            total_weight * 2          # Strategy consensus (most important)
            + tt_bonus * 3            # TT from last draw
            + pw_tt_bonus * 2         # TT from prior winners
            + rank_bonus              # High rank bonus
            + n_strategies * 1.5      # Breadth bonus
            + info.get("total_appearances", 0) * 0.1  # Historical frequency
        )

        scored.append({
            "candidate": cand,
            "score": round(score, 1),
            "n_strategies": n_strategies,
            "total_weight": total_weight,
            "tt_match": info.get("tt_match", False),
            "pw_tt_match": info.get("pw_tt_match", False),
            "rank_bonus": round(rank_bonus, 1),
            "strategies": [s["name"] for s in info["strategies"]],
            "best_rank": min((s["rank"] for s in info["strategies"]), default=999),
            "total_appearances": info.get("total_appearances", 0),
        })

    # Sort by score descending, then by best_rank ascending
    scored.sort(key=lambda x: (-x["score"], x["best_rank"]))
    return scored[:target_n]


# ======================== MAIN ========================

def main():
    parser = argparse.ArgumentParser(description="Fusion Predictor — 50 candidates")
    parser.add_argument("--url", default=DEFAULTS["BASE_URL"])
    parser.add_argument("--db", default=DEFAULTS["DB"])
    parser.add_argument("--state", default=DEFAULTS["STATE"])
    parser.add_argument("--game", default=DEFAULTS["GAME"])
    parser.add_argument("--date", required=False, help="Target date YYYY-MM-DD")
    parser.add_argument("--tod", default="", help="midday or evening")
    parser.add_argument("--limit", type=int, default=50, help="Number of candidates")
    parser.add_argument("--pw", nargs="*", help="Prior winner values for TT (e.g. 0371 9148)")
    args = parser.parse_args()

    base = args.url
    db = args.db
    state = args.state
    game = args.game
    target_n = args.limit
    target_tod = args.tod

    # Get target date
    if args.date:
        target_date = args.date
    else:
        target_date = input("Target date [YYYY-MM-DD]: ").strip()

    if not target_tod:
        target_tod = input("Target TOD [midday/evening]: ").strip() or ""

    print(f"\n{'='*80}")
    print(f"  🎯 FUSION PREDICTOR — {target_n} Candidates")
    print(f"  {state} {game} | {target_date} {target_tod or 'all'}")
    print(f"{'='*80}")

    # ---- STEP 1: Get recent draws for TT seeds ----
    # Get draws from a few days before target
    from datetime import datetime, timedelta
    tdt = datetime.strptime(target_date, "%Y-%m-%d")
    seed_start = (tdt - timedelta(days=5)).strftime("%Y-%m-%d")

    all_draws = fetch_recent_draws(base, db, state, game, seed_start, target_date)
    all_draws.sort(key=lambda d: (d["date"], 0 if (d.get("tod") or "").lower() == "midday" else 1))

    # Find draws BEFORE the target
    pre_draws = []
    for d in all_draws:
        dd = d["date"]
        dtod = (d.get("tod") or "").lower()
        if dd < target_date or (dd == target_date and target_tod and dtod != target_tod
            and target_tod == "evening" and dtod == "midday"):
            pre_draws.append(d)

    if not pre_draws:
        print("  ⚠️  No prior draws found for TT seeds!")
        return

    print(f"\n  📡 Recent draws (for TT seeds):")
    for d in pre_draws[-6:]:
        print(f"    {d['date']} {(d.get('tod') or ''):8s} {d.get('value','?')}")

    # ---- STEP 2: Generate Truth Tables ----
    # TT from last 3 draws (covers the "next 1-3 draws" window)
    tt_seeds = []
    last_3 = pre_draws[-3:]
    tt_union = set()

    print(f"\n  🔢 Truth Table seeds (last 3 draws):")
    for d in last_3:
        val = d.get("value", "")
        if val and len(val) >= 4:
            tt = generate_tt(val)
            tt_union |= tt
            tt_seeds.append({"value": val, "date": d["date"],
                             "tod": d.get("tod", ""), "tt_set": tt})
            print(f"    {d['date']} {(d.get('tod') or ''):8s} {val} → {len(tt)} unique sorted")

    print(f"    Union of all TT seeds: {len(tt_union)} unique sorted forms")

    # TT from prior winners (user-provided or from look-forward)
    pw_tt_union = set()
    pw_values = args.pw or []
    if pw_values:
        print(f"\n  🏆 Prior Winner TT seeds:")
        for pv in pw_values:
            if len(pv) >= 4:
                ptt = generate_tt(pv)
                pw_tt_union |= ptt
                print(f"    PW {pv} → {len(ptt)} unique sorted")
        print(f"    Union of PW TTs: {len(pw_tt_union)} unique sorted")

    # ---- STEP 3: Run all RBTL strategies ----
    print(f"\n  🔄 Running {len(RBTL_STRATEGIES)} RBTL strategies...")

    # Master scoring dict: candidate -> info
    candidates = defaultdict(lambda: {
        "strategies": [],
        "total_weight": 0,
        "total_appearances": 0,
        "tt_match": False,
        "pw_tt_match": False,
        "tt_bonus": 0,
        "pw_tt_bonus": 0,
    })

    for strat in RBTL_STRATEGIES:
        results, err = run_rbtl(
            base, db, state, game, target_date, target_tod,
            strat["params"]
        )
        if err:
            print(f"    ❌ {strat['name']}: {err}")
            continue

        # For Focus, only take top 20
        if "top 20" in strat["name"].lower():
            results = results[:20]

        n = len(results)
        print(f"    ✅ {strat['name']}: {n} candidates")

        for r in results:
            c = r["candidate"]
            candidates[c]["strategies"].append({
                "name": strat["name"],
                "rank": r["rank"],
                "weight": strat["weight"],
            })
            candidates[c]["total_weight"] += strat["weight"]
            candidates[c]["total_appearances"] = max(
                candidates[c]["total_appearances"],
                r.get("total_appearances", 0)
            )

    # ---- STEP 4: Apply TT scoring ----
    print(f"\n  🔢 Applying Truth Table scoring...")
    tt_matches = 0
    pw_matches = 0
    for c in candidates:
        if c in tt_union:
            candidates[c]["tt_match"] = True
            candidates[c]["tt_bonus"] = 2  # Strong signal
            tt_matches += 1
        if c in pw_tt_union:
            candidates[c]["pw_tt_match"] = True
            candidates[c]["pw_tt_bonus"] = 1.5
            pw_matches += 1

    print(f"    TT matches (last 3 draws): {tt_matches} candidates")
    if pw_values:
        print(f"    PW TT matches: {pw_matches} candidates")

    # Also add pure TT candidates that might not be in any RBTL strategy
    # These get a lower base weight but TT bonus
    tt_only_added = 0
    for norm in tt_union:
        if norm not in candidates:
            candidates[norm]["tt_match"] = True
            candidates[norm]["tt_bonus"] = 2
            candidates[norm]["total_weight"] = 0  # No RBTL backing
            candidates[norm]["strategies"] = []
            tt_only_added += 1

    print(f"    TT-only candidates added: {tt_only_added}")
    print(f"    Total unique candidates in pool: {len(candidates)}")

    # ---- STEP 5: Fusion scoring ----
    print(f"\n  🎯 Scoring {len(candidates)} candidates...")
    top = fusion_score(dict(candidates), target_n)

    # ---- STEP 6: Display results ----
    print(f"\n{'='*80}")
    print(f"  🏆 TOP {len(top)} CANDIDATES — Fusion Ranked")
    print(f"{'='*80}")

    print(f"\n  {'#':<4}{'Number':<9}{'Score':<8}{'Strats':<8}{'Weight':<8}"
          f"{'TT':<5}{'PW':<5}{'Best#':<8}{'Hits':<6}{'Strategies'}")
    print(f"  {'-'*4}{'-'*9}{'-'*8}{'-'*8}{'-'*8}{'-'*5}{'-'*5}{'-'*8}{'-'*6}{'-'*30}")

    for i, c in enumerate(top):
        tt = "🔢" if c["tt_match"] else "  "
        pw = "🏆" if c["pw_tt_match"] else "  "
        strats_short = ", ".join(s.split("(")[0].strip()[:10] for s in c["strategies"][:3])
        if len(c["strategies"]) > 3:
            strats_short += f" +{len(c['strategies'])-3}"

        print(f"  {i+1:<4}{c['candidate']:<9}{c['score']:<8}"
              f"{c['n_strategies']:<8}{c['total_weight']:<8}"
              f"{tt:<5}{pw:<5}{'#'+str(c['best_rank']):<8}{c['total_appearances']:<6}"
              f"{strats_short}")

    # Summary stats
    n_with_tt = sum(1 for c in top if c["tt_match"])
    n_with_pw = sum(1 for c in top if c["pw_tt_match"])
    n_multi = sum(1 for c in top if c["n_strategies"] >= 2)
    avg_score = sum(c["score"] for c in top) / len(top) if top else 0
    max_strats = max(c["n_strategies"] for c in top) if top else 0

    print(f"\n  📊 Composition:")
    print(f"    Multi-strategy (≥2): {n_multi}/{len(top)} ({n_multi/len(top)*100:.0f}%)")
    print(f"    TT match:            {n_with_tt}/{len(top)} ({n_with_tt/len(top)*100:.0f}%)")
    if pw_values:
        print(f"    PW TT match:         {n_with_pw}/{len(top)} ({n_with_pw/len(top)*100:.0f}%)")
    print(f"    Max strategies:      {max_strats}")
    print(f"    Avg score:           {avg_score:.1f}")

    # Play list
    print(f"\n  📝 PLAY LIST ({len(top)} numbers):")
    print(f"  {'─'*54}")
    numbers = [c["candidate"] for c in top]
    for j in range(0, len(numbers), 10):
        row = numbers[j:j+10]
        print(f"    {'  '.join(row)}")

    # Cost analysis
    print(f"\n  💰 Cost Analysis:")
    print(f"    Straight plays: {len(top)} × $1 = ${len(top)}")
    print(f"    If winner is in list: $5,000 payout = {5000/len(top):.0f}x ROI")
    print(f"    Play for 3 draws: ${len(top)*3} → if 1 hit = {5000/(len(top)*3):.0f}x ROI")

    return top


# ======================== BACKTEST MODE ========================

def backtest(args_override=None):
    """
    Run fusion predictor across a range of dates and measure hit rate.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULTS["BASE_URL"])
    parser.add_argument("--db", default=DEFAULTS["DB"])
    parser.add_argument("--state", default=DEFAULTS["STATE"])
    parser.add_argument("--game", default=DEFAULTS["GAME"])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--use-pw", action="store_true",
                        help="Use the draw BEFORE the prior draw as PW TT seed")
    args = parser.parse_args(args_override)

    base = args.url
    db = args.db
    state = args.state
    game = args.game
    target_n = args.limit

    print(f"\n{'='*90}")
    print(f"  🎯 FUSION PREDICTOR — BACKTEST MODE")
    print(f"  {state} {game} | {args.start} to {args.end} | Top {target_n}")
    print(f"{'='*90}")

    # Fetch all draws
    from datetime import datetime, timedelta
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    seed_start = (start_dt - timedelta(days=7)).strftime("%Y-%m-%d")

    all_draws = fetch_recent_draws(base, db, state, game, seed_start, args.end)
    all_draws.sort(key=lambda d: (d["date"], 0 if (d.get("tod") or "").lower() == "midday" else 1))

    draws_in_range = [d for d in all_draws
                      if d["date"] >= args.start and d["date"] <= args.end]
    print(f"  Draws to test: {len(draws_in_range)}")

    # Header
    print(f"\n  {'Date':<12}{'TOD':<9}{'Winner':<8}{'TT Seeds':<20}{'Fusion':<14}{'Score':<8}{'Strats':<8}")
    print(f"  {'-'*80}")

    hits = 0
    total = 0
    total_cost = 0
    hit_details = []

    for i, target in enumerate(draws_in_range):
        tdate = target["date"]
        ttod = (target.get("tod") or "").lower()
        tvalue = target.get("value", "?")
        tactual = target.get("actual", "?")

        # Find index in sorted draws
        target_idx = None
        for j, sd in enumerate(all_draws):
            if sd["date"] == tdate and (sd.get("tod") or "").lower() == ttod:
                target_idx = j
                break
        if target_idx is None or target_idx < 3:
            continue

        # Last 3 draws for TT
        last_3 = all_draws[max(0, target_idx-3):target_idx]
        tt_union = set()
        tt_labels = []
        for d in last_3:
            val = d.get("value", "")
            if val and len(val) >= 4:
                tt_union |= generate_tt(val)
                tt_labels.append(val[-4:])

        # PW TT (the draw 2 before, simulating "prior winner" usage)
        pw_tt = set()
        if args.use_pw and target_idx >= 4:
            pw_val = all_draws[target_idx - 4].get("value", "")
            if pw_val:
                pw_tt = generate_tt(pw_val)

        # Run strategies silently
        candidates = defaultdict(lambda: {
            "strategies": [], "total_weight": 0, "total_appearances": 0,
            "tt_match": False, "pw_tt_match": False, "tt_bonus": 0, "pw_tt_bonus": 0,
        })

        for strat in RBTL_STRATEGIES:
            results, err = run_rbtl(
                base, db, state, game, tdate, ttod, strat["params"]
            )
            if err:
                continue
            if "top 20" in strat["name"].lower():
                results = results[:20]
            for r in results:
                c = r["candidate"]
                candidates[c]["strategies"].append({
                    "name": strat["name"], "rank": r["rank"], "weight": strat["weight"]
                })
                candidates[c]["total_weight"] += strat["weight"]
                candidates[c]["total_appearances"] = max(
                    candidates[c]["total_appearances"], r.get("total_appearances", 0))

        # TT scoring
        for c in candidates:
            if c in tt_union:
                candidates[c]["tt_match"] = True
                candidates[c]["tt_bonus"] = 2
            if c in pw_tt:
                candidates[c]["pw_tt_match"] = True
                candidates[c]["pw_tt_bonus"] = 1.5

        # Add TT-only candidates
        for norm in tt_union:
            if norm not in candidates:
                candidates[norm]["tt_match"] = True
                candidates[norm]["tt_bonus"] = 2
                candidates[norm]["strategies"] = []
                candidates[norm]["total_weight"] = 0

        # Score and take top N
        top = fusion_score(dict(candidates), target_n)
        top_set = set(c["candidate"] for c in top)

        # Check winner
        found = tactual in top_set
        total += 1
        total_cost += target_n

        tt_seed_str = ",".join(tt_labels[-3:])

        if found:
            hits += 1
            winner_info = next((c for c in top if c["candidate"] == tactual), None)
            rank = next((i+1 for i, c in enumerate(top) if c["candidate"] == tactual), "?")
            score = winner_info["score"] if winner_info else 0
            n_s = winner_info["n_strategies"] if winner_info else 0
            print(f"  {tdate:<12}{ttod:<9}{tvalue:<8}{tt_seed_str:<20}"
                  f"{'✅#'+str(rank)+'/'+str(target_n):<14}{score:<8.1f}{n_s:<8}")
            hit_details.append({"date": tdate, "tod": ttod, "value": tvalue,
                                "rank": rank, "score": score})
        else:
            print(f"  {tdate:<12}{ttod:<9}{tvalue:<8}{tt_seed_str:<20}"
                  f"{'❌':<14}{'—':<8}{'—':<8}")

    # Summary
    print(f"\n{'='*90}")
    print(f"  📊 BACKTEST RESULTS")
    print(f"{'='*90}")
    hit_pct = hits / total * 100 if total else 0
    revenue = hits * 5000
    profit = revenue - total_cost
    roi = revenue / total_cost * 100 if total_cost else 0

    print(f"  Draws tested:  {total}")
    print(f"  Hits:          {hits} ({hit_pct:.1f}%)")
    print(f"  Total cost:    ${total_cost:,} ({total} draws × ${target_n})")
    print(f"  Revenue:       ${revenue:,}")
    print(f"  Profit:        ${profit:,}")
    print(f"  ROI:           {roi:.0f}%")

    if hits > 0:
        avg_rank = sum(h["rank"] for h in hit_details) / len(hit_details)
        print(f"  Avg rank:      #{avg_rank:.0f}")

    # Rolling window analysis
    print(f"\n  📈 Rolling 3-draw window analysis:")
    print(f"    (Does the winner appear within any 3 consecutive draws?)")
    rolling_hits = 0
    rolling_windows = 0
    for i in range(0, total - 2, 3):
        window = draws_in_range[i:i+3]
        window_hit = False
        for d in window:
            ta = d.get("actual", "")
            # Check if we need to regenerate (simplified - just check our results)
            # In reality we'd track per-window, but approximate by checking
            # if any of the 3 draws was a hit in our main results
            if any(h["date"] == d["date"] and h["tod"] == (d.get("tod") or "").lower()
                   for h in hit_details):
                window_hit = True
        if window_hit:
            rolling_hits += 1
        rolling_windows += 1

    if rolling_windows > 0:
        print(f"    Windows tested: {rolling_windows}")
        print(f"    Windows with ≥1 hit: {rolling_hits} ({rolling_hits/rolling_windows*100:.0f}%)")
        print(f"    3-draw cost: ${target_n * 3} per window")
        window_revenue = rolling_hits * 5000
        window_cost = rolling_windows * target_n * 3
        print(f"    Window profit: ${window_revenue - window_cost:,}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        backtest(sys.argv[2:])
    else:
        main()
