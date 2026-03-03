#!/usr/bin/env python3
"""
🎯 Streak Candidate Generator — From Consecutive Sums to Next Winners

Takes consecutive sum streaks from MongoDB, extracts 2DP-5DP digit profiles
from past winners, generates candidate numbers using remainder-sum logic.

Usage:
    python streak_candidates.py
    python streak_candidates.py --game pick4 --min-streak 3 --top-sums 5
    python streak_candidates.py --game pick5 --state Florida --sum 23
    python streak_candidates.py --game pick5 --sum 21 --dp 2 --type S
"""

import os
import json
import argparse
from datetime import datetime
from collections import defaultdict
from itertools import combinations

# ─── MongoDB Connection ───
MONGO_URL = os.environ.get('MONGO_URL', '')
MONGO_DB = 'lottery'
MONGO_COLLECTION = 'lottery_v2'

PICK5_STATES = [
    'Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio',
    'Pennsylvania', 'Georgia', 'Washington DC', 'Louisiana', 'Germany'
]

GAME_PATTERNS = {
    'pick4': ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4',
              'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4',
              'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4'],
    'pick5': ['pick 5 day', 'pick 5 evening', 'pick 5 midday',
              'play 5 day', 'play 5 night', 'dc 5 evening', 'dc 5 midday',
              'georgia five evening', 'georgia five midday',
              'pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5',
              'dc 5', 'dc5', 'play 5', 'play5', 'georgia five', 'georgia 5'],
}

# ─── Colors ───
B = '\033[1m'; R = '\033[91m'; O = '\033[93m'; G = '\033[92m'
C = '\033[96m'; D = '\033[2m'; M = '\033[95m'; RST = '\033[0m'
FIRE = '🔥'


def get_mongo_collection():
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    return client[MONGO_DB][MONGO_COLLECTION]


def get_games_for_state(collection, state, game_type):
    all_games = collection.distinct('game_name', {'state_name': state})
    pats = GAME_PATTERNS.get(game_type, [game_type])
    matched = [g for g in all_games if any(p in g.lower() for p in pats)]
    filtered = []
    for game in matched:
        gl = game.lower()
        is_parent = not any(tod in gl for tod in ['day', 'night', 'midday', 'evening'])
        if is_parent and any(g.lower().startswith(gl) and g.lower() != gl for g in matched):
            continue
        filtered.append(game)
    return filtered if filtered else matched


def parse_numbers(nums_field):
    if isinstance(nums_field, list):
        return [str(n) for n in nums_field]
    if isinstance(nums_field, str):
        try:
            return [str(n) for n in json.loads(nums_field)]
        except:
            return list(nums_field.replace(' ', '').replace('-', ''))
    return []


def fetch_draws(collection, state, game_type, start_dt, end_dt):
    num_digits = 5 if game_type == 'pick5' else 4
    games = get_games_for_state(collection, state, game_type)
    if not games:
        return []
    query = {
        'state_name': state,
        'game_name': {'$in': games},
        'date': {'$gte': start_dt, '$lte': end_dt}
    }
    raw = list(collection.find(query).sort('date', 1))
    draws = []
    for d in raw:
        nums = parse_numbers(d.get('winning_numbers', d.get('numbers', [])))[:num_digits]
        if len(nums) != num_digits:
            continue
        value = ''.join(nums)
        digits = [int(x) for x in nums]
        tod = d.get('tod', d.get('draw_time', ''))
        if not tod:
            gn = d.get('game_name', '').lower()
            if 'midday' in gn or 'day' in gn:
                tod = 'Midday'
            elif 'evening' in gn or 'eve' in gn or 'night' in gn:
                tod = 'Evening'
        draws.append({
            'value': value, 'date': d['date'].strftime('%Y-%m-%d') if hasattr(d['date'], 'strftime') else str(d['date'])[:10],
            'state': state, 'tod': tod or '',
            'sum': sum(digits), 'digits': digits,
            'normalized': ''.join(str(x) for x in sorted(digits)),
        })
    return draws


def find_streaks(all_draws, min_streak=2):
    by_sum = defaultdict(list)
    for d in all_draws:
        by_sum[d['sum']].append(d)
    streaks = []
    for s, group in by_sum.items():
        group.sort(key=lambda x: x['date'])
        run = [group[0]]
        for i in range(1, len(group)):
            gap = (datetime.strptime(group[i]['date'], '%Y-%m-%d') - datetime.strptime(group[i-1]['date'], '%Y-%m-%d')).days
            if gap <= 1:
                run.append(group[i])
            else:
                if len(run) >= min_streak:
                    streaks.append({'sum': s, 'length': len(run), 'draws': run[:],
                        'start': run[0]['date'], 'end': run[-1]['date'],
                        'states': sorted(set(d['state'] for d in run))})
                run = [group[i]]
        if len(run) >= min_streak:
            streaks.append({'sum': s, 'length': len(run), 'draws': run[:],
                'start': run[0]['date'], 'end': run[-1]['date'],
                'states': sorted(set(d['state'] for d in run))})
    return sorted(streaks, key=lambda x: (-x['length'], x['sum']))


# ─── DP Extraction ───
def get_unique_combos(digits, k):
    """Get unique sorted digit combinations of size k."""
    seen = set()
    for combo in combinations(digits, k):
        key = tuple(sorted(combo))
        if key not in seen:
            seen.add(key)
            yield key


def classify_number(digits):
    """Classify a number: S=straight, D=double, DD=double-double, T=triple, Q=quad, QN=quint."""
    from collections import Counter
    counts = sorted(Counter(digits).values(), reverse=True)
    if len(digits) == 4:
        if counts[0] == 4: return 'Q'
        if counts[0] == 3: return 'T'
        if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 'DD'
        if counts[0] == 2: return 'D'
        return 'S'
    else:  # pick5
        if counts[0] == 5: return 'QN'
        if counts[0] == 4: return 'Q'
        if counts[0] == 3 and len(counts) > 1 and counts[1] == 2: return 'FH'
        if counts[0] == 3: return 'T'
        if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 'DD'
        if counts[0] == 2: return 'D'
        return 'S'


# ─── Candidate Generation (remainder logic) ───
def gen_candidates_from_dp(dp_digits, target_sum, num_total_digits):
    """
    Given a DP combo (e.g., (6,7) for 2DP) and a target sum,
    generate all num_total_digits-digit numbers containing those digits
    where remaining digits sum to (target_sum - sum(dp_digits)).
    """
    dp_sum = sum(dp_digits)
    remainder = target_sum - dp_sum
    remaining_count = num_total_digits - len(dp_digits)

    if remainder < 0 or remainder > 9 * remaining_count:
        return {}

    # Generate all combos of remaining_count digits that sum to remainder
    candidates = {}

    def gen_remaining(pos, current, rem_left, digits_left):
        if digits_left == 0:
            if rem_left == 0:
                all_digits = list(dp_digits) + current
                norm = tuple(sorted(all_digits))
                if norm not in candidates:
                    ctype = classify_number(all_digits)
                    candidates[norm] = {
                        'norm': ''.join(str(d) for d in norm),
                        'type': ctype,
                        'digits': all_digits,
                    }
            return
        start = 0 if pos == 0 else current[-1] if current else 0  # keep sorted to avoid dupes
        for d in range(start, 10):
            if d > rem_left:
                break
            gen_remaining(pos + 1, current + [d], rem_left - d, digits_left - 1)

    gen_remaining(0, [], remainder, remaining_count)
    return candidates


def generate_all_candidates(streak, game_type):
    """Generate all candidates from a streak's PWs using 2DP through max-DP."""
    num_digits = 5 if game_type == 'pick5' else 4
    target_sum = streak['sum']

    # Collect all unique DP combos across all PWs in the streak
    dp_freq = {}  # {dp_size: {combo_tuple: count}}
    for dp_size in range(2, num_digits + 1):
        dp_freq[dp_size] = defaultdict(int)
        for draw in streak['draws']:
            for combo in get_unique_combos(draw['digits'], dp_size):
                dp_freq[dp_size][combo] += 1

    # Generate candidates from each DP level
    all_candidates = {}  # norm_tuple → {norm, type, sources: set(), dp_level}
    for dp_size in range(2, num_digits + 1):
        for combo, freq in sorted(dp_freq[dp_size].items(), key=lambda x: -x[1]):
            cands = gen_candidates_from_dp(combo, target_sum, num_digits)
            for norm_key, cand in cands.items():
                if norm_key not in all_candidates:
                    all_candidates[norm_key] = {
                        'norm': cand['norm'],
                        'type': cand['type'],
                        'dp_sources': [],
                        'best_dp': dp_size,
                        'max_freq': freq,
                    }
                all_candidates[norm_key]['dp_sources'].append((dp_size, combo, freq))
                if freq > all_candidates[norm_key]['max_freq']:
                    all_candidates[norm_key]['max_freq'] = freq
                if dp_size > all_candidates[norm_key]['best_dp']:
                    all_candidates[norm_key]['best_dp'] = dp_size

    return all_candidates


# ─── Display ───
TYPE_COLORS = {'S': G, 'D': O, 'DD': O, 'T': R, 'Q': R, 'FH': R, 'QN': R}

def print_streak_header(streak, idx):
    fire = FIRE * min(streak['length'] - 1, 3)
    print(f"\n{'─'*80}")
    print(f"  {B}#{idx+1}  {O}Σ{streak['sum']}{RST}  "
          f"{R if streak['length']>=4 else O}{B}{streak['length']}d streak{RST} {fire}  "
          f"{D}{streak['start']} → {streak['end']}{RST}  "
          f"States: {', '.join(streak['states'])}")
    print(f"  {D}PWs:{RST} ", end='')
    for d in streak['draws']:
        print(f"{B}{d['value']}{RST}{D}({d['state'][:3]}){RST} ", end='')
    print()


def print_dp_analysis(streak, game_type):
    """Show the DP frequency analysis."""
    num_digits = 5 if game_type == 'pick5' else 4
    print(f"\n  {C}── DP Frequency (from {len(streak['draws'])} PWs) ──{RST}")

    for dp_size in range(2, num_digits + 1):
        freq = defaultdict(int)
        for draw in streak['draws']:
            for combo in get_unique_combos(draw['digits'], dp_size):
                freq[combo] += 1

        # Show pairs with freq >= 2
        hot = sorted(freq.items(), key=lambda x: -x[1])
        hot_display = [(combo, cnt) for combo, cnt in hot if cnt >= 2]

        label = f"{dp_size}DP"
        if hot_display:
            pairs_str = '  '.join(
                f"{O}{''.join(str(d) for d in c)}({cnt}x){FIRE}{RST}" if cnt >= 3
                else f"{''.join(str(d) for d in c)}({cnt}x){FIRE}" if cnt >= 2
                else f"{''.join(str(d) for d in c)}"
                for c, cnt in hot_display[:12]
            )
            print(f"    {B}{label}:{RST} {pairs_str}  {D}({len(freq)} unique){RST}")
        else:
            print(f"    {B}{label}:{RST} {D}{len(freq)} unique, none repeated{RST}")


def print_candidates(candidates, game_type, show_types=None, max_per_type=30):
    """Display candidates grouped by type."""
    if show_types is None:
        show_types = ['S', 'D', 'DD', 'T', 'Q', 'FH', 'QN']

    by_type = defaultdict(list)
    for norm_key, cand in candidates.items():
        by_type[cand['type']].append(cand)

    # Sort each type by: best_dp desc, max_freq desc
    for t in by_type:
        by_type[t].sort(key=lambda c: (-c['best_dp'], -c['max_freq']))

    type_labels = {
        'S': 'Straights (all unique digits)',
        'D': 'Doubles (one pair)',
        'DD': 'Double-Doubles (two pairs)',
        'T': 'Triples (three of a kind)',
        'Q': 'Quads (four of a kind)',
        'FH': 'Full House (triple + pair)',
        'QN': 'Quints (five of a kind)',
    }

    total = sum(len(v) for t, v in by_type.items() if t in show_types)
    print(f"\n  {G}── Candidates: {total} total ──{RST}")

    for t in show_types:
        cands = by_type.get(t, [])
        if not cands:
            continue
        color = TYPE_COLORS.get(t, RST)
        label = type_labels.get(t, t)
        print(f"\n    {color}{B}{t} — {label} ({len(cands)}){RST}")

        # Display in rows of 10
        display = cands[:max_per_type]
        row = []
        for c in display:
            freq_badge = f"{O}*{RST}" if c['max_freq'] >= 3 else ''
            row.append(f"{c['norm']}{freq_badge}")
            if len(row) == 10:
                print(f"      {' '.join(row)}")
                row = []
        if row:
            print(f"      {' '.join(row)}")
        if len(cands) > max_per_type:
            print(f"      {D}... and {len(cands) - max_per_type} more{RST}")


def print_copyable_output(candidates, show_types=None):
    """Print space-separated candidates for easy copy-paste."""
    if show_types is None:
        show_types = ['S', 'D', 'DD', 'T', 'Q', 'FH', 'QN']
    nums = sorted(set(
        c['norm'] for c in candidates.values() if c['type'] in show_types
    ))
    print(f"\n  {M}── Copy-Paste Output ({len(nums)} candidates) ──{RST}")
    # Print in rows of 8
    for i in range(0, len(nums), 8):
        print(f"    {' '.join(nums[i:i+8])}")


def main():
    parser = argparse.ArgumentParser(description='🎯 Streak Candidate Generator')
    parser.add_argument('--start', default='2026-01-01', help='Start date')
    parser.add_argument('--end', default='2026-02-23', help='End date')
    parser.add_argument('--game', choices=['pick4', 'pick5'], default='pick5', help='Game type')
    parser.add_argument('--min-streak', type=int, default=3, help='Min streak length (default: 3)')
    parser.add_argument('--top-sums', type=int, default=5, help='Process top N streaks (default: 5)')
    parser.add_argument('--state', default='', help='Filter to single state')
    parser.add_argument('--sum', type=int, default=0, help='Filter to specific sum value')
    parser.add_argument('--type', nargs='*', default=None, help='Show only these types: S D DD T Q FH')
    parser.add_argument('--max', type=int, default=30, help='Max candidates per type to display')
    parser.add_argument('--copy', action='store_true', help='Print copy-paste format at end')
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start, '%Y-%m-%d')
    end_dt = datetime.strptime(args.end, '%Y-%m-%d')
    num_digits = 5 if args.game == 'pick5' else 4
    show_types = [t.upper() for t in args.type] if args.type else None

    print(f"\n{B}🎯 Streak Candidate Generator{RST}")
    print(f"   {D}{args.game.upper()} | {args.start} → {args.end} | min streak: {args.min_streak}d{RST}")

    print(f"\n  Connecting to MongoDB...")
    collection = get_mongo_collection()

    # Get states
    if args.state:
        states = [args.state]
    elif args.game == 'pick5':
        states = PICK5_STATES
    else:
        states = sorted(set(s for s in collection.distinct('state_name') if s))

    # Fetch all draws
    print(f"  Scanning {len(states)} states...")
    all_draws = []
    for i, state in enumerate(states):
        draws = fetch_draws(collection, state, args.game, start_dt, end_dt)
        all_draws.extend(draws)
        print(f"\r  [{i+1}/{len(states)}] {state}: {len(draws)} draws     ", end='', flush=True)
    print(f"\n  ✅ {len(all_draws):,} total draws")

    # Find streaks
    streaks = find_streaks(all_draws, args.min_streak)

    # Filter by sum if requested
    if args.sum:
        streaks = [s for s in streaks if s['sum'] == args.sum]

    if not streaks:
        print(f"\n  {R}No streaks found matching criteria.{RST}")
        return

    print(f"  {O}{len(streaks)} streaks found{RST}")

    # Process top N streaks
    process = streaks[:args.top_sums]

    for idx, streak in enumerate(process):
        print_streak_header(streak, idx)
        print_dp_analysis(streak, args.game)

        # Generate candidates
        candidates = generate_all_candidates(streak, args.game)
        print_candidates(candidates, args.game, show_types=show_types, max_per_type=args.max)

        if args.copy:
            print_copyable_output(candidates, show_types=show_types)

    # Summary
    print(f"\n{'='*80}")
    print(f"  {B}Summary{RST}")
    print(f"  Streaks analyzed: {len(process)}")
    total_cands = 0
    for streak in process:
        cands = generate_all_candidates(streak, args.game)
        total_cands += len(cands)
        by_type = defaultdict(int)
        for c in cands.values():
            by_type[c['type']] += 1
        type_str = '  '.join(f"{t}:{cnt}" for t, cnt in sorted(by_type.items()))
        print(f"    Σ{streak['sum']} ({streak['length']}d): {len(cands)} candidates — {type_str}")
    print(f"  Total unique candidates: {O}{total_cands}{RST}")
    print(f"\n{B}✅ Done{RST}\n")


if __name__ == '__main__':
    main()
