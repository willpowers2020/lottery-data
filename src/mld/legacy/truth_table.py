"""
Truth Table Strategy
====================
For a given 4-digit seed number, generate all combinations where each digit
can be itself, +1, or -1 (wrapping: 0-1=9, 9+1=0).

This produces 3^4 = 81 combinations per seed.

Usage:
  python3 truth_table.py                    # Interactive mode
  python3 truth_table.py 0371              # Generate combos for 0371
  python3 truth_table.py backtest 0371 Florida 2024-07-17   # Check against actuals
"""

import itertools
import sys
import requests
from collections import defaultdict


def increment_digit(d):
    """Digit + 1 with wrap: 9 → 0"""
    return (int(d) + 1) % 10


def decrement_digit(d):
    """Digit - 1 with wrap: 0 → 9"""
    return (int(d) - 1) % 10


def generate_truth_table(number):
    """
    Generate all ±1 combinations for a 4-digit number.
    Each digit can be: original, +1, or -1 (mod 10).
    Returns list of 81 strings (3^4 combinations).
    """
    digits = list(str(number).zfill(4))

    # For each digit position: [original, +1, -1]
    digit_options = [
        [d, str(increment_digit(d)), str(decrement_digit(d))]
        for d in digits
    ]

    # Cartesian product of all digit options
    combinations = list(itertools.product(*digit_options))

    # Convert tuples to strings
    return [''.join(combo) for combo in combinations]


def normalize(number_str):
    """Sort digits for normalized comparison"""
    return ''.join(sorted(number_str))


def backtest(seed, state, game_type, target_date, target_tod="",
             base_url="http://localhost:5001", db="mongo_v2"):
    """
    Generate truth table for seed, then check which combos
    were actually drawn on the target date.
    """
    combos = generate_truth_table(seed)
    combo_set = set(combos)
    combo_norm_set = set(normalize(c) for c in combos)

    print(f"\n{'='*60}")
    print(f"  🔢 TRUTH TABLE — Seed: {seed}")
    print(f"{'='*60}")
    print(f"  Digits: {' | '.join(list(str(seed).zfill(4)))}")
    print(f"  Options per digit:")
    for i, d in enumerate(str(seed).zfill(4)):
        inc = str(increment_digit(d))
        dec = str(decrement_digit(d))
        print(f"    Position {i+1}: [{d}, {inc}, {dec}]")
    print(f"  Total combinations: {len(combos)}")

    # Group by normalized (sorted) form
    norm_groups = defaultdict(list)
    for c in combos:
        norm_groups[normalize(c)].append(c)
    print(f"  Unique sorted forms: {len(norm_groups)}")

    # Fetch draws for target date
    print(f"\n  Target: {state} {game_type} {target_date} {target_tod or 'all'}")

    sep = "&" if "?" in "/api/draws/recent" else "?"
    url = f"{base_url}/api/draws/recent{sep}db={db}"

    try:
        r = requests.post(url, json={
            "state": state,
            "game_type": game_type,
            "start_date": target_date,
            "end_date": target_date,
        }, timeout=15)
        draws = r.json().get("draws", [])
    except Exception as e:
        print(f"  ⚠️  API error: {e}")
        print(f"  Showing combinations only.\n")
        print_combos(combos, seed)
        return combos

    if not draws:
        print(f"  ⚠️  No draws found for {target_date}")
        print_combos(combos, seed)
        return combos

    # Filter by TOD if specified
    if target_tod:
        draws = [d for d in draws if (d.get("tod") or "").lower() == target_tod.lower()]

    print(f"  Draws found: {len(draws)}")

    # Check each draw against truth table
    matches = []
    for d in draws:
        value = d.get("value", "")
        actual = d.get("actual", "")
        tod = (d.get("tod") or "").lower()

        # Check exact match (any permutation)
        exact = value in combo_set
        # Check normalized match
        norm_match = actual in combo_norm_set or normalize(value) in combo_norm_set

        if exact or norm_match:
            matches.append({
                "value": value,
                "actual": actual,
                "tod": tod,
                "exact": exact,
                "norm_match": norm_match,
            })

        status = "🏆 EXACT" if exact else ("✅ NORM" if norm_match else "")
        print(f"    {tod:8s} {value} (sorted: {actual}) {status}")

    print(f"\n  Results:")
    print(f"    Total draws checked: {len(draws)}")
    print(f"    Exact matches (value in TT): {sum(1 for m in matches if m['exact'])}")
    print(f"    Normalized matches (sorted): {sum(1 for m in matches if m['norm_match'])}")

    if matches:
        print(f"\n  🎯 HITS:")
        for m in matches:
            print(f"    {m['tod']:8s} {m['value']} → {'🏆 EXACT' if m['exact'] else '✅ NORM'}")

    print_combos(combos, seed)
    return combos


def print_combos(combos, seed):
    """Print all combinations in a grid format"""
    print(f"\n  📋 All 81 combinations for {seed}:")
    print(f"  {'─'*54}")
    for i in range(0, len(combos), 9):
        row = combos[i:i+9]
        print(f"    {'  '.join(row)}")
    print()


def backtest_range(seed, state, game_type, start_date, end_date,
                   base_url="http://localhost:5001", db="mongo_v2"):
    """
    Test truth table against a range of dates.
    Shows how often the winning number falls in the 81 combos.
    """
    combos = generate_truth_table(seed)
    combo_set = set(combos)
    combo_norm_set = set(normalize(c) for c in combos)

    print(f"\n{'='*60}")
    print(f"  🔢 TRUTH TABLE RANGE TEST — Seed: {seed}")
    print(f"  {start_date} to {end_date}")
    print(f"  Combos: {len(combos)} | Unique sorted: {len(combo_norm_set)}")
    print(f"{'='*60}")

    sep = "&" if "?" in "/api/draws/recent" else "?"
    url = f"{base_url}/api/draws/recent{sep}db={db}"

    try:
        r = requests.post(url, json={
            "state": state, "game_type": game_type,
            "start_date": start_date, "end_date": end_date,
        }, timeout=30)
        draws = r.json().get("draws", [])
    except Exception as e:
        print(f"  ⚠️  API error: {e}")
        return

    print(f"  Total draws: {len(draws)}\n")

    exact_hits = 0
    norm_hits = 0

    for d in draws:
        value = d.get("value", "")
        actual = d.get("actual", "")
        tod = (d.get("tod") or "").lower()
        date = d.get("date", "")

        exact = value in combo_set
        norm = actual in combo_norm_set or normalize(value) in combo_norm_set

        if exact:
            exact_hits += 1
            print(f"  🏆 {date} {tod:8s} {value} (sorted: {actual}) — EXACT MATCH")
        elif norm:
            norm_hits += 1
            print(f"  ✅ {date} {tod:8s} {value} (sorted: {actual}) — NORM MATCH")

    print(f"\n  {'─'*40}")
    print(f"  Draws tested: {len(draws)}")
    print(f"  Exact matches: {exact_hits} ({exact_hits/len(draws)*100:.1f}%)" if draws else "")
    print(f"  Norm matches:  {norm_hits} ({norm_hits/len(draws)*100:.1f}%)" if draws else "")
    print(f"  Total hits:    {exact_hits+norm_hits} ({(exact_hits+norm_hits)/len(draws)*100:.1f}%)" if draws else "")
    print(f"  Coverage: {len(combo_norm_set)}/5040 possible sorted Pick4 = {len(combo_norm_set)/5040*100:.1f}%")
    expected = len(draws) * len(combo_norm_set) / 5040
    print(f"  Expected hits by chance: {expected:.1f}")
    print(f"  Actual/Expected ratio: {(exact_hits+norm_hits)/expected:.2f}x" if expected > 0 else "")


def main():
    args = sys.argv[1:]

    if not args:
        # Interactive mode
        while True:
            try:
                number = input("\nEnter a 4-digit number (or 'q' to quit): ").strip()
                if number.lower() == 'q':
                    break
                if not number.isdigit() or len(number) != 4:
                    print("Please enter exactly 4 digits.")
                    continue

                combos = generate_truth_table(number)
                print(f"\nNumber of combinations: {len(combos)}")
                print("Combinations:")
                for combo in combos:
                    print(combo)
                break

            except ValueError as e:
                print(e)

    elif args[0] == 'backtest' and len(args) >= 4:
        # backtest <seed> <state> <date> [tod]
        seed = args[1]
        state = args[2]
        date = args[3]
        tod = args[4] if len(args) > 4 else ""
        backtest(seed, state, "pick4", date, tod)

    elif args[0] == 'range' and len(args) >= 5:
        # range <seed> <state> <start> <end>
        seed = args[1]
        state = args[2]
        start = args[3]
        end = args[4]
        backtest_range(seed, state, "pick4", start, end)

    elif len(args) == 1 and args[0].isdigit() and len(args[0]) == 4:
        # Just generate combos
        combos = generate_truth_table(args[0])
        print(f"Number of combinations: {len(combos)}")
        print("Combinations:")
        for combo in combos:
            print(combo)

    else:
        print("Usage:")
        print("  python3 truth_table.py                          # Interactive")
        print("  python3 truth_table.py 0371                     # Generate combos")
        print("  python3 truth_table.py backtest 0371 Florida 2024-07-17 [midday|evening]")
        print("  python3 truth_table.py range 0371 Florida 2024-07-01 2024-07-31")


if __name__ == "__main__":
    main()
