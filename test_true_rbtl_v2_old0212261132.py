#!/usr/bin/env python3
"""
Test True RBTL v2 - Reverse Engineer 9869 on 2019-09-15 Evening
================================================================
Calls the new /api/rbtl/backtest-v2 endpoint which implements
the actual RBTL workflow with ±30 day rolling clusters.

Run while your app is serving on localhost:5001:
    python3 test_true_rbtl_v2.py
"""

import requests
import json

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

TARGET_NUMBER = "9869"
TARGET_NORMALIZED = "6899"


def sep(char="=", width=80):
    print(char * width)


def run_test(lookback_days=5, cluster_window=30, top_n_clusters=5):
    """Run a single true RBTL backtest."""
    url = f"{BASE_URL}/api/rbtl/backtest-v2?db={DB_MODE}"
    payload = {
        "state": "Florida",
        "game_type": "pick4",
        "target_date": "2019-09-15",
        "target_tod": "evening",
        "lookback_days": lookback_days,
        "cluster_window": cluster_window,
        "top_n_clusters": top_n_clusters,
        "include_same_day": True,
        "suggested_limit": 100
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code != 200:
            print(f"ERROR: HTTP {resp.status_code}")
            print(resp.text[:500])
            return None
        return resp.json()
    except requests.exceptions.ConnectionError:
        print("ERROR: Connection refused - is the app running on localhost:5001?")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def display_results(data):
    """Display the backtest results."""
    if not data:
        return
    
    sep()
    print(f"  TRUE RBTL v2 BACKTEST RESULTS")
    sep()
    
    print(f"\n  Target: {data['target_date']} {data['target_tod']}")
    print(f"  Lookback: {data['lookback_period']} ({data['lookback_days']} days)")
    print(f"  Data cutoff: {data.get('data_cutoff', '?')} (no data on/after this date used)")
    print(f"  Cluster window: ±{data['cluster_window']} days")
    
    # Seeds
    print(f"\n  SEEDS ({data['seed_count']}):")
    print(f"  Values: {', '.join(data['seed_values'])}")
    print(f"  Normalized: {', '.join(data['seed_actuals'])}")
    
    # Historical hits
    print(f"\n  Historical permutation hits: {data['historical_hit_count']}")
    print(f"  Clusters formed (merged): {data['total_clusters']}")
    
    # Top clusters
    print(f"\n  TOP {len(data['top_clusters'])} CLUSTERS (by seed hit count):")
    print(f"  {'#':<4} {'Hits':>5} {'Uniq':>5} {'Date Range':<40} {'Days':>5} {'Draws':>6} {'Uniq#':>6} {'Seeds'}")
    print(f"  {'-'*110}")
    for c in data['top_clusters']:
        seeds_str = ', '.join(c['seed_norms'][:4])
        if len(c['seed_norms']) > 4:
            seeds_str += f" +{len(c['seed_norms'])-4}"
        print(f"  {c['rank']:<4} {c['seed_count']:>5} {c['unique_seeds']:>5} {c['date_range']:<40} {c['days_span']:>5} {c['total_draws']:>6} {c['unique_actuals']:>6} {seeds_str}")
    
    # Candidates
    print(f"\n  Total unique candidates: {data['total_candidates']}")
    
    # Target results
    print(f"\n  TARGET WINNERS:")
    sep("-", 80)
    for w in data['winner_results']:
        status = "✅ FOUND" if w['found_in_candidates'] else "❌ MISS"
        rank_str = f"Rank #{w['rank']} of {w['total_candidates']}" if w['rank'] else "Not ranked"
        cluster_str = f"In clusters: {w['clusters']}" if w['clusters'] else ""
        apps_str = f"({w['total_appearances']} appearances)" if w['total_appearances'] else ""
        print(f"  {status}  {w['target_value']} (norm: {w['target_actual']}) {w['target_tod']}")
        print(f"         {rank_str} {apps_str} {cluster_str}")
    
    sep("-", 80)
    print(f"\n  HIT RATE: {data['hit_rate']}% ({data['winners_found']}/{data['target_winner_count']})")
    
    # Top suggested plays
    print(f"\n  TOP 30 SUGGESTED PLAYS:")
    print(f"  {'Rank':<6} {'Candidate':<12} {'#Clusters':>10} {'Appearances':>12} {'Clusters':<20} {'Winner?'}")
    print(f"  {'-'*80}")
    
    for play in data['suggested_plays'][:30]:
        winner_mark = "🎯 WINNER" if play['is_target_winner'] else ""
        print(f"  {play['rank']:<6} {play['candidate']:<12} {play['cluster_count']:>10} {play['total_appearances']:>12} {str(play['clusters']):<20} {winner_mark}")
    
    sep()


def main():
    sep()
    print(f"  REVERSE ENGINEERING: {TARGET_NUMBER} (norm: {TARGET_NORMALIZED})")
    print(f"  Using TRUE RBTL Process (v2 endpoint)")
    sep()
    
    # Test with default settings
    print("\n  Running with: 5d lookback, ±30 day clusters, top 5 clusters...")
    data = run_test(lookback_days=5, cluster_window=30, top_n_clusters=5)
    display_results(data)
    
    if data and data['hit_rate'] < 100:
        # Try with more clusters
        print("\n\n  Target not fully found — trying with top 10 clusters...")
        data2 = run_test(lookback_days=5, cluster_window=30, top_n_clusters=10)
        if data2:
            display_results(data2)
    
    # Also try 7d lookback
    print("\n\n  Also testing with 7d lookback...")
    data3 = run_test(lookback_days=7, cluster_window=30, top_n_clusters=5)
    if data3:
        found = any(w['found_in_candidates'] for w in data3['winner_results'] if w['target_actual'] == TARGET_NORMALIZED)
        rank = next((w['rank'] for w in data3['winner_results'] if w['target_actual'] == TARGET_NORMALIZED and w['rank']), None)
        print(f"  7d/±30/top5: {'✅' if found else '❌'} {f'Rank #{rank}' if rank else 'Not found'} | {data3['total_candidates']} candidates")


if __name__ == "__main__":
    main()
