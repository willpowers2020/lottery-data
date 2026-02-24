#!/usr/bin/env python3
"""
🎯 Pick 5 Candidate Generator — 3DP → Sum-Matched Candidates

Input: One or more 5-digit past winners
Process:
  1. Extract all unique 3DP combos from each PW
  2. For each 3DP, find all 2-digit remainders that complete the target sum
  3. Generate every valid 5-digit normalized candidate
  4. Classify: S (straight), D (double), DD (double-double), T (triple), FH (full house), Q (quad)
  5. Dedupe across all sources, track which 3DPs generated each candidate

Usage:
    python pick5_gen.py 73382 55445
    python pick5_gen.py 73382 55445 40388 79313 87530 --type S D
    python pick5_gen.py 41759 --sum 26
    echo "73382 55445 40388" | python pick5_gen.py --stdin
"""

import sys
import argparse
from itertools import combinations
from collections import Counter, defaultdict

# ─── Colors ───
B = '\033[1m'; R = '\033[91m'; O = '\033[93m'; G = '\033[92m'
C = '\033[96m'; D = '\033[2m'; M = '\033[95m'; U = '\033[4m'; RST = '\033[0m'
FIRE = '🔥'


def classify(digits):
    """Classify a 5-digit number by its digit pattern."""
    counts = sorted(Counter(digits).values(), reverse=True)
    if counts[0] == 5: return 'QN'
    if counts[0] == 4: return 'Q'
    if counts[0] == 3 and len(counts) > 1 and counts[1] == 2: return 'FH'
    if counts[0] == 3: return 'T'
    if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 'DD'
    if counts[0] == 2: return 'D'
    return 'S'


def get_3dp_combos(digits):
    """Get all unique sorted 3-digit combinations from a 5-digit number."""
    seen = set()
    for combo in combinations(digits, 3):
        key = tuple(sorted(combo))
        if key not in seen:
            seen.add(key)
            yield key


def gen_candidates_from_3dp(triple, target_sum):
    """
    Given a 3DP (e.g., (3,7,8)) and target sum,
    generate all 5-digit candidates where:
      - contains the 3 digits from triple
      - 2 remaining digits sum to (target_sum - sum(triple))
      - remaining digits are in sorted order (to avoid internal dupes)
    Returns dict of {normalized_tuple: {norm_str, type, remaining}}
    """
    remainder = target_sum - sum(triple)
    if remainder < 0 or remainder > 18:
        return {}

    candidates = {}
    for a in range(0, 10):
        b = remainder - a
        if b < a or b > 9:  # a <= b to avoid dupes
            continue
        all_digits = list(triple) + [a, b]
        norm = tuple(sorted(all_digits))
        if norm not in candidates:
            candidates[norm] = {
                'norm': ''.join(str(d) for d in norm),
                'type': classify(all_digits),
                'remaining': (a, b),
            }
    return candidates


def main():
    parser = argparse.ArgumentParser(description='🎯 Pick 5 Candidate Generator (3DP → Candidates)')
    parser.add_argument('numbers', nargs='*', help='5-digit past winners (e.g., 73382 55445 40388)')
    parser.add_argument('--sum', type=int, default=0, help='Override target sum (default: auto from PWs)')
    parser.add_argument('--type', nargs='*', default=None, help='Filter types: S D DD T FH Q QN')
    parser.add_argument('--max', type=int, default=0, help='Max candidates to show (0 = all)')
    parser.add_argument('--stdin', action='store_true', help='Read numbers from stdin')
    parser.add_argument('--copy', action='store_true', help='Print copy-paste block at end')
    parser.add_argument('--no-color', action='store_true', help='Disable colors')
    args = parser.parse_args()

    # Disable colors if requested
    global B, R, O, G, C, D, M, U, RST
    if args.no_color:
        B = R = O = G = C = D = M = U = RST = ''

    # Collect input numbers
    numbers = list(args.numbers) if args.numbers else []
    if args.stdin or (not numbers and not sys.stdin.isatty()):
        for line in sys.stdin:
            numbers.extend(line.strip().split())

    if not numbers:
        print(f"\n  {R}No input numbers provided.{RST}")
        print(f"  Usage: python pick5_gen.py 73382 55445 40388")
        print(f"         python pick5_gen.py 73382 --sum 26")
        return

    # Validate
    pws = []
    for n in numbers:
        n = n.strip().replace('-', '').replace(' ', '')
        if len(n) != 5 or not n.isdigit():
            print(f"  {O}⚠ Skipping invalid: {n} (need 5 digits){RST}")
            continue
        digits = [int(c) for c in n]
        pws.append({'value': n, 'digits': digits, 'sum': sum(digits),
                     'normalized': ''.join(str(d) for d in sorted(digits))})

    if not pws:
        print(f"\n  {R}No valid 5-digit numbers provided.{RST}")
        return

    # Determine target sum
    if args.sum:
        target_sum = args.sum
    else:
        # Use the most common sum across all PWs
        sum_freq = Counter(pw['sum'] for pw in pws)
        target_sum = sum_freq.most_common(1)[0][0]
        if len(sum_freq) > 1:
            print(f"\n  {O}Multiple sums detected: {dict(sum_freq)}{RST}")
            print(f"  {O}Using most common: Σ{target_sum} (use --sum to override){RST}")

    show_types = set(t.upper() for t in args.type) if args.type else None

    # ─── Header ───
    print(f"\n{B}🎯 Pick 5 Candidate Generator{RST}")
    print(f"   {D}PWs: {' '.join(pw['value'] for pw in pws)} | Target Sum: Σ{target_sum}{RST}")

    # ─── Step 1: Extract all 3DP combos ───
    all_3dp = defaultdict(int)  # combo_tuple → frequency across all PWs
    pw_3dp_map = {}  # combo_tuple → list of PW values that contain it

    for pw in pws:
        for combo in get_3dp_combos(pw['digits']):
            all_3dp[combo] += 1
            if combo not in pw_3dp_map:
                pw_3dp_map[combo] = []
            pw_3dp_map[combo].append(pw['value'])

    # Sort by frequency desc
    sorted_3dp = sorted(all_3dp.items(), key=lambda x: (-x[1], x[0]))

    print(f"\n  {C}── 3DP Combos: {len(sorted_3dp)} unique (from {len(pws)} PWs) ──{RST}")
    # Show the 3DPs, highlight those appearing in multiple PWs
    row = []
    for combo, freq in sorted_3dp:
        combo_str = ''.join(str(d) for d in combo)
        if freq >= 3:
            row.append(f"{O}{B}{combo_str}({freq}x){FIRE}{RST}")
        elif freq >= 2:
            row.append(f"{combo_str}({freq}x){FIRE}")
        else:
            row.append(combo_str)
        if len(row) == 10:
            print(f"    {' '.join(row)}")
            row = []
    if row:
        print(f"    {' '.join(row)}")

    # ─── Step 2: Generate candidates from each 3DP ───
    print(f"\n  {C}── Generating candidates for Σ{target_sum} ──{RST}")

    all_candidates = {}  # norm_tuple → {norm, type, sources: [(3dp, remaining, freq)]}
    for combo, freq in sorted_3dp:
        cands = gen_candidates_from_3dp(combo, target_sum)
        for norm_key, cand in cands.items():
            if norm_key not in all_candidates:
                all_candidates[norm_key] = {
                    'norm': cand['norm'],
                    'type': cand['type'],
                    'sources': [],
                    'max_freq': 0,
                    'source_count': 0,
                }
            all_candidates[norm_key]['sources'].append({
                'triple': combo,
                'remaining': cand['remaining'],
                'freq': freq,
            })
            all_candidates[norm_key]['source_count'] += 1
            if freq > all_candidates[norm_key]['max_freq']:
                all_candidates[norm_key]['max_freq'] = freq

    # Mark which candidates ARE past winners
    pw_norms = set(pw['normalized'] for pw in pws)

    # ─── Step 3: Display by type ───
    by_type = defaultdict(list)
    for norm_key, cand in all_candidates.items():
        by_type[cand['type']].append(cand)

    # Sort within each type: most 3DP sources first, then max freq
    for t in by_type:
        by_type[t].sort(key=lambda c: (-c['source_count'], -c['max_freq'], c['norm']))

    type_order = ['S', 'D', 'DD', 'T', 'FH', 'Q', 'QN']
    type_labels = {
        'S': 'Straights (all unique)', 'D': 'Doubles (one pair)',
        'DD': 'Double-Doubles (two pairs)', 'T': 'Triples (three of a kind)',
        'FH': 'Full House (3+2)', 'Q': 'Quads (four same)', 'QN': 'Quints (all same)',
    }
    type_colors = {'S': G, 'D': O, 'DD': O, 'T': R, 'FH': R, 'Q': R, 'QN': R}

    filtered_total = 0
    for t in type_order:
        cands = by_type.get(t, [])
        if not cands:
            continue
        if show_types and t not in show_types:
            continue
        filtered_total += len(cands)

    print(f"\n  {G}{B}Total: {filtered_total} candidates for Σ{target_sum}{RST}")

    all_for_copy = []
    for t in type_order:
        cands = by_type.get(t, [])
        if not cands:
            continue
        if show_types and t not in show_types:
            continue

        color = type_colors.get(t, RST)
        label = type_labels.get(t, t)
        print(f"\n  {color}{B}  {t} — {label} ({len(cands)}){RST}")

        display = cands[:args.max] if args.max else cands
        row = []
        for c in display:
            is_pw = c['norm'] in pw_norms
            pw_tag = f" {M}★PW{RST}" if is_pw else ''
            freq_tag = f"{O}*{RST}" if c['max_freq'] >= 2 else ''
            src_tag = f"{D}[{c['source_count']}]{RST}" if c['source_count'] >= 3 else ''
            row.append(f"{c['norm']}{freq_tag}{src_tag}{pw_tag}")
            if len(row) == 8:
                print(f"      {' '.join(row)}")
                row = []
        if row:
            print(f"      {' '.join(row)}")
        if args.max and len(cands) > args.max:
            print(f"      {D}... and {len(cands) - args.max} more{RST}")

        all_for_copy.extend(c['norm'] for c in cands)

    # ─── Step 4: Stats ───
    print(f"\n  {'─'*60}")
    print(f"  {B}Stats{RST}")
    print(f"  Input PWs:       {len(pws)}")
    print(f"  Target Sum:      Σ{target_sum}")
    print(f"  3DP combos:      {len(sorted_3dp)}")
    hot_3dp = [(c, f) for c, f in sorted_3dp if f >= 2]
    if hot_3dp:
        print(f"  Hot 3DPs (2x+):  {', '.join(''.join(str(d) for d in c) + f'({f}x)' for c,f in hot_3dp[:10])}")
    print(f"  Candidates:      {filtered_total}")
    for t in type_order:
        cnt = len(by_type.get(t, []))
        if cnt and (not show_types or t in show_types):
            print(f"    {t:3s}: {cnt}")

    # ─── Copy output ───
    if args.copy:
        unique = sorted(set(all_for_copy))
        print(f"\n  {M}── Copy-Paste ({len(unique)} candidates) ──{RST}")
        for i in range(0, len(unique), 8):
            print(f"    {' '.join(unique[i:i+8])}")

    print(f"\n{B}✅ Done{RST}\n")


if __name__ == '__main__':
    main()
