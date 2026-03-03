#!/usr/bin/env python3
"""
Reverse Engineer FL Pick4 Win: 9869 on 2019-09-15
===================================================
Sweeps lookback_days × dp_size combos to find which
configuration would have surfaced 9869 (normalized: 6899)
in the suggested plays list.

Run while your app is serving on localhost:5001:
    python3 reverse_engineer_win.py
"""

import requests
import json
from datetime import datetime
from itertools import product

# ==============================
# CONFIGURATION
# ==============================
BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

TARGET_DATE = "2019-09-15"
TARGET_NUMBER = "9869"
TARGET_NORMALIZED = "6899"
STATE = "Florida"
GAME_TYPE = "pick4"

LOOKBACK_DAYS = [3, 5, 7, 10]
DP_SIZES = [2, 3]
PREDICTION_WINDOW = 5  # days after target to check

# ==============================
# RUN SWEEP
# ==============================

def run_backtest(lookback, dp_size):
    """Run a single backtest and return results."""
    url = f"{BASE_URL}/api/rbtl/backtest?db={DB_MODE}"
    payload = {
        "state": STATE,
        "game_type": GAME_TYPE,
        "target_date": TARGET_DATE,
        "lookback_days": lookback,
        "dp_size": dp_size,
        "prediction_window": PREDICTION_WINDOW
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"error": "Connection refused - is the app running on localhost:5001?"}
    except Exception as e:
        return {"error": str(e)}


def analyze_result(data, lookback, dp_size):
    """Analyze whether our target number was found."""
    if "error" in data:
        return {
            "config": f"{lookback}d/{dp_size}DP",
            "error": data["error"]
        }
    
    # Check if target is in prediction results (winners)
    target_in_winners = False
    winner_dp_hit = False
    winner_rank = None
    winner_pairs = []
    
    for pr in data.get("prediction_results", []):
        if pr["target_actual"] == TARGET_NORMALIZED:
            target_in_winners = True
            winner_dp_hit = pr.get("dp_hit", False)
            winner_rank = pr.get("rank_in_predictions")
            winner_pairs = pr.get("shared_pairs_with_seeds", [])
            break
    
    # Check dp_matched_winners for detailed info
    matched_info = None
    for mw in data.get("dp_matched_winners", []):
        if mw["target_actual"] == TARGET_NORMALIZED:
            matched_info = mw
            break
    
    # Check if target appears in suggested plays
    in_suggested = False
    suggested_rank = None
    was_boosted = False
    for sp in data.get("suggested_plays", []):
        if sp["candidate"] == TARGET_NORMALIZED:
            in_suggested = True
            suggested_rank = sp["rank"]
            was_boosted = sp.get("boosted", False)
            break
    
    # Check if target is in hot month candidates at all
    in_candidates = TARGET_NORMALIZED in set(data.get("hot_month_candidates_sample", []))
    
    # Get total candidate count
    total_candidates = data.get("hot_month_candidate_count", 0)
    total_suggested = data.get("suggested_plays_count", 0)
    
    # Hot months found
    hot_months = data.get("hot_months", [])
    hot_month_count = len(hot_months)
    
    # Seed info
    seed_count = data.get("seed_count", 0)
    seed_perms = data.get("seed_perm_count", 0)
    
    return {
        "config": f"{lookback}d/{dp_size}DP",
        "lookback": lookback,
        "dp_size": dp_size,
        "seed_count": seed_count,
        "seed_perms": seed_perms,
        "hot_month_count": hot_month_count,
        "total_candidates": total_candidates,
        "total_suggested": total_suggested,
        "in_candidates": in_candidates,
        "in_suggested": in_suggested,
        "suggested_rank": suggested_rank,
        "was_boosted": was_boosted,
        "dp_hit": winner_dp_hit,
        "winner_pairs": winner_pairs,
        "matched_info": matched_info,
        "dp_hit_rate": data.get("dp_hit_rate", 0),
        "actionable_rate": data.get("actionable_dp_hit_rate", 0),
        "window_hit_rate": data.get("window_hit_rate", 0),
        "top3_plays": [sp["candidate"] for sp in data.get("suggested_plays", [])[:3]]
    }


def print_separator(char="=", width=80):
    print(char * width)


def main():
    print_separator()
    print(f"  REVERSE ENGINEERING: {TARGET_NUMBER} (norm: {TARGET_NORMALIZED})")
    print(f"  Target Date: {TARGET_DATE} | State: {STATE} | Game: {GAME_TYPE}")
    print(f"  Sweeping: {len(LOOKBACK_DAYS)} lookbacks × {len(DP_SIZES)} DP sizes = {len(LOOKBACK_DAYS) * len(DP_SIZES)} runs")
    print_separator()
    print()
    
    results = []
    
    for lookback, dp_size in product(LOOKBACK_DAYS, DP_SIZES):
        label = f"{lookback}d / {dp_size}DP"
        print(f"  Running {label}...", end=" ", flush=True)
        
        data = run_backtest(lookback, dp_size)
        result = analyze_result(data, lookback, dp_size)
        results.append(result)
        
        if "error" in result:
            print(f"❌ ERROR: {result['error']}")
        elif result["in_suggested"]:
            rank_info = f"Rank #{result['suggested_rank']}"
            boost_info = " (BOOSTED)" if result["was_boosted"] else ""
            print(f"✅ FOUND in plays list — {rank_info}{boost_info}")
        elif result["in_candidates"]:
            print(f"⚠️  In candidates but NOT in suggested plays")
        else:
            print(f"❌ Not found in candidates")
    
    # =====================
    # SUMMARY TABLE
    # =====================
    print()
    print_separator()
    print("  RESULTS SUMMARY")
    print_separator()
    print()
    
    header = f"{'Config':<12} {'Seeds':>6} {'Perms':>6} {'Hot Mo':>7} {'Cands':>7} {'In Cands':>9} {'In Plays':>9} {'Rank':>8} {'Boosted':>8} {'DP Hit':>7} {'Act.Rate':>9}"
    print(header)
    print("-" * len(header))
    
    for r in results:
        if "error" in r:
            print(f"{r['config']:<12} {'ERROR':>6}")
            continue
        
        in_cands = "✅" if r["in_candidates"] else "❌"
        in_plays = "✅" if r["in_suggested"] else "❌"
        rank = f"#{r['suggested_rank']}" if r["suggested_rank"] else "—"
        boosted = "⬆ YES" if r["was_boosted"] else "—"
        dp_hit = "✅" if r["dp_hit"] else "❌"
        act_rate = f"{r['actionable_rate']}%"
        
        print(f"{r['config']:<12} {r['seed_count']:>6} {r['seed_perms']:>6} {r['hot_month_count']:>7} {r['total_candidates']:>7} {in_cands:>9} {in_plays:>9} {rank:>8} {boosted:>8} {dp_hit:>7} {act_rate:>9}")
    
    # =====================
    # BEST CONFIG
    # =====================
    print()
    print_separator()
    
    # Find configs where target was in suggested plays
    found_configs = [r for r in results if r.get("in_suggested")]
    
    if found_configs:
        # Best = lowest rank (highest in list)
        best = min(found_configs, key=lambda r: r["suggested_rank"])
        print(f"  🏆 BEST CONFIG: {best['config']}")
        print(f"     Rank #{best['suggested_rank']} in suggested plays")
        if best["was_boosted"]:
            print(f"     (Boosted from outside top 50)")
        print(f"     Top 3 plays: {', '.join(best['top3_plays'])}")
        
        if best.get("matched_info"):
            mi = best["matched_info"]
            print(f"     Best Month: {mi.get('best_month', '?')} ({mi.get('best_month_seeds', '?')} seeds)")
            print(f"     Found in months: {', '.join(mi.get('appearance_months', []))}")
            print(f"     Score: {mi.get('score', '?')} | Apps: {mi.get('appearance_count', '?')} | DP Pairs: {mi.get('dp_pair_matches', '?')}")
    else:
        # Check if any config at least had it in candidates
        candidate_configs = [r for r in results if r.get("in_candidates")]
        if candidate_configs:
            print(f"  ⚠️  {TARGET_NORMALIZED} found in candidates for {len(candidate_configs)} configs but never ranked high enough for suggested plays")
            for r in candidate_configs:
                mi = r.get("matched_info", {})
                print(f"     {r['config']}: {r['total_candidates']} total candidates, best month: {mi.get('best_month', '?')}")
            print(f"\n  Consider: increasing max suggested plays from 50, or adjusting min_seeds_for_hot")
        else:
            print(f"  ❌ {TARGET_NORMALIZED} was NOT found in any configuration")
            print(f"     This number may not have strong historical patterns in the lookback windows tested")
    
    print_separator()
    print()
    print("  Tip: To test more configs, edit LOOKBACK_DAYS and DP_SIZES at the top of this script")
    print()


if __name__ == "__main__":
    main()
