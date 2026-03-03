"""
Win #2 Cluster Survival Check
================================
Shadow profile: 2 seeds (mid+eve same day), dp=0, min_count=2
Target: Florida pick4 2019-10-09 midday
"""

import requests, json, sys
from datetime import datetime, timedelta

BASE = "http://localhost:5001"
DB = "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{BASE}{path}{sep}db={DB}"

def run_bt(grouping, mc, dp_size=0):
    body = {
        "state": "Florida",
        "game_type": "pick4",
        "target_date": "2019-10-09",
        "target_tod": "midday",
        "lookback_days": -1,  # Shadow mode
        "min_count": mc,
        "dp_size": dp_size,
        "dp_seed_mode": "last",
        "suggested_limit": 999,
        "include_same_day": True,
        "look_forward_days": 0,
        "grouping": grouping,
    }
    r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
    return r.json()

def find_winner(data):
    plays = data.get("suggested_plays", [])
    winners = data.get("target_winners", [])
    winner_results = data.get("winner_results", [])
    
    # From winner_results (more detail)
    for wr in winner_results:
        if wr.get("found_in_candidates"):
            return {
                "found": True,
                "rank": wr.get("rank", 0),
                "total": wr.get("total_candidates", len(plays)),
                "hits": wr.get("total_appearances", 0),
                "months": wr.get("months", []),
                "value": wr.get("target_actual", ""),
                "filter_reason": None,
            }
        else:
            return {
                "found": False,
                "total": len(plays),
                "filter_reason": wr.get("filter_reason", ""),
                "months": wr.get("months", []),
                "hits": wr.get("total_appearances", 0),
                "value": wr.get("target_actual", ""),
            }
    
    # Fallback: check suggested_plays
    for w in winners:
        wval = w.get("value", "")
        wnorm = "".join(sorted(wval.replace("-", "")))
        for idx, p in enumerate(plays):
            if p["candidate"] == wnorm:
                return {
                    "found": True, "rank": idx + 1, "total": len(plays),
                    "hits": p.get("total_appearances", 0),
                    "months": p.get("months", []),
                    "value": w.get("actual", wval),
                    "filter_reason": None,
                }
    return {"found": False, "total": len(plays), "filter_reason": "Not in plays", "value": "", "months": [], "hits": 0}

# ---- Load seeds ----
print("=" * 70)
print("  🔍 WIN #2 CLUSTER SURVIVAL CHECK")
print("  Florida pick4 | 2019-10-09 midday | Shadow (dp=0)")
print("=" * 70)

print("\n⏳ Loading seeds...")
r = requests.post(api("/api/draws/recent"), json={
    "state": "Florida", "game_type": "pick4",
    "start_date": "2019-10-04", "end_date": "2019-10-09"
}, timeout=15)
draws = r.json().get("draws", [])

# Show seeds (suppress midday target)
print(f"\n📋 Available draws:")
for d in draws:
    marker = " 🏆 TARGET" if d["date"] == "2019-10-09" and (d.get("tod") or "").lower() == "midday" else ""
    print(f"  {d['date']} {d.get('tod',''):<8} → {d.get('actual','?')}{marker}")

# ---- Run backtests ----
GROUPINGS = ["monthly", "cluster_15", "cluster_30", "cluster_60"]
MIN_COUNTS = [1, 2, 3, 4, 5]
DP_SIZES = [0, 2]  # Test both no-DP and with-DP

results = {}
print(f"\n{'=' * 70}")
print(f"⏳ Running backtests...")
print("=" * 70)

for dp in DP_SIZES:
    dp_label = f"dp={dp}"
    print(f"\n  --- DP SIZE: {dp} {'(no filter)' if dp == 0 else '(2DP filter)'} ---")
    
    for grouping in GROUPINGS:
        for mc in MIN_COUNTS:
            try:
                data = run_bt(grouping, mc, dp)
                w = find_winner(data)
                clusters = data.get("top_months", [])
                seeds = data.get("seed_values", [])
                
                key = (grouping, mc, dp)
                results[key] = w
                results[key]["clusters"] = clusters
                results[key]["seeds"] = seeds
                
                if w["found"]:
                    print(f"  {grouping:<12} mc≥{mc} {dp_label}: ✅ rank #{w['rank']}/{w['total']}, "
                          f"hits={w['hits']}, clusters={len(w['months'])}")
                else:
                    reason = w.get('filter_reason', '')
                    print(f"  {grouping:<12} mc≥{mc} {dp_label}: ❌ ({w['total']} cands) {reason}")
            except Exception as e:
                print(f"  {grouping:<12} mc≥{mc} {dp_label}: ERROR {e}")

# ---- Summary Tables ----
print(f"\n{'=' * 70}")
print(f"  SUMMARY TABLE — dp=0 (no DP filter, like Shadow/Win#2)")
print("=" * 70)

header = f"  {'Grouping':<14}" + "".join([f"{'mc≥'+str(mc):<14}" for mc in MIN_COUNTS])
print(header)
print("  " + "-" * (14 + 14 * len(MIN_COUNTS)))

for grouping in GROUPINGS:
    row = f"  {grouping:<14}"
    for mc in MIN_COUNTS:
        r = results.get((grouping, mc, 0))
        if r and r["found"]:
            row += f"{'✅ #'+str(r['rank'])+' ('+str(r['hits'])+'h)':<14}"
        else:
            row += f"{'❌':<14}"
    print(row)

print(f"\n{'=' * 70}")
print(f"  SUMMARY TABLE — dp=2 (with 2DP filter, like Sniper/Win#1)")
print("=" * 70)

print(header)
print("  " + "-" * (14 + 14 * len(MIN_COUNTS)))

for grouping in GROUPINGS:
    row = f"  {grouping:<14}"
    for mc in MIN_COUNTS:
        r = results.get((grouping, mc, 2))
        if r and r["found"]:
            row += f"{'✅ #'+str(r['rank'])+' ('+str(r['hits'])+'h)':<14}"
        else:
            row += f"{'❌':<14}"
    print(row)

# ---- Key Insight ----
print(f"\n{'=' * 70}")
print(f"  💡 KEY INSIGHT — Does dp=0 find the winner when dp=2 doesn't?")
print("=" * 70)

for grouping in GROUPINGS:
    for mc in MIN_COUNTS:
        r_dp0 = results.get((grouping, mc, 0))
        r_dp2 = results.get((grouping, mc, 2))
        if r_dp0 and r_dp0["found"] and r_dp2 and not r_dp2["found"]:
            print(f"  🎯 {grouping} mc≥{mc}: dp=0 SAVES winner (#{r_dp0['rank']}/{r_dp0['total']})")
            print(f"     dp=2 lost it: {r_dp2.get('filter_reason','')}")
        elif r_dp0 and r_dp0["found"] and r_dp2 and r_dp2["found"]:
            if r_dp0["rank"] < r_dp2["rank"]:
                print(f"  📈 {grouping} mc≥{mc}: dp=0 ranks higher (#{r_dp0['rank']}) vs dp=2 (#{r_dp2['rank']})")

# ---- Best playable list ----
print(f"\n{'=' * 70}")
print(f"  🏆 BEST PLAYABLE LISTS (≤100 candidates with winner)")
print("=" * 70)

playable = []
for key, r in results.items():
    if r["found"] and r["total"] <= 100:
        playable.append((key, r))

playable.sort(key=lambda x: x[1]["total"])

if playable:
    for (grp, mc, dp), r in playable[:10]:
        print(f"  {grp:<12} mc≥{mc} dp={dp}: #{r['rank']}/{r['total']} "
              f"(hits={r['hits']}, cost=${r['total']})")
else:
    print("  No lists ≤100 with winner found. Closest:")
    found_any = [(k, r) for k, r in results.items() if r["found"]]
    found_any.sort(key=lambda x: x[1]["total"])
    for (grp, mc, dp), r in found_any[:5]:
        print(f"  {grp:<12} mc≥{mc} dp={dp}: #{r['rank']}/{r['total']}")

# ---- Cluster detail for best result ----
print(f"\n{'=' * 70}")
print(f"  🔍 WINNER CLUSTER DETAIL (cluster_30 mc≥1 dp=0)")
print("=" * 70)

best = results.get(("cluster_30", 1, 0))
if best and best["found"]:
    print(f"\n  Winner: {best['value']}")
    print(f"  Rank: #{best['rank']}/{best['total']}")
    print(f"  Total hits: {best['hits']}")
    print(f"  Seeds: {', '.join(best.get('seeds', []))}")
    print(f"  Appeared in {len(best['months'])} cluster(s):")
    for m in best["months"]:
        print(f"    └─ {m}")

print(f"\n  Done! 🎉")
