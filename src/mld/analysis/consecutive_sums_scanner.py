#!/usr/bin/env python3
"""
🔥 Consecutive Sums Scanner — 2026 All States
Scans MongoDB for Pick 4 & Pick 5 draws, finds sums that repeat on consecutive days.

Usage:
    python consecutive_sums_scanner.py
    python consecutive_sums_scanner.py --min-streak 3 --game pick4
    python consecutive_sums_scanner.py --start 2026-02-01 --end 2026-02-23 --state Florida
"""

import os
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

# ─── MongoDB Connection ───
MONGO_URL = os.environ.get('MONGO_URL', '')
MONGO_DB = 'lottery'
MONGO_COLLECTION = 'lottery_v2'  # optimized schema

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


def get_mongo_collection():
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    return client[MONGO_DB][MONGO_COLLECTION]


def get_games_for_state(collection, state, game_type):
    """Find matching game names for a state+game_type."""
    all_games = collection.distinct('game_name', {'state_name': state})
    pats = GAME_PATTERNS.get(game_type, [game_type])
    matched = [g for g in all_games if any(p in g.lower() for p in pats)]

    # Remove parent games if child TOD variants exist
    filtered = []
    for game in matched:
        gl = game.lower()
        is_parent = not any(tod in gl for tod in ['day', 'night', 'midday', 'evening'])
        if is_parent:
            has_child = any(g.lower().startswith(gl) and g.lower() != gl for g in matched)
            if has_child:
                continue
        filtered.append(game)
    return filtered if filtered else matched


def parse_numbers(nums_field):
    """Parse winning numbers from MongoDB document."""
    if isinstance(nums_field, list):
        return [str(n) for n in nums_field]
    if isinstance(nums_field, str):
        try:
            return [str(n) for n in json.loads(nums_field)]
        except (json.JSONDecodeError, ValueError):
            return list(nums_field.replace(' ', '').replace('-', ''))
    return []


def fetch_draws(collection, state, game_type, start_date, end_date):
    """Fetch all draws for a state+game in date range."""
    num_digits = 5 if game_type == 'pick5' else 4
    games = get_games_for_state(collection, state, game_type)
    if not games:
        return []

    query = {
        'state_name': state,
        'game_name': {'$in': games},
        'date': {'$gte': start_date, '$lte': end_date}
    }
    raw = list(collection.find(query).sort('date', 1))
    draws = []
    for d in raw:
        nums = parse_numbers(d.get('winning_numbers', d.get('numbers', [])))
        nums = nums[:num_digits]
        if len(nums) != num_digits:
            continue
        value = ''.join(nums)
        digits = [int(x) for x in nums]
        tod = d.get('tod', d.get('draw_time', ''))
        if not tod:
            gn = d.get('game_name', '').lower()
            if 'midday' in gn or 'mid-day' in gn or 'day' in gn:
                tod = 'Midday'
            elif 'evening' in gn or 'eve' in gn or 'night' in gn:
                tod = 'Evening'
            else:
                tod = ''
        draws.append({
            'value': value,
            'date': d['date'].strftime('%Y-%m-%d') if hasattr(d['date'], 'strftime') else str(d['date'])[:10],
            'state': state,
            'tod': tod,
            'sum': sum(digits),
            'digits': digits,
            'normalized': ''.join(str(x) for x in sorted(digits)),
            'game': d.get('game_name', ''),
        })
    return draws


def find_streaks(all_draws, min_streak=2):
    """Find consecutive sum streaks (gap ≤ 1 day between draws with same sum)."""
    by_sum = defaultdict(list)
    for d in all_draws:
        by_sum[d['sum']].append(d)

    streaks = []
    for s, group in by_sum.items():
        group.sort(key=lambda x: x['date'])
        run = [group[0]]
        for i in range(1, len(group)):
            d_prev = datetime.strptime(group[i - 1]['date'], '%Y-%m-%d')
            d_curr = datetime.strptime(group[i]['date'], '%Y-%m-%d')
            gap = (d_curr - d_prev).days
            if gap <= 1:
                run.append(group[i])
            else:
                if len(run) >= min_streak:
                    streaks.append(build_streak(s, run))
                run = [group[i]]
        if len(run) >= min_streak:
            streaks.append(build_streak(s, run))

    return sorted(streaks, key=lambda x: (-x['length'], -len(x['states']), x['sum']))


def build_streak(s, run):
    states = list(set(d['state'] for d in run))
    return {
        'sum': s,
        'length': len(run),
        'start': run[0]['date'],
        'end': run[-1]['date'],
        'states': sorted(states),
        'draws': run,
    }


# ─── Display ───
BOLD = '\033[1m'
RED = '\033[91m'
ORA = '\033[93m'
GRN = '\033[92m'
CYN = '\033[96m'
DIM = '\033[2m'
RST = '\033[0m'
FIRE = '🔥'


def print_header(title, count=None):
    print(f"\n{'='*80}")
    cnt = f" ({count})" if count is not None else ""
    print(f"  {BOLD}{title}{cnt}{RST}")
    print(f"{'='*80}")


def print_streak(streak, idx):
    s = streak
    length_color = RED if s['length'] >= 4 else ORA if s['length'] >= 3 else GRN
    fire = FIRE * min(s['length'] - 1, 3)

    print(f"\n  {BOLD}#{idx+1}{RST}  "
          f"{ORA}Σ{s['sum']}{RST}  "
          f"{length_color}{BOLD}{s['length']}d streak{RST} {fire}  "
          f"{DIM}{s['start']} → {s['end']}{RST}  "
          f"States: {', '.join(s['states'])}")

    # Draw details
    for i, d in enumerate(s['draws']):
        gap = ''
        if i > 0:
            d_prev = datetime.strptime(s['draws'][i - 1]['date'], '%Y-%m-%d')
            d_curr = datetime.strptime(d['date'], '%Y-%m-%d')
            g = (d_curr - d_prev).days
            if g == 0:
                gap = f" {ORA}[0d]{FIRE}{RST}"
            elif g == 1:
                gap = f" {ORA}[1d]{FIRE}{RST}"
            else:
                gap = f" [{g}d]"

        tod_str = f" {DIM}{d['tod']}{RST}" if d['tod'] else ""
        print(f"    {DIM}{d['date']}{RST}  {BOLD}{d['value']}{RST}  "
              f"{CYN}{d['state'][:12]}{RST}{tod_str}{gap}")


def print_summary(game_type, streaks, total_draws, states_scanned):
    print(f"\n  {DIM}{'─'*60}{RST}")
    if not streaks:
        print(f"  No consecutive sum streaks found.")
        return

    longest = max(s['length'] for s in streaks)
    # Most common sum in streaks
    sum_freq = defaultdict(int)
    for s in streaks:
        sum_freq[s['sum']] += s['length']
    hottest = sorted(sum_freq.items(), key=lambda x: -x[1])[0]

    # Streaks by length
    by_len = defaultdict(int)
    for s in streaks:
        by_len[s['length']] += 1

    print(f"  {BOLD}Summary — {game_type.upper()}{RST}")
    print(f"  States scanned: {states_scanned}")
    print(f"  Total draws:    {total_draws:,}")
    print(f"  Streaks found:  {ORA}{len(streaks)}{RST}")
    print(f"  Longest streak: {RED}{longest}d{RST}")
    print(f"  Hottest sum:    {ORA}Σ{hottest[0]}{RST} ({hottest[1]} total consecutive days)")
    print(f"  Breakdown:      ", end='')
    for length in sorted(by_len.keys(), reverse=True):
        print(f"{length}d={by_len[length]}  ", end='')
    print()


def main():
    parser = argparse.ArgumentParser(description='🔥 Consecutive Sums Scanner — 2026')
    parser.add_argument('--start', default='2026-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', default='2026-02-23', help='End date (YYYY-MM-DD)')
    parser.add_argument('--min-streak', type=int, default=2, help='Minimum streak length (default: 2)')
    parser.add_argument('--game', choices=['pick4', 'pick5', 'both'], default='both', help='Game type')
    parser.add_argument('--state', default='', help='Single state (default: all states)')
    parser.add_argument('--top', type=int, default=50, help='Show top N streaks per game (default: 50)')
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start, '%Y-%m-%d')
    end_dt = datetime.strptime(args.end, '%Y-%m-%d')

    print(f"\n{BOLD}🔥 Consecutive Sums Scanner{RST}")
    print(f"   {DIM}Date range: {args.start} → {args.end} | Min streak: {args.min_streak}d | Game: {args.game}{RST}")

    print(f"\n  Connecting to MongoDB...")
    collection = get_mongo_collection()
    print(f"  ✅ Connected")

    # Get states
    if args.state:
        p4_states = [args.state] if args.game in ('pick4', 'both') else []
        p5_states = [args.state] if args.game in ('pick5', 'both') else []
    else:
        if args.game in ('pick4', 'both'):
            p4_states = sorted(set(s for s in collection.distinct('state_name') if s))
        else:
            p4_states = []
        if args.game in ('pick5', 'both'):
            p5_states = PICK5_STATES
        else:
            p5_states = []

    # ─── PICK 4 ───
    if p4_states:
        print_header("PICK 4 — Scanning", len(p4_states))
        all_p4 = []
        for i, state in enumerate(p4_states):
            draws = fetch_draws(collection, state, 'pick4', start_dt, end_dt)
            all_p4.extend(draws)
            status = f"  [{i+1}/{len(p4_states)}] {state}: {len(draws)} draws"
            print(f"\r{status:<60}", end='', flush=True)
        print()

        p4_streaks = find_streaks(all_p4, args.min_streak)
        print_header(f"PICK 4 STREAKS (≥{args.min_streak}d)", len(p4_streaks))
        for i, s in enumerate(p4_streaks[:args.top]):
            print_streak(s, i)
        if len(p4_streaks) > args.top:
            print(f"\n  {DIM}... and {len(p4_streaks) - args.top} more (use --top to see more){RST}")
        print_summary('Pick 4', p4_streaks, len(all_p4), len(p4_states))

    # ─── PICK 5 ───
    if p5_states:
        print_header("PICK 5 — Scanning", len(p5_states))
        all_p5 = []
        for i, state in enumerate(p5_states):
            draws = fetch_draws(collection, state, 'pick5', start_dt, end_dt)
            all_p5.extend(draws)
            status = f"  [{i+1}/{len(p5_states)}] {state}: {len(draws)} draws"
            print(f"\r{status:<60}", end='', flush=True)
        print()

        p5_streaks = find_streaks(all_p5, args.min_streak)
        print_header(f"PICK 5 STREAKS (≥{args.min_streak}d)", len(p5_streaks))
        for i, s in enumerate(p5_streaks[:args.top]):
            print_streak(s, i)
        if len(p5_streaks) > args.top:
            print(f"\n  {DIM}... and {len(p5_streaks) - args.top} more{RST}")
        print_summary('Pick 5', p5_streaks, len(all_p5), len(p5_states))

    print(f"\n{BOLD}✅ Done{RST}\n")


if __name__ == '__main__':
    main()
