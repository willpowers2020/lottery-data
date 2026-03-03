#!/usr/bin/env python3
"""
Pick 5 Nexus Strategy Analyzer
===============================
Queries MLD MongoDB (lottery_v2) for Pick 5 draws across all states,
computes Sums, TD (Total Differences), and ΔSumsTD,
then analyzes patterns to predict the next draw window.

Usage:
    python3 pick5_nexus.py                          # Default: last 2 years
    python3 pick5_nexus.py --start 2020-01-01       # Custom start
    python3 pick5_nexus.py --start 2023-01-01 --end 2025-02-21
    python3 pick5_nexus.py --delta 7                # Target delta (default: 7)
    python3 pick5_nexus.py --no-abs                 # Don't use absolute value
    python3 pick5_nexus.py --export                 # Export to CSV
    python3 pick5_nexus.py --state Pennsylvania     # Filter single state
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import statistics

try:
    from pymongo import MongoClient
except ImportError:
    print("❌ pymongo not installed. Run: pip3 install pymongo")
    sys.exit(1)

# ============================================================
# DATABASE CONFIG
# ============================================================
MONGO_URL = os.environ.get(
    'MONGO_URL',
    'mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/'
)
MONGO_DB = 'lottery'
MONGO_COLLECTION = 'lottery_v2'

# ============================================================
# COMPUTATION FUNCTIONS
# ============================================================

def calc_td(number_str):
    """Calculate Total Differences: sum of |digit[i] - digit[i+1]| for consecutive digits."""
    digits = [int(d) for d in str(number_str)]
    td = 0
    for i in range(len(digits) - 1):
        td += abs(digits[i] - digits[i + 1])
    return td


def calc_sums(number_str):
    """Calculate digit sum."""
    return sum(int(d) for d in str(number_str))


def days_between(d1_str, d2_str):
    """Days between two date strings."""
    fmt = '%Y-%m-%d'
    try:
        a = datetime.strptime(d1_str[:10], fmt)
        b = datetime.strptime(d2_str[:10], fmt)
        return abs((b - a).days)
    except:
        return 0


# ============================================================
# DATABASE QUERY
# ============================================================

def fetch_pick5_draws(start_date, end_date, state=None):
    """Fetch all Pick 5 draws from MongoDB in date range."""
    print(f"\n🔌 Connecting to MongoDB Atlas...")
    
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
        # Test connection
        client.admin.command('ping')
        print(f"✅ Connected successfully")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)
    
    db = client[MONGO_DB]
    coll = db[MONGO_COLLECTION]
    
    # Convert string dates to datetime objects (MongoDB stores dates as datetime)
    start_dt = datetime.strptime(start_date[:10], '%Y-%m-%d')
    end_dt = datetime.strptime(end_date[:10], '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    query = {
        'game_type': 'pick5',
        'date': {
            '$gte': start_dt,
            '$lte': end_dt
        }
    }
    
    if state:
        query['state_name'] = state
    
    print(f"📊 Querying Pick 5 draws: {start_date} → {end_date}" + 
          (f" | State: {state}" if state else " | All States"))
    
    cursor = coll.find(query).sort('date', 1)
    draws = list(cursor)
    
    print(f"📦 Retrieved {len(draws)} draws")
    client.close()
    
    return draws


# ============================================================
# PROCESS & ENRICH DATA
# ============================================================

def process_draws(draws):
    """Add computed fields: TD, ΔSumsTD to each draw."""
    processed = []
    
    for d in draws:
        number_str = d.get('number_str', '')
        if not number_str or len(number_str) != 5:
            continue
        
        sums = d.get('digits_sum', calc_sums(number_str))
        td = calc_td(number_str)
        delta = sums - td
        
        # Handle date as datetime object or string
        raw_date = d.get('date', '')
        if isinstance(raw_date, datetime):
            date_str = raw_date.strftime('%Y-%m-%d')
        else:
            date_str = str(raw_date)[:10]
        
        processed.append({
            'date': date_str,
            'value': number_str,
            'normalized': d.get('normalized', ''),
            'state': d.get('state_name', ''),
            'state_code': d.get('state', ''),
            'game_name': d.get('game_name', ''),
            'tod': d.get('tod', ''),
            'sums': sums,
            'td': td,
            'delta_sums_td': delta,
            'abs_delta': abs(delta),
            'month': date_str[:7],
        })
    
    return processed


# ============================================================
# ANALYSIS ENGINE
# ============================================================

def analyze_nexus(data, target_delta=7, use_abs=True):
    """Full nexus analysis on filtered data."""
    
    # Filter to target delta
    if use_abs:
        filtered = [d for d in data if d['abs_delta'] == abs(target_delta)]
    else:
        filtered = [d for d in data if d['delta_sums_td'] == target_delta]
    
    if not filtered:
        return None
    
    analysis = {
        'target_delta': target_delta,
        'use_absolute': use_abs,
        'total_draws': len(data),
        'matching_draws': len(filtered),
        'hit_rate_pct': round(len(filtered) / len(data) * 100, 2),
        'filtered_data': filtered,
    }
    
    # --- Gap Analysis ---
    gaps = []
    for i in range(1, len(filtered)):
        gap = days_between(filtered[i-1]['date'], filtered[i]['date'])
        if gap > 0:
            gaps.append(gap)
    
    if gaps:
        analysis['gap'] = {
            'avg': round(statistics.mean(gaps), 1),
            'median': statistics.median(gaps),
            'mode': Counter(gaps).most_common(1)[0][0] if gaps else 0,
            'min': min(gaps),
            'max': max(gaps),
            'stdev': round(statistics.stdev(gaps), 1) if len(gaps) > 1 else 0,
            'recent_5': gaps[-5:],
            'all': gaps,
        }
    else:
        analysis['gap'] = {'avg': 0, 'median': 0, 'mode': 0, 'min': 0, 'max': 0, 'stdev': 0, 'recent_5': [], 'all': []}
    
    # --- Month Distribution ---
    month_counts = Counter(d['date'][5:7] for d in filtered)
    month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    analysis['months'] = {
        f"{i+1:02d}": {'name': month_names[i], 'count': month_counts.get(f"{i+1:02d}", 0)}
        for i in range(12)
    }
    analysis['hot_months'] = [
        {'month': month_names[int(m)-1], 'count': c}
        for m, c in month_counts.most_common(5)
    ]
    
    # --- Day of Week Distribution ---
    dow_names = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    dow_counts = Counter()
    for d in filtered:
        try:
            dt = datetime.strptime(d['date'][:10], '%Y-%m-%d')
            dow_counts[dt.weekday()] += 1
        except:
            pass
    analysis['day_of_week'] = [
        {'day': dow_names[i], 'count': dow_counts.get(i, 0)}
        for i in range(7)
    ]
    analysis['hot_days'] = sorted(
        [{'day': dow_names[i], 'count': c} for i, c in dow_counts.items()],
        key=lambda x: x['count'], reverse=True
    )[:3]
    
    # --- State Distribution ---
    state_counts = Counter(d['state'] for d in filtered)
    analysis['states'] = [
        {'state': s, 'count': c}
        for s, c in state_counts.most_common()
    ]
    analysis['hot_states'] = analysis['states'][:10]
    
    # --- TOD Distribution ---
    tod_counts = Counter(d['tod'] for d in filtered if d['tod'])
    analysis['tod'] = [
        {'tod': t, 'count': c}
        for t, c in tod_counts.most_common()
    ]
    
    # --- Sums & TD Value Distribution ---
    sums_counts = Counter(d['sums'] for d in filtered)
    td_counts = Counter(d['td'] for d in filtered)
    analysis['hot_sums'] = sums_counts.most_common(10)
    analysis['hot_td'] = td_counts.most_common(10)
    
    # --- Sums/TD Pair Analysis ---
    pair_counts = Counter((d['sums'], d['td']) for d in filtered)
    analysis['hot_pairs'] = [
        {'sums': s, 'td': t, 'count': c}
        for (s, t), c in pair_counts.most_common(10)
    ]
    
    # --- Normalized Value Frequency ---
    norm_counts = Counter(d['normalized'] for d in filtered)
    analysis['hot_normalized'] = [
        {'norm': n, 'count': c}
        for n, c in norm_counts.most_common(15)
    ]
    
    # --- Consecutive Date Clustering ---
    # Find draws within 3 days of each other
    clusters = []
    current_cluster = [filtered[0]]
    for i in range(1, len(filtered)):
        gap = days_between(filtered[i-1]['date'], filtered[i]['date'])
        if gap <= 3:
            current_cluster.append(filtered[i])
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [filtered[i]]
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)
    analysis['clusters'] = [
        {
            'dates': [d['date'] for d in c],
            'states': [d['state'] for d in c],
            'values': [d['value'] for d in c],
            'size': len(c)
        }
        for c in clusters
    ]
    
    # --- PREDICTION ---
    last = filtered[-1]
    gap_median = analysis['gap']['median'] or analysis['gap']['avg']
    
    try:
        last_dt = datetime.strptime(last['date'][:10], '%Y-%m-%d')
    except:
        last_dt = datetime.now()
    
    est_next = last_dt + timedelta(days=int(gap_median))
    window_start = last_dt + timedelta(days=max(1, analysis['gap']['min']))
    window_end = last_dt + timedelta(days=min(analysis['gap']['max'], int(gap_median * 2)))
    
    analysis['prediction'] = {
        'last_hit': last['date'],
        'last_value': last['value'],
        'last_state': last['state'],
        'gap_used': gap_median,
        'estimated_next': est_next.strftime('%Y-%m-%d'),
        'window_start': window_start.strftime('%Y-%m-%d'),
        'window_end': window_end.strftime('%Y-%m-%d'),
        'days_since_last': (datetime.now() - last_dt).days,
        'hot_months': analysis['hot_months'][:3],
        'hot_days': analysis['hot_days'][:3],
        'hot_states': analysis['hot_states'][:5],
        'hot_sums': analysis['hot_sums'][:5],
        'hot_td': analysis['hot_td'][:5],
        'hot_pairs': analysis['hot_pairs'][:5],
        'hot_normalized': analysis['hot_normalized'][:10],
    }
    
    return analysis


# ============================================================
# DISPLAY
# ============================================================

def print_header(title, char='═', width=70):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def print_section(title, char='─', width=50):
    print(f"\n  {char * 3} {title} {char * max(1, width - len(title) - 5)}")


def display_results(analysis):
    """Pretty-print the nexus analysis."""
    
    if not analysis:
        print("\n❌ No matching draws found for the specified delta.")
        return
    
    delta_label = f"|{analysis['target_delta']}|" if analysis['use_absolute'] else str(analysis['target_delta'])
    
    print_header(f"PICK 5 NEXUS STRATEGY — ΔSumsTD = {delta_label}")
    
    print(f"\n  📊 Total draws scanned:    {analysis['total_draws']:,}")
    print(f"  🎯 Matching Δ={delta_label}:        {analysis['matching_draws']:,}")
    print(f"  📈 Hit rate:               {analysis['hit_rate_pct']}%")
    
    # Gap Analysis
    gap = analysis['gap']
    print_section("GAP ANALYSIS (days between Δ hits)")
    print(f"  Average:   {gap['avg']} days")
    print(f"  Median:    {gap['median']} days")
    print(f"  Mode:      {gap['mode']} days")
    print(f"  Range:     {gap['min']} — {gap['max']} days")
    print(f"  Std Dev:   {gap['stdev']} days")
    print(f"  Recent 5:  {gap['recent_5']}")
    
    # Prediction
    pred = analysis['prediction']
    print_header(f"🔮 PREDICTION", char='▓')
    print(f"\n  Last Δ{delta_label} hit:     {pred['last_hit']}  ({pred['last_value']}  {pred['last_state']})")
    print(f"  Days since last:     {pred['days_since_last']} days")
    print(f"  Gap used (median):   {pred['gap_used']} days")
    print(f"  ┌─────────────────────────────────────────────┐")
    print(f"  │  Estimated next:   {pred['estimated_next']}                 │")
    print(f"  │  Window:           {pred['window_start']} → {pred['window_end']}  │")
    print(f"  └─────────────────────────────────────────────┘")
    
    # Hot Months
    print_section("HOT MONTHS")
    for m in pred['hot_months']:
        bar = '█' * m['count']
        print(f"  {m['month']:>5}  {bar} ({m['count']})")
    
    # Hot Days
    print_section("HOT DAYS OF WEEK")
    for d in pred['hot_days']:
        bar = '█' * d['count']
        print(f"  {d['day']:>5}  {bar} ({d['count']})")
    
    # Hot States
    print_section("HOT STATES (Top 10)")
    for i, s in enumerate(analysis['hot_states'][:10]):
        marker = '🔥' if i < 3 else '  '
        bar = '█' * min(s['count'], 50)
        print(f"  {marker} {s['state']:>20}  {bar} ({s['count']})")
    
    # TOD
    print_section("TIME OF DAY")
    for t in analysis['tod']:
        bar = '█' * min(t['count'], 50)
        print(f"  {t['tod']:>12}  {bar} ({t['count']})")
    
    # Hot Sums/TD Pairs
    print_section("HOT SUMS × TD PAIRS")
    print(f"  {'Sums':>6}  {'TD':>6}  {'Count':>6}  {'Δ':>6}")
    print(f"  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}")
    for p in pred['hot_pairs']:
        delta = p['sums'] - p['td']
        print(f"  {p['sums']:>6}  {p['td']:>6}  {p['count']:>6}  {delta:>6}")
    
    # Hot Normalized Values
    print_section("HOT NORMALIZED VALUES (sorted digits)")
    for n in pred['hot_normalized']:
        print(f"  {n['norm']}  ×{n['count']}")
    
    # Clusters
    if analysis['clusters']:
        print_section(f"CONSECUTIVE CLUSTERS (≤3 days apart): {len(analysis['clusters'])} found")
        for i, c in enumerate(analysis['clusters'][:10]):
            dates_str = ', '.join(c['dates'])
            states_str = ', '.join(set(c['states']))
            print(f"  Cluster {i+1} ({c['size']} draws): {dates_str}")
            print(f"           States: {states_str}")
            print(f"           Values: {', '.join(c['values'])}")
    
    # ABS recommendation
    print_header("💡 RECOMMENDATION: |ABS| MODE")
    print(f"""
  Using absolute value (making -7 equal to 7) is RECOMMENDED because:
  
  1. The MAGNITUDE of the Sums-TD gap creates the signal.
     Direction (+ or -) doesn't change the digit structure.
     
  2. A number with Sums=30, TD=37 (Δ=-7) has the same
     composition characteristics as Sums=37, TD=30 (Δ=+7).
     
  3. Combining +/- doubles your data pool → stronger patterns.
  
  Current mode: {'|ABS| ON ✅' if analysis['use_absolute'] else 'ABS OFF ⚠️  (consider enabling)'}
""")


# ============================================================
# EXPORT
# ============================================================

def export_csv(analysis, filename='pick5_nexus_export.csv'):
    """Export filtered results to CSV."""
    import csv
    
    data = analysis['filtered_data']
    if not data:
        print("No data to export.")
        return
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Date', 'Value', 'Normalized', 'State', 'TOD', 'Game',
            'Sums', 'TD', 'Delta_Sums_TD', 'Abs_Delta', 'Month'
        ])
        for d in data:
            writer.writerow([
                d['date'], d['value'], d['normalized'], d['state'], d['tod'],
                d.get('game_name', ''), d['sums'], d['td'],
                d['delta_sums_td'], d['abs_delta'], d['month']
            ])
    
    print(f"\n✅ Exported {len(data)} rows to {filename}")


# ============================================================
# DATA TABLE DISPLAY
# ============================================================

def display_table(data, limit=50):
    """Display filtered draws as a table."""
    print(f"\n{'─' * 100}")
    print(f"  {'Date':>12}  {'Value':>7}  {'Norm':>7}  {'State':>18}  {'TOD':>10}  "
          f"{'Sums':>5}  {'TD':>5}  {'Δ':>5}  {'|Δ|':>5}")
    print(f"  {'─'*12}  {'─'*7}  {'─'*7}  {'─'*18}  {'─'*10}  "
          f"{'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}")
    
    for d in data[:limit]:
        print(f"  {d['date']:>12}  {d['value']:>7}  {d['normalized']:>7}  {d['state']:>18}  {d['tod']:>10}  "
              f"{d['sums']:>5}  {d['td']:>5}  {d['delta_sums_td']:>5}  {d['abs_delta']:>5}")
    
    if len(data) > limit:
        print(f"\n  ... showing {limit} of {len(data)} rows (use --export for full data)")


# ============================================================
# QUICK CHECK
# ============================================================

def quick_check(number, target_delta=7):
    """Quickly check a number's Sums, TD, and Delta."""
    if len(number) != 5 or not number.isdigit():
        print("❌ Please enter a valid 5-digit number")
        return
    
    sums = calc_sums(number)
    td = calc_td(number)
    delta = sums - td
    abs_delta = abs(delta)
    match = abs_delta == abs(target_delta)
    
    print(f"\n  Number:  {number}")
    print(f"  Digits:  {' '.join(number)}")
    print(f"  Sums:    {sums}  (sum of digits)")
    print(f"  TD:      {td}  (sum of consecutive differences)")
    print(f"  Δ:       {delta}  (Sums - TD)")
    print(f"  |Δ|:     {abs_delta}")
    print(f"  Match:   {'✅ YES — matches Δ' + str(target_delta) if match else '❌ NO — does not match Δ' + str(target_delta)}")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Pick 5 Nexus Strategy Analyzer — Sums × TD × Date',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 pick5_nexus.py                             # Last 2 years, all states, Δ7
  python3 pick5_nexus.py --start 2020-01-01          # Custom start date
  python3 pick5_nexus.py --delta 5                   # Different target delta
  python3 pick5_nexus.py --state Ohio                # Single state
  python3 pick5_nexus.py --export                    # Export matches to CSV
  python3 pick5_nexus.py --check 35688               # Quick check a number
  python3 pick5_nexus.py --table                     # Show data table
  python3 pick5_nexus.py --no-abs                    # Use signed delta (not absolute)
        """
    )
    
    today = datetime.now().strftime('%Y-%m-%d')
    two_years_ago = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    
    parser.add_argument('--start', default=two_years_ago, help=f'Start date YYYY-MM-DD (default: {two_years_ago})')
    parser.add_argument('--end', default=today, help=f'End date YYYY-MM-DD (default: {today})')
    parser.add_argument('--delta', type=int, default=7, help='Target ΔSumsTD value (default: 7)')
    parser.add_argument('--no-abs', action='store_true', help='Use signed delta instead of absolute value')
    parser.add_argument('--state', default=None, help='Filter by state name (e.g. "Ohio")')
    parser.add_argument('--export', action='store_true', help='Export matching draws to CSV')
    parser.add_argument('--table', action='store_true', help='Display data table of matches')
    parser.add_argument('--table-limit', type=int, default=50, help='Max rows in table display (default: 50)')
    parser.add_argument('--check', default=None, help='Quick check a 5-digit number')
    parser.add_argument('--all-deltas', action='store_true', help='Show distribution of all delta values')
    
    args = parser.parse_args()
    
    # Quick check mode
    if args.check:
        quick_check(args.check, args.delta)
        return
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        PICK 5 NEXUS STRATEGY ANALYZER                      ║")
    print("║        Sums × TD × Date — Delta Pattern Engine             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    # Fetch data
    draws = fetch_pick5_draws(args.start, args.end, args.state)
    
    if not draws:
        print("\n❌ No draws found. Check your date range and connection.")
        return
    
    # Process
    data = process_draws(draws)
    print(f"✅ Processed {len(data)} valid Pick 5 draws")
    
    # Show all delta distribution if requested
    if args.all_deltas:
        print_section("ALL DELTA DISTRIBUTION")
        delta_counts = Counter(d['abs_delta'] for d in data)
        for delta, count in sorted(delta_counts.items()):
            pct = round(count / len(data) * 100, 1)
            bar = '█' * min(int(pct * 2), 50)
            print(f"  |Δ|={delta:>3}  {bar} {count:>6} ({pct}%)")
    
    # Analyze
    use_abs = not args.no_abs
    analysis = analyze_nexus(data, target_delta=args.delta, use_abs=use_abs)
    
    # Display
    display_results(analysis)
    
    if args.table and analysis:
        display_table(analysis['filtered_data'], limit=args.table_limit)
    
    if args.export and analysis:
        export_csv(analysis)


if __name__ == '__main__':
    main()
