#!/usr/bin/env python3
"""
pick5_mongo_scraper.py — Scrape Pick 5 draws → MongoDB (lottery_v2)
====================================================================

Scrapes lotterycorner.com (primary) with state lottery sites as backup.
Inserts directly into MongoDB lottery_v2 with full optimized schema.

Usage:
    python3 pick5_mongo_scraper.py                    # All states, 2026 only
    python3 pick5_mongo_scraper.py --state md          # Single state
    python3 pick5_mongo_scraper.py --year 2025         # Specific year
    python3 pick5_mongo_scraper.py --start 2024        # From 2024 to now
    python3 pick5_mongo_scraper.py --status            # Show what's in MongoDB
    python3 pick5_mongo_scraper.py --dry-run           # Preview, don't insert

Requirements:
    pip install pymongo requests beautifulsoup4
"""

import os
import sys
import re
import json
import argparse
import time
from datetime import datetime, date
from itertools import combinations
from collections import Counter

import requests
from bs4 import BeautifulSoup

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

MONGO_URL = os.environ.get('MONGO_URL',
    'mongodb+srv://willpowers2026:dFUATeYtHrP87gPk@cluster0.nmujtyo.mongodb.net/')
MONGO_DB = 'lottery'
MONGO_COLLECTION = 'lottery_v2'

BASE_URL = 'https://www.lotterycorner.com'

# State configs: code, full name, game slugs, game_name in MongoDB, TOD
PICK5_STATES = {
    'fl': {
        'name': 'Florida',
        'games': [
            {'slug': 'pick-5-midday', 'game_name': 'Pick 5 Midday', 'tod': 'Midday'},
            {'slug': 'pick-5-evening', 'game_name': 'Pick 5 Evening', 'tod': 'Evening'},
        ],
        'start_year': 2016,
        'backup_url': None,
    },
    'ga': {
        'name': 'Georgia',
        'games': [
            {'slug': 'georgia-five-midday', 'game_name': 'Georgia Five Midday', 'tod': 'Midday'},
            {'slug': 'georgia-five-evening', 'game_name': 'Georgia Five Evening', 'tod': 'Evening'},
        ],
        'start_year': 2010,
        'backup_url': None,
    },
    'oh': {
        'name': 'Ohio',
        'games': [
            {'slug': 'pick-5-midday', 'game_name': 'Pick 5 Midday', 'tod': 'Midday'},
            {'slug': 'pick-5-evening', 'game_name': 'Pick 5 Evening', 'tod': 'Evening'},
        ],
        'start_year': 2007,
        'backup_url': None,
    },
    'pa': {
        'name': 'Pennsylvania',
        'games': [
            {'slug': 'pick-5-midday', 'game_name': 'Pick 5 Midday', 'tod': 'Midday'},
            {'slug': 'pick-5-evening', 'game_name': 'Pick 5 Evening', 'tod': 'Evening'},
        ],
        'start_year': 2004,
        'backup_url': None,
    },
    'md': {
        'name': 'Maryland',
        'games': [
            {'slug': 'pick-5-midday', 'game_name': 'Pick 5 Midday', 'tod': 'Midday'},
            {'slug': 'pick-5-evening', 'game_name': 'Pick 5 Evening', 'tod': 'Evening'},
        ],
        'start_year': 2022,
        'backup_url': None,
    },
    'va': {
        'name': 'Virginia',
        'games': [
            {'slug': 'pick-5-day', 'game_name': 'Pick 5 Day', 'tod': 'Midday'},
            {'slug': 'pick-5-night', 'game_name': 'Pick 5 Night', 'tod': 'Evening'},
        ],
        'start_year': 2022,
        'backup_url': None,
    },
    'de': {
        'name': 'Delaware',
        'games': [
            {'slug': 'play-5-day', 'game_name': 'Play 5 Day', 'tod': 'Midday'},
            {'slug': 'play-5', 'game_name': 'Play 5 Night', 'tod': 'Evening',
             'alt_slugs': ['play-5-night', 'play-5-evening']},
        ],
        'start_year': 2022,
        'backup_url': None,
    },
    'dc': {
        'name': 'Washington DC',
        'games': [
            {'slug': 'dc-5-midday', 'game_name': 'Dc 5 Midday', 'tod': 'Midday'},
            {'slug': 'dc-5-evening', 'game_name': 'Dc 5 Evening', 'tod': 'Evening'},
        ],
        'start_year': 2010,
        'backup_url': None,
    },
    'la': {
        'name': 'Louisiana',
        'games': [
            {'slug': 'pick-5', 'game_name': 'Pick 5', 'tod': ''},
        ],
        'start_year': 2022,
        'backup_url': None,
    },
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

# ═══════════════════════════════════════════════════════════════════════
# MONGODB HELPERS
# ═══════════════════════════════════════════════════════════════════════

def get_mongo_collection():
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    return client[MONGO_DB][MONGO_COLLECTION]


def build_document(state_name, game_name, draw_date, numbers, tod):
    """Build a lottery_v2 document with all optimized fields."""
    digits = [str(n) for n in numbers]
    sorted_digits = sorted(digits)
    normalized = ''.join(sorted_digits)
    digit_ints = [int(d) for d in digits]
    digit_sum = sum(digit_ints)

    # 2DP pairs
    pairs = set()
    for combo in combinations(sorted_digits, 2):
        pairs.add(''.join(combo))
    
    # 3DP triples
    triples = set()
    for combo in combinations(sorted_digits, 3):
        triples.add(''.join(combo))

    return {
        'country': 'United States',
        'state_name': state_name,
        'game_name': game_name,
        'game_type': 'pick5',
        'date': draw_date,
        'numbers': digits,
        'normalized': normalized,
        'digits_sum': digit_sum,
        'pairs_2dp': sorted(list(pairs)),
        'triples_3dp': sorted(list(triples)),
        'tod': tod,
    }


# ═══════════════════════════════════════════════════════════════════════
# LOTTERYCORNER.COM SCRAPER (PRIMARY)
# ═══════════════════════════════════════════════════════════════════════

def scrape_lotterycorner(state_code, game_slug, year):
    """Scrape a single year of a game from lotterycorner.com.
    Returns list of (date, numbers) tuples."""
    url = f"{BASE_URL}/{state_code}/{game_slug}/{year}"
    results = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"    ⚠️  HTTP {resp.status_code} for {url}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')

        # lotterycorner uses table rows with date + numbers
        rows = soup.select('table tbody tr')
        if not rows:
            # Try alternate selector
            rows = soup.select('.result-item, .draw-result, tr[data-date]')

        for row in rows:
            try:
                # Try to extract date
                date_cell = row.select_one('td:first-child, .date')
                if not date_cell:
                    continue
                date_text = date_cell.get_text(strip=True)

                # Parse date - lotterycorner typically uses "Mon DD, YYYY" or "MM/DD/YYYY"
                draw_date = parse_date(date_text)
                if not draw_date:
                    continue

                # Extract numbers - look for individual digit spans or number cells
                num_spans = row.select('.ball, .number, .num, td.numbers span')
                if num_spans:
                    numbers = [s.get_text(strip=True) for s in num_spans]
                else:
                    # Try second column
                    cols = row.select('td')
                    if len(cols) >= 2:
                        num_text = cols[1].get_text(strip=True)
                        # Parse "1-2-3-4-5" or "1 2 3 4 5" or "12345"
                        numbers = parse_numbers(num_text)
                    else:
                        continue

                # Filter to single digits only, take first 5 (ignore Fire Ball)
                numbers = [n for n in numbers if re.match(r'^\d$', n)]
                if len(numbers) >= 5:
                    results.append((draw_date, numbers[:5]))

            except Exception as e:
                continue

    except requests.RequestException as e:
        print(f"    ❌ Request failed: {e}")

    return results


def parse_date(text):
    """Parse various date formats into a datetime object."""
    text = text.strip().replace(',', '')
    formats = [
        '%b %d %Y',       # Jan 01 2026
        '%B %d %Y',       # January 01 2026
        '%m/%d/%Y',       # 01/01/2026
        '%m-%d-%Y',       # 01-01-2026
        '%Y-%m-%d',       # 2026-01-01
        '%d %b %Y',       # 01 Jan 2026
        '%m/%d/%y',       # 01/01/26
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    
    # Try regex for "Month DD YYYY" with optional comma
    m = re.match(r'(\w+)\s+(\d{1,2})\s+(\d{4})', text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", '%B %d %Y')
        except ValueError:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", '%b %d %Y')
            except ValueError:
                pass
    return None


def parse_numbers(text):
    """Parse number string into individual digits."""
    text = text.strip()
    # Try "1-2-3-4-5"
    if '-' in text:
        return text.split('-')
    # Try "1 2 3 4 5"
    if ' ' in text:
        return text.split()
    # Try "12345" (5 consecutive digits)
    if re.match(r'^\d{5}$', text):
        return list(text)
    return []


# ═══════════════════════════════════════════════════════════════════════
# STATE LOTTERY SITE SCRAPERS (BACKUP)
# ═══════════════════════════════════════════════════════════════════════

def scrape_state_backup(state_code, game_config, year):
    """Try state-specific lottery site as backup. Returns list of (date, numbers)."""
    scrapers = {
        'fl': scrape_flalottery,
        'md': scrape_mdlottery,
        'va': scrape_valottery,
        'de': scrape_delottery,
        'dc': scrape_dclottery,
        'la': scrape_lalottery,
    }
    scraper = scrapers.get(state_code)
    if scraper:
        try:
            return scraper(game_config, year)
        except Exception as e:
            print(f"    ❌ Backup scraper failed for {state_code}: {e}")
    return []


def scrape_mdlottery(game_config, year):
    """Scrape Maryland lottery - mdlottery.com"""
    # MD provides CSV downloads
    results = []
    game_map = {'Pick 5 Midday': 'pick5mid', 'Pick 5 Evening': 'pick5eve'}
    game_id = game_map.get(game_config['game_name'], '')
    if not game_id:
        return []
    
    url = f"https://www.mdlottery.com/games/pick-5/winning-numbers/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('.table-responsive table tbody tr, .winning-numbers-table tr')
        for row in rows:
            cols = row.select('td')
            if len(cols) >= 3:
                date_text = cols[0].get_text(strip=True)
                draw_date = parse_date(date_text)
                if draw_date and draw_date.year == year:
                    nums = parse_numbers(cols[1].get_text(strip=True))
                    if len(nums) == 5:
                        results.append((draw_date, nums))
    except Exception as e:
        print(f"    ⚠️  MD backup: {e}")
    return results


def scrape_valottery(game_config, year):
    """Scrape Virginia lottery - valottery.com"""
    results = []
    url = f"https://www.valottery.com/pick5"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('.past-results tr, .results-table tr')
        for row in rows:
            cols = row.select('td')
            if len(cols) >= 2:
                date_text = cols[0].get_text(strip=True)
                draw_date = parse_date(date_text)
                if draw_date and draw_date.year == year:
                    nums = parse_numbers(cols[1].get_text(strip=True))
                    if len(nums) == 5:
                        results.append((draw_date, nums))
    except Exception as e:
        print(f"    ⚠️  VA backup: {e}")
    return results


def scrape_delottery(game_config, year):
    """Scrape Delaware lottery - delottery.com/Winning-Numbers/Search-Winners"""
    results = []
    tod = game_config.get('tod', '')
    # DE search URL: /Winning-Numbers/Search-Winners/YYYY/MM/Play5
    for month in range(1, 13):
        url = f"https://www.delottery.com/Winning-Numbers/Search-Winners/{year}/{month}/Play5"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Look for winning number entries
            rows = soup.select('.search-results-item, .winning-number-row, tr')
            for row in rows:
                text = row.get_text(' ', strip=True)
                # Try to find date and 5 digits
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
                if not date_match:
                    continue
                draw_date = parse_date(date_match.group(1))
                if not draw_date or draw_date.year != year:
                    continue
                # Find 5 single digits
                digits = re.findall(r'\b(\d)\b', text)
                if len(digits) >= 5:
                    # Check if this is the right TOD (Day/Night)
                    text_lower = text.lower()
                    if tod == 'Midday' and 'night' in text_lower:
                        continue
                    if tod == 'Evening' and 'day' in text_lower and 'night' not in text_lower:
                        continue
                    results.append((draw_date, digits[:5]))
        except Exception as e:
            continue
        time.sleep(0.3)
    return results


def scrape_flalottery(game_config, year):
    """Scrape Florida lottery - floridalottery.com past results page"""
    # FL official site is JS-rendered, so this may not work
    # Keep as placeholder
    return []


def scrape_dclottery(game_config, year):
    """Scrape DC lottery - dclottery.com"""
    results = []
    url = f"https://www.dclottery.com/games/dc-5"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('.past-winning-numbers tr, .results-row')
        for row in rows:
            cols = row.select('td')
            if len(cols) >= 2:
                draw_date = parse_date(cols[0].get_text(strip=True))
                if draw_date and draw_date.year == year:
                    nums = parse_numbers(cols[1].get_text(strip=True))
                    if len(nums) == 5:
                        results.append((draw_date, nums))
    except Exception as e:
        print(f"    ⚠️  DC backup: {e}")
    return results


def scrape_lalottery(game_config, year):
    """Scrape Louisiana lottery - louisianalottery.com"""
    results = []
    url = f"https://louisianalottery.com/pick-5/winning-numbers"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('.winning-numbers-list tr, .results-table tr')
        for row in rows:
            cols = row.select('td')
            if len(cols) >= 2:
                draw_date = parse_date(cols[0].get_text(strip=True))
                if draw_date and draw_date.year == year:
                    nums = parse_numbers(cols[1].get_text(strip=True))
                    if len(nums) == 5:
                        results.append((draw_date, nums))
    except Exception as e:
        print(f"    ⚠️  LA backup: {e}")
    return results


# ═══════════════════════════════════════════════════════════════════════
# MAIN LOGIC
# ═══════════════════════════════════════════════════════════════════════

def get_latest_date(coll, state_name, game_name):
    """Get the most recent draw date for a state/game in MongoDB."""
    doc = coll.find_one(
        {'state_name': state_name, 'game_name': game_name},
        sort=[('date', -1)]
    )
    if doc and doc.get('date'):
        return doc['date']
    return None


def scrape_and_insert(state_code, config, years, coll, dry_run=False):
    """Scrape a state and insert new draws into MongoDB."""
    state_name = config['name']
    total_new = 0
    total_skipped = 0
    total_errors = 0

    for game in config['games']:
        game_name = game['game_name']
        slug = game['slug']
        tod = game['tod']

        # Get latest date in MongoDB for this game
        latest = get_latest_date(coll, state_name, game_name)
        latest_str = latest.strftime('%Y-%m-%d') if latest else 'none'
        print(f"\n  📋 {state_name} / {game_name}")
        print(f"     Latest in MongoDB: {latest_str}")

        for year in years:
            # Primary: lotterycorner (try main slug first, then alt_slugs)
            print(f"     Scraping {year} from lotterycorner...", end=' ')
            results = scrape_lotterycorner(state_code, slug, year)

            # Try alternate slugs if primary fails
            if not results and game.get('alt_slugs'):
                for alt_slug in game['alt_slugs']:
                    print(f"trying {alt_slug}...", end=' ')
                    results = scrape_lotterycorner(state_code, alt_slug, year)
                    if results:
                        break

            if not results:
                # Backup: state lottery site
                print(f"0 results. Trying state backup...", end=' ')
                results = scrape_state_backup(state_code, game, year)

            print(f"{len(results)} draws found")

            new_count = 0
            for draw_date, numbers in results:
                # Skip if already in MongoDB
                if latest and draw_date <= latest:
                    total_skipped += 1
                    continue

                doc = build_document(state_name, game_name, draw_date, numbers, tod)

                if dry_run:
                    print(f"       [DRY] {draw_date.strftime('%Y-%m-%d')} {''.join(numbers)} {game_name}")
                    new_count += 1
                else:
                    try:
                        # Upsert to avoid duplicates
                        coll.update_one(
                            {'state_name': state_name, 'game_name': game_name, 'date': draw_date},
                            {'$set': doc},
                            upsert=True
                        )
                        new_count += 1
                    except Exception as e:
                        print(f"       ❌ Insert error: {e}")
                        total_errors += 1

            if new_count:
                print(f"     ✅ +{new_count} new draws")
            total_new += new_count

            time.sleep(0.5)  # Be nice to servers

    return total_new, total_skipped, total_errors


def show_status(coll):
    """Show current MongoDB status for Pick 5."""
    print("\n" + "=" * 60)
    print("  MongoDB Pick 5 Status (lottery_v2)")
    print("=" * 60)

    pipeline = [
        {'$match': {'game_type': 'pick5'}},
        {'$group': {
            '_id': {'state': '$state_name', 'game': '$game_name'},
            'count': {'$sum': 1},
            'first': {'$min': '$date'},
            'last': {'$max': '$date'},
        }},
        {'$sort': {'_id.state': 1, '_id.game': 1}}
    ]
    results = list(coll.aggregate(pipeline))

    if not results:
        print("\n  No Pick 5 data found in MongoDB.")
        return

    current_state = ''
    total = 0
    for r in results:
        state = r['_id']['state']
        game = r['_id']['game']
        count = r['count']
        first = r['first'].strftime('%Y-%m-%d') if r['first'] else '?'
        last = r['last'].strftime('%Y-%m-%d') if r['last'] else '?'
        total += count

        if state != current_state:
            print(f"\n  {state}")
            current_state = state
        print(f"    {game:<25} {count:>6} draws  {first} → {last}")

    print(f"\n  Total: {total:,} Pick 5 draws")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Pick 5 Scraper → MongoDB')
    parser.add_argument('--state', type=str, help='Single state code (e.g., md, va, de, dc, la)')
    parser.add_argument('--year', type=int, help='Single year to scrape')
    parser.add_argument('--start', type=int, help='Start year (scrapes from start to current)')
    parser.add_argument('--status', action='store_true', help='Show MongoDB status')
    parser.add_argument('--dry-run', action='store_true', help='Preview without inserting')
    parser.add_argument('--all-years', action='store_true', help='Scrape all years from start_year')
    args = parser.parse_args()

    coll = get_mongo_collection()

    if args.status:
        show_status(coll)
        return

    # Determine which states to scrape
    if args.state:
        code = args.state.lower()
        if code not in PICK5_STATES:
            print(f"❌ Unknown state: {code}. Available: {', '.join(PICK5_STATES.keys())}")
            sys.exit(1)
        states = {code: PICK5_STATES[code]}
    else:
        states = PICK5_STATES

    # Determine years
    current_year = date.today().year
    if args.year:
        years = [args.year]
    elif args.start:
        years = list(range(args.start, current_year + 1))
    elif args.all_years:
        years = None  # Will use per-state start_year
    else:
        # Default: current year only (most common use case)
        years = [current_year]

    print("\n" + "=" * 60)
    print("  🎯 Pick 5 Scraper → MongoDB")
    print("=" * 60)
    if args.dry_run:
        print("  ⚠️  DRY RUN — no data will be inserted")
    print(f"  States: {', '.join(s['name'] for s in states.values())}")
    print(f"  Years:  {years if years else 'all (per-state start)'}")
    print(f"  Target: MongoDB {MONGO_DB}/{MONGO_COLLECTION}")

    grand_new = 0
    grand_skip = 0
    grand_err = 0

    for code, config in states.items():
        state_years = years or list(range(config['start_year'], current_year + 1))
        print(f"\n{'─' * 50}")
        print(f"  🏛️  {config['name']} ({code.upper()}) — {len(state_years)} year(s)")
        print(f"{'─' * 50}")

        new, skip, err = scrape_and_insert(code, config, state_years, coll, args.dry_run)
        grand_new += new
        grand_skip += skip
        grand_err += err

    print(f"\n{'=' * 60}")
    print(f"  ✅ COMPLETE: +{grand_new} new | {grand_skip} skipped | {grand_err} errors")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    main()
