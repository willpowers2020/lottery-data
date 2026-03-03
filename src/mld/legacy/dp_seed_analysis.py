"""
2DP Seed-Winner Correlation Analysis
======================================
For each draw, checks if the winner shares any 2-digit pairs
with the most recent seed (Sniper mode).

Run:  python3 dp_seed_analysis.py
"""

import requests, json, sys
from datetime import datetime, timedelta
from itertools import combinations

def prompt(msg, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{msg}{suffix}: ").strip()
    return val if val else default

def api_url(base, path, db):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

def get_2dp(number):
    """Get all 2-digit pairs from a 4-digit number (sorted digits)."""
    digits = sorted(number.replace("-", ""))
    if len(digits) < 4:
        return set()
    pairs = set()
    for i in range(len(digits)):
        for j in range(i + 1, len(digits)):
            pairs.add(digits[i] + digits[j])
    return pairs

def main():
    print("=" * 70)
    print("  📊 2DP SEED-WINNER CORRELATION ANALYSIS")
    print("=" * 70)
    print()

    base = prompt("Flask app URL", "http://localhost:5001")
    db = prompt("DB mode", "mongo_v2")
    state = prompt("State (full name)", "Florida")
    game_type = prompt("Game type", "pick4")
    start_date = prompt("Start date", "2026-01-01")
    end_date = prompt("End date", "2026-02-18")
    pw_days = int(prompt("Seed window days", "5"))

    # Fetch all draws in range
    print(f"\n⏳ Loading draws from {start_date} to {end_date}...")
    r = requests.post(api_url(base, "/api/draws/recent", db), json={
        "state": state, "game_type": game_type,
        "start_date": start_date, "end_date": end_date
    }, timeout=15)
    all_draws = r.json().get("draws", [])

    if not all_draws:
        print("❌ No draws found")
        return

    # Sort chronologically
    tod_ord = {"evening": 2, "night": 2, "midday": 1, "day": 1}
    all_draws.sort(key=lambda d: (d["date"], tod_ord.get((d.get("tod") or "").lower(), 0)))

    print(f"📋 {len(all_draws)} draws found")

    # For each draw, find its seed (the most recent prior draw)
    results = []
    share_0 = 0
    share_1 = 0
    share_2 = 0
    share_3plus = 0
    total_checked = 0

    print(f"\n{'Date':<12}{'TOD':<9}{'Winner':<8}{'Seed':<8}{'Shared':<10}{'Pairs'}")
    print("-" * 65)

    for i, draw in enumerate(all_draws):
        target_date = draw["date"]
        target_tod = (draw.get("tod") or "").lower()
        winner_actual = draw.get("actual", "")
        winner_norm = "".join(sorted(winner_actual.replace("-", "")))

        # Find seed: most recent draw BEFORE this one
        # For evening: seed = same day midday (if exists) or previous day evening
        # For midday: seed = previous day evening
        seed = None
        for j in range(i - 1, -1, -1):
            prev = all_draws[j]
            prev_date = prev["date"]
            prev_tod = (prev.get("tod") or "").lower()

            # Must be before target
            if prev_date > target_date:
                continue
            if prev_date == target_date:
                if target_tod == "evening" and prev_tod == "midday":
                    seed = prev
                    break
                else:
                    continue
            else:
                # Previous day — take it
                seed = prev
                break

        if seed is None:
            # Try fetching from further back
            td = datetime.strptime(target_date, "%Y-%m-%d")
            sd = (td - timedelta(days=pw_days)).strftime("%Y-%m-%d")
            try:
                r2 = requests.post(api_url(base, "/api/draws/recent", db), json={
                    "state": state, "game_type": game_type,
                    "start_date": sd, "end_date": target_date
                }, timeout=10)
                extra_draws = r2.json().get("draws", [])
                # Find most recent before target
                for ed in sorted(extra_draws, key=lambda d: (d["date"], tod_ord.get((d.get("tod") or "").lower(), 0)), reverse=True):
                    ed_date = ed["date"]
                    ed_tod = (ed.get("tod") or "").lower()
                    if ed_date < target_date:
                        seed = ed
                        break
                    elif ed_date == target_date and target_tod == "evening" and ed_tod == "midday":
                        seed = ed
                        break
            except:
                pass

        if seed is None:
            continue

        seed_actual = seed.get("actual", "")
        seed_norm = "".join(sorted(seed_actual.replace("-", "")))

        # Get 2DP pairs
        winner_pairs = get_2dp(winner_norm)
        seed_pairs = get_2dp(seed_norm)
        shared = winner_pairs & seed_pairs
        num_shared = len(shared)

        total_checked += 1
        if num_shared == 0:
            share_0 += 1
        elif num_shared == 1:
            share_1 += 1
        elif num_shared == 2:
            share_2 += 1
        else:
            share_3plus += 1

        shared_str = ", ".join(sorted(shared)) if shared else "NONE"
        marker = "✅" if num_shared > 0 else "❌"

        results.append({
            "date": target_date,
            "tod": target_tod,
            "winner": winner_actual,
            "winner_norm": winner_norm,
            "seed": seed_actual,
            "seed_norm": seed_norm,
            "shared_pairs": sorted(shared),
            "num_shared": num_shared,
        })

        print(f"{target_date:<12}{target_tod:<9}{winner_actual:<8}{seed_actual:<8}"
              f"{marker} {num_shared:<7}{shared_str}")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"  📊 SUMMARY — {total_checked} draws analyzed")
    print(f"{'=' * 70}")

    has_shared = share_1 + share_2 + share_3plus
    pct_shared = has_shared / total_checked * 100 if total_checked > 0 else 0

    print(f"\n  Winners sharing ≥1 2DP with seed: {has_shared}/{total_checked} ({pct_shared:.1f}%)")
    print(f"  Winners sharing 0 pairs:   {share_0} ({share_0/total_checked*100:.1f}%)")
    print(f"  Winners sharing 1 pair:    {share_1} ({share_1/total_checked*100:.1f}%)")
    print(f"  Winners sharing 2 pairs:   {share_2} ({share_2/total_checked*100:.1f}%)")
    print(f"  Winners sharing 3+ pairs:  {share_3plus} ({share_3plus/total_checked*100:.1f}%)")

    # Expected by chance
    # Pick4 box has C(10,4)=210 combos, each has C(4,2)=6 pairs from C(10,2)=45 possible
    # Probability two random pick4 numbers share at least 1 pair:
    # P(share ≥1) = 1 - P(share 0)
    # Each number has 6 pairs out of 45. P(no overlap) = C(39,6)/C(45,6) ≈ 0.425
    # So P(≥1 shared) ≈ 57.5% by random chance
    print(f"\n  📐 EXPECTED BY RANDOM CHANCE:")
    print(f"  Two random pick4 numbers share ≥1 2DP pair ~57% of the time")
    print(f"  (each has 6 pairs from 45 possible 2-digit combos)")
    print(f"\n  Your observed rate: {pct_shared:.1f}%")
    if pct_shared > 57:
        print(f"  → {pct_shared - 57:.1f}% ABOVE random chance — signal detected!")
    elif pct_shared < 57:
        print(f"  → {57 - pct_shared:.1f}% BELOW random chance")
    else:
        print(f"  → Right at chance level")

    # Deeper: among winners found by cluster, how many share 2DP?
    # vs among winners NOT found, how many share 2DP?
    print(f"\n{'=' * 70}")
    print(f"  🔍 BREAKDOWN BY SHARED PAIR COUNT")
    print(f"{'=' * 70}")

    print(f"\n  {'Shared Pairs':<16}{'Count':<10}{'%':<10}{'Implication'}")
    print("  " + "-" * 55)
    print(f"  {'0 pairs':<16}{share_0:<10}{share_0/total_checked*100:>5.1f}%    DP filter would REMOVE winner")
    print(f"  {'1 pair':<16}{share_1:<10}{share_1/total_checked*100:>5.1f}%    DP filter keeps (barely)")
    print(f"  {'2 pairs':<16}{share_2:<10}{share_2/total_checked*100:>5.1f}%    DP filter keeps (strong)")
    print(f"  {'3+ pairs':<16}{share_3plus:<10}{share_3plus/total_checked*100:>5.1f}%    DP filter keeps (very strong)")

    dp_keeps = share_1 + share_2 + share_3plus
    dp_removes = share_0
    print(f"\n  DP filter verdict:")
    print(f"    Correctly keeps winner:  {dp_keeps}/{total_checked} ({dp_keeps/total_checked*100:.1f}%)")
    print(f"    Incorrectly removes:     {dp_removes}/{total_checked} ({dp_removes/total_checked*100:.1f}%)")

    # TOD breakdown
    print(f"\n{'=' * 70}")
    print(f"  🕐 BY TIME OF DAY")
    print(f"{'=' * 70}")

    for tod_check in ["evening", "midday"]:
        tod_results = [r for r in results if r["tod"] == tod_check]
        if not tod_results:
            continue
        tod_shared = len([r for r in tod_results if r["num_shared"] > 0])
        print(f"\n  {tod_check.upper()}: {tod_shared}/{len(tod_results)} ({tod_shared/len(tod_results)*100:.1f}%) share ≥1 2DP")
        # Avg shared
        avg_shared = sum(r["num_shared"] for r in tod_results) / len(tod_results)
        print(f"    Avg shared pairs: {avg_shared:.2f}")

    # Most common shared pairs
    print(f"\n{'=' * 70}")
    print(f"  🔢 MOST COMMON SHARED PAIRS")
    print(f"{'=' * 70}")

    from collections import Counter
    pair_counts = Counter()
    for r in results:
        for p in r["shared_pairs"]:
            pair_counts[p] += 1

    print(f"\n  {'Pair':<8}{'Times Shared':<15}{'% of draws'}")
    print("  " + "-" * 35)
    for pair, count in pair_counts.most_common(15):
        print(f"  {pair:<8}{count:<15}{count/total_checked*100:.1f}%")

    print(f"\n  Done! 🎉")


if __name__ == "__main__":
    main()
