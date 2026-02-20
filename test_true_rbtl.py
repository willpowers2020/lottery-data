#!/usr/bin/env python3
"""
RBTL True Process - Test for 9/15/2019 Evening
================================================
Replicates the actual RBTL workflow:

Step 1: Take seeds (lookback + same-day midday)
Step 2: For each seed, find ALL historical permutation matches
Step 3: For each historical hit, create a ±30 day window cluster
Step 4: Merge overlapping clusters, rank by COUNT of seed matches
Step 5: From top clusters, pull ALL numbers drawn in those windows
Step 6: Those are the candidate plays ("Repeated" numbers)

Target: 9869 (Evening draw on 2019-09-15)
Seeds: 5489, 0094, 0201, 9552, 1704, 1876, 8975

Run while your app is serving on localhost:5001:
    python3 test_true_rbtl.py
"""

import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import permutations

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

# === CONFIG ===
STATE = "Florida"
GAME_TYPE = "pick4"
TARGET_DATE = "2019-09-15"
TARGET_TOD = "Evening"
TARGET_NUMBER = "9869"
TARGET_NORMALIZED = "6899"

# Seeds: lookback draws + midday on target date
SEEDS = ["5489", "0094", "0201", "9552", "1704", "1876", "8975"]

CLUSTER_WINDOW = 30  # ±30 days from each historical hit
TOP_CLUSTERS = 10     # How many top clusters to show


def normalize(num_str):
    """Sort digits to get normalized form."""
    return ''.join(sorted(num_str))


def get_all_permutations(normalized):
    """Get all unique permutations of a normalized number."""
    return set(''.join(p) for p in permutations(normalized))


def fetch_all_draws():
    """Fetch all FL Pick4 historical draws via the analyze endpoint."""
    print("  Fetching all FL Pick4 historical data...")
    
    # Use the analyze endpoint with a wide date range to get all draws
    # We'll use the /api/rbtl/analyze endpoint which returns historical matches
    url = f"{BASE_URL}/api/rbtl/analyze?db={DB_MODE}"
    
    # We need raw draw data. Let's use a different approach - 
    # fetch draws by querying the backtest endpoint which gives us access to all_draws
    # Actually, let's just query the data-stats first to understand what we have
    stats_url = f"{BASE_URL}/api/rbtl/data-stats/{STATE}/{GAME_TYPE}?db={DB_MODE}"
    
    try:
        resp = requests.get(stats_url, timeout=30)
        stats = resp.json()
        print(f"  Database has {stats.get('total_draws', '?')} total draws")
        print(f"  Date range: {stats.get('first_draw', '?')} to {stats.get('last_draw', '?')}")
    except Exception as e:
        print(f"  Could not fetch stats: {e}")
    
    # Use analyze endpoint to get historical occurrences of our seeds
    # We need to send seeds as a date range that captures them
    # Seeds are from ~09/12/2019 to 09/15/2019 midday
    payload = {
        "game_type": GAME_TYPE,
        "states": [STATE],
        "start_date": "2019-09-10",
        "end_date": "2019-09-15",
        "tod": "All"
    }
    
    print("  Fetching seed analysis via /api/rbtl/analyze...")
    resp = requests.post(url, json=payload, timeout=120)
    
    if resp.status_code != 200:
        print(f"  ERROR: {resp.status_code} - {resp.text[:200]}")
        return None
    
    data = resp.json()
    print(f"  Got {data.get('total_historical_matches', 0)} historical matches for {len(data.get('past_winners', []))} unique normalized seeds")
    
    return data


def build_clusters_from_analyze(data):
    """
    From the analyze results, build ±30 day clusters around each historical hit.
    """
    draws = data.get('draws', [])
    
    if not draws:
        print("  No historical draws found!")
        return []
    
    # Normalize our seeds
    seed_norms = set(normalize(s) for s in SEEDS)
    print(f"\n  Seed normalized forms: {sorted(seed_norms)}")
    
    # Group historical hits by their normalized form (only for our seeds)
    # Each draw in the results has: date, value, norm, state, tod, input_date, perm, etc.
    historical_hits = []
    for d in draws:
        if d.get('norm') in seed_norms:
            try:
                hit_date = datetime.strptime(d['date'], '%Y-%m-%d')
                # Only use hits BEFORE our seed period (before 2019-09-10)
                if hit_date < datetime(2019, 9, 10):
                    historical_hits.append({
                        'date': hit_date,
                        'value': d['value'],
                        'norm': d['norm'],
                        'state': d.get('state', ''),
                        'tod': d.get('tod', ''),
                        'seed_norm': d.get('norm')
                    })
            except (ValueError, KeyError):
                continue
    
    print(f"  Found {len(historical_hits)} historical hits for our seeds (before seed period)")
    
    if not historical_hits:
        return []
    
    # Sort by date
    historical_hits.sort(key=lambda x: x['date'])
    
    # Build ±30 day clusters around each historical hit
    # Then merge overlapping clusters
    raw_windows = []
    for hit in historical_hits:
        window_start = hit['date'] - timedelta(days=CLUSTER_WINDOW)
        window_end = hit['date'] + timedelta(days=CLUSTER_WINDOW)
        raw_windows.append({
            'start': window_start,
            'end': window_end,
            'center_hit': hit,
            'seed_hits': [hit]
        })
    
    # Merge overlapping windows
    raw_windows.sort(key=lambda w: w['start'])
    merged = []
    
    for window in raw_windows:
        if merged and window['start'] <= merged[-1]['end']:
            # Overlapping - merge
            merged[-1]['end'] = max(merged[-1]['end'], window['end'])
            merged[-1]['seed_hits'].append(window['center_hit'])
        else:
            merged.append({
                'start': window['start'],
                'end': window['end'],
                'seed_hits': [window['center_hit']]
            })
    
    # Count seed matches per cluster
    for cluster in merged:
        cluster['seed_count'] = len(cluster['seed_hits'])
        cluster['unique_seeds'] = len(set(h['norm'] for h in cluster['seed_hits']))
        cluster['seed_norms'] = list(set(h['norm'] for h in cluster['seed_hits']))
        cluster['date_range'] = f"{cluster['start'].strftime('%Y-%m-%d')} to {cluster['end'].strftime('%Y-%m-%d')}"
        cluster['days_span'] = (cluster['end'] - cluster['start']).days
    
    # Rank by count of seed matches (as per the real RBTL process)
    merged.sort(key=lambda c: c['seed_count'], reverse=True)
    
    return merged


def fetch_draws_in_window(start_date, end_date):
    """
    Fetch all draws in a date window using the analyze endpoint.
    We'll query with a dummy seed range that covers the window.
    """
    url = f"{BASE_URL}/api/rbtl/analyze?db={DB_MODE}"
    payload = {
        "game_type": GAME_TYPE,
        "states": [STATE],
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "tod": "All"
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            # The past_winners field has the normalized numbers drawn in this range
            # But we need ALL draws, not just unique norms
            # The draws field has historical matches, but we need the actual draws FROM this window
            # Let's use the seed_draws concept - the draws IN the date range
            return data
        return None
    except:
        return None


def get_candidates_from_clusters(clusters, top_n=5):
    """
    For the top N clusters, fetch ALL numbers drawn in those windows.
    These are the candidate plays.
    """
    print(f"\n  Fetching candidates from top {top_n} clusters...")
    
    all_candidates = defaultdict(lambda: {'count': 0, 'clusters': [], 'dates': []})
    
    for i, cluster in enumerate(clusters[:top_n]):
        print(f"\n  Cluster #{i+1}: {cluster['date_range']} ({cluster['seed_count']} seed hits, {cluster['days_span']} days)")
        print(f"    Seeds found: {cluster['seed_norms']}")
        
        # Fetch all draws in this window
        data = fetch_draws_in_window(cluster['start'], cluster['end'])
        
        if data and data.get('past_winners'):
            winners_in_window = data['past_winners']
            seed_count_in_window = data.get('total_seed_draws', 0)
            print(f"    Draws in window: {seed_count_in_window} | Unique normalized: {len(winners_in_window)}")
            
            for norm in winners_in_window:
                all_candidates[norm]['count'] += 1
                all_candidates[norm]['clusters'].append(i + 1)
        else:
            print(f"    No data returned for this window")
    
    return dict(all_candidates)


def print_separator(char="=", width=80):
    print(char * width)


def main():
    print_separator()
    print(f"  TRUE RBTL PROCESS - Reverse Engineering {TARGET_NUMBER}")
    print(f"  Target: {TARGET_DATE} {TARGET_TOD}")
    print(f"  Seeds: {', '.join(SEEDS)}")
    print(f"  Cluster window: ±{CLUSTER_WINDOW} days")
    print_separator()
    
    # Step 1: Get historical occurrences of seed permutations
    print(f"\n{'─'*60}")
    print("  STEP 1: Find historical permutation matches for seeds")
    print(f"{'─'*60}")
    
    data = fetch_all_draws()
    if not data:
        print("  FAILED - Could not fetch data. Is the app running?")
        return
    
    # Step 2: Build and rank clusters
    print(f"\n{'─'*60}")
    print("  STEP 2: Build ±30 day clusters around historical hits")
    print(f"{'─'*60}")
    
    clusters = build_clusters_from_analyze(data)
    
    if not clusters:
        print("  No clusters found!")
        return
    
    print(f"\n  Total clusters (merged): {len(clusters)}")
    print(f"\n  Top clusters by seed match count:")
    print(f"  {'#':<4} {'Seed Hits':>10} {'Unique':>7} {'Date Range':<35} {'Days':>5} {'Seeds Found'}")
    print(f"  {'-'*100}")
    
    for i, c in enumerate(clusters[:15]):
        print(f"  {i+1:<4} {c['seed_count']:>10} {c['unique_seeds']:>7} {c['date_range']:<35} {c['days_span']:>5} {', '.join(c['seed_norms'][:5])}")
    
    # Step 3: Get candidates from top clusters
    print(f"\n{'─'*60}")
    print("  STEP 3: Pull ALL numbers from top hot clusters (candidates)")
    print(f"{'─'*60}")
    
    candidates = get_candidates_from_clusters(clusters, top_n=5)
    
    if not candidates:
        print("  No candidates found!")
        return
    
    # Sort candidates by how many clusters they appear in
    ranked = sorted(candidates.items(), key=lambda x: x[1]['count'], reverse=True)
    
    print(f"\n  Total unique candidates: {len(ranked)}")
    
    # Check if target is in candidates
    target_found = TARGET_NORMALIZED in candidates
    target_info = candidates.get(TARGET_NORMALIZED)
    
    print(f"\n{'─'*60}")
    print("  RESULTS: Did we find {TARGET_NUMBER} (norm: {TARGET_NORMALIZED})?")
    print(f"{'─'*60}")
    
    if target_found:
        # Find rank
        target_rank = None
        for i, (norm, info) in enumerate(ranked):
            if norm == TARGET_NORMALIZED:
                target_rank = i + 1
                break
        
        print(f"\n  ✅ YES! {TARGET_NORMALIZED} found!")
        print(f"     Rank: #{target_rank} of {len(ranked)} candidates")
        print(f"     Appeared in {target_info['count']} of the top clusters: {target_info['clusters']}")
    else:
        print(f"\n  ❌ {TARGET_NORMALIZED} was NOT found in candidates from top 5 clusters")
        print(f"     Checking if it appears in any cluster...")
        
        # Check all clusters
        all_candidates = get_candidates_from_clusters(clusters, top_n=len(clusters))
        if TARGET_NORMALIZED in all_candidates:
            info = all_candidates[TARGET_NORMALIZED]
            print(f"     Found in cluster(s): {info['clusters']}")
        else:
            print(f"     Not found in any cluster")
    
    # Show top candidates
    print(f"\n  Top 30 candidates (by cluster frequency):")
    print(f"  {'Rank':<6} {'Normalized':<12} {'In # Clusters':<15} {'Clusters'}")
    print(f"  {'-'*60}")
    
    seed_norms = set(normalize(s) for s in SEEDS)
    
    for i, (norm, info) in enumerate(ranked[:30]):
        is_seed = "🌱" if norm in seed_norms else "  "
        is_target = "🎯" if norm == TARGET_NORMALIZED else "  "
        marker = is_target if norm == TARGET_NORMALIZED else is_seed
        print(f"  {i+1:<6} {norm:<12} {info['count']:<15} {info['clusters']} {marker}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Seeds: {len(SEEDS)}")
    print(f"  Historical hits: {len(data.get('draws', []))}")
    print(f"  Clusters found: {len(clusters)}")
    print(f"  Top cluster: {clusters[0]['seed_count']} seed hits in {clusters[0]['date_range']}")
    print(f"  Total candidates: {len(ranked)}")
    print(f"  Target {TARGET_NORMALIZED} found: {'✅ YES' if target_found else '❌ NO'}")
    if target_found:
        print(f"  Target rank: #{target_rank} of {len(ranked)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
