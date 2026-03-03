"""
Truth Table ∩ RBTL — Comprehensive Backtest
=============================================
Tests RBTL ∩ TT across a full month of draws.
TT seed = the PREVIOUS draw's value (what you'd actually know).

Usage: python3 test_tt_broad.py
"""
import requests, json, sys
from collections import defaultdict

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

# Config
STATE = "Florida"
GAME = "pick4"
START = "2024-07-01"
END = "2024-07-31"

print(f"\n{'='*90}")
print(f"  🔢 TRUTH TABLE ∩ RBTL — BROAD BACKTEST")
print(f"  {STATE} {GAME} | {START} to {END}")
print(f"{'='*90}")

# Fetch all draws in range + a few days before for seeds
r = requests.post(api("/api/draws/recent"), json={
    "state": STATE, "game_type": GAME,
    "start_date": "2024-06-28", "end_date": END,
}, timeout=30)
all_draws = r.json().get("draws", [])
all_draws.sort(key=lambda d: (d["date"], d.get("tod", "")))

# Build chronological list
draws_in_range = [d for d in all_draws if d["date"] >= START and d["date"] <= END]
print(f"  Draws in range: {len(draws_in_range)}")
print(f"  Total draws (incl pre-range seeds): {len(all_draws)}")

# For each target draw, the TT seed = the immediately preceding draw's value
draw_index = {f"{d['date']}_{d.get('tod','')}": d for d in all_draws}
sorted_draws = sorted(all_draws, key=lambda d: (d["date"], 0 if (d.get("tod") or "").lower() == "midday" else 1))

# Strategies to test
STRATEGIES = [
    {"label": "RBTL only (Shadow mc≥2)", "grouping": "monthly", "mc": 2, "dp": 0, "tt": False},
    {"label": "TT only (mc≥1)", "grouping": "monthly", "mc": 1, "dp": 0, "tt": True},
    {"label": "RBTL ∩ TT (monthly mc≥2)", "grouping": "monthly", "mc": 2, "dp": 0, "tt": True},
    {"label": "RBTL ∩ TT (cluster_year mc≥2)", "grouping": "cluster_year", "mc": 2, "dp": 0, "tt": True},
    {"label": "Sniper ∩ TT (mc≥1 2DP)", "grouping": "monthly", "mc": 1, "dp": 2, "tt": True},
]

# Results storage
results = {s["label"]: [] for s in STRATEGIES}

# Header
print(f"\n  {'Date':<12}{'TOD':<9}{'Winner':<8}{'TT Seed':<8}", end="")
for s in STRATEGIES:
    short = s["label"].split("(")[0].strip()[:14]
    print(f"  {short:<16}", end="")
print()
print(f"  {'-'*12}{'-'*9}{'-'*8}{'-'*8}", end="")
for _ in STRATEGIES:
    print(f"  {'-'*16}", end="")
print()

for i, target in enumerate(draws_in_range):
    tdate = target["date"]
    ttod = (target.get("tod") or "").lower()
    tactual = target.get("actual", "?")
    tvalue = target.get("value", "?")

    # Find previous draw for TT seed
    target_idx = None
    for j, sd in enumerate(sorted_draws):
        if sd["date"] == tdate and (sd.get("tod") or "").lower() == ttod:
            target_idx = j
            break

    if target_idx is None or target_idx == 0:
        continue

    prev_draw = sorted_draws[target_idx - 1]
    tt_seed = prev_draw.get("value", "")

    # Print row start
    sys.stdout.write(f"  {tdate:<12}{ttod:<9}{tvalue:<8}{tt_seed:<8}")

    for s in STRATEGIES:
        body = {
            "state": STATE, "game_type": GAME,
            "target_date": tdate, "target_tod": ttod,
            "lookback_days": -1, "min_count": s["mc"], "dp_size": s["dp"],
            "dp_seed_mode": "last", "suggested_limit": 999,
            "include_same_day": True, "look_forward_days": 0,
            "grouping": s["grouping"],
            "truth_table_seed": tt_seed if s["tt"] else "",
        }
        try:
            r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
            d = r.json()
            if d.get("error"):
                sys.stdout.write(f"  {'ERR':<16}")
                results[s["label"]].append({"found": False, "error": True})
                continue

            plays = d.get("suggested_plays", [])
            found = False
            rank = 0
            for wr in d.get("winner_results", []):
                if wr.get("found_in_candidates"):
                    found = True
                    rank = wr.get("rank", 0)

            n = len(plays)
            if found:
                cell = f"✅#{rank}/{n}"
                results[s["label"]].append({"found": True, "rank": rank, "total": n})
            elif n == 0:
                cell = "—"
                results[s["label"]].append({"found": False, "total": 0})
            else:
                cell = f"❌ /{n}"
                results[s["label"]].append({"found": False, "total": n})

            sys.stdout.write(f"  {cell:<16}")

        except Exception as e:
            sys.stdout.write(f"  {'EXC':<16}")
            results[s["label"]].append({"found": False, "error": True})

    print()

# ===== SUMMARY =====
print(f"\n{'='*90}")
print(f"  📊 SUMMARY — {len(draws_in_range)} draws tested")
print(f"{'='*90}")

print(f"\n  {'Strategy':<38}{'Wins':<8}{'Hit%':<8}{'Avg List':<10}{'Avg Rank':<10}{'Est ROI'}")
print(f"  {'-'*38}{'-'*8}{'-'*8}{'-'*10}{'-'*10}{'-'*10}")

for s in STRATEGIES:
    res = results[s["label"]]
    wins = [r for r in res if r.get("found")]
    active = [r for r in res if r.get("total", 0) > 0 or r.get("found")]
    total = len(res)

    n_wins = len(wins)
    hit_pct = n_wins / total * 100 if total else 0

    avg_list = 0
    avg_rank = 0
    if active:
        avg_list = sum(r.get("total", 0) for r in active) / len(active)
    if wins:
        avg_rank = sum(r["rank"] for r in wins) / len(wins)

    # ROI estimate: play avg_list per draw, win $5000 per hit
    total_cost = sum(r.get("total", 0) for r in active)
    revenue = n_wins * 5000
    roi = (revenue / total_cost * 100) if total_cost > 0 else 0
    profit = revenue - total_cost

    print(f"  {s['label']:<38}{n_wins:<8}{hit_pct:<8.1f}{avg_list:<10.0f}{avg_rank:<10.1f}{roi:<.0f}%")

# Detailed profit
print(f"\n  {'Strategy':<38}{'Total Cost':<12}{'Revenue':<12}{'Profit':<12}{'ROI'}")
print(f"  {'-'*38}{'-'*12}{'-'*12}{'-'*12}{'-'*10}")

for s in STRATEGIES:
    res = results[s["label"]]
    wins = [r for r in res if r.get("found")]
    active = [r for r in res if r.get("total", 0) > 0 or r.get("found")]

    total_cost = sum(r.get("total", 0) for r in active)
    revenue = len(wins) * 5000
    profit = revenue - total_cost
    roi = (revenue / total_cost * 100) if total_cost > 0 else 0

    pfx = "💎" if profit > 0 and roi > 500 else ("✅" if profit > 0 else "❌")
    print(f"  {pfx} {s['label']:<36}${total_cost:<11,}${revenue:<11,}${profit:<11,}{roi:.0f}%")

# Top winners by strategy
print(f"\n  🏆 TOP WINS (smallest list with winner):")
all_wins = []
for s in STRATEGIES:
    for i, r in enumerate(results[s["label"]]):
        if r.get("found"):
            all_wins.append({
                "strategy": s["label"],
                "draw": i,
                "rank": r["rank"],
                "total": r["total"],
                "roi_per_play": 5000 / r["total"] if r["total"] > 0 else 0,
            })

all_wins.sort(key=lambda w: w["total"])
for w in all_wins[:20]:
    d = draws_in_range[w["draw"]] if w["draw"] < len(draws_in_range) else {}
    date = d.get("date", "?")
    tod = (d.get("tod") or "")[:3]
    val = d.get("value", "?")
    print(f"    {date} {tod:<4} {val}  #{w['rank']}/{w['total']}  "
          f"${w['total']} → {w['roi_per_play']:.0f}x  [{w['strategy'][:30]}]")

print(f"\n  Done! 🎉")
