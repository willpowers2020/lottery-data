"""
Test: Replicate MLD's "Repeated" column behavior.
MLD only shows numbers that appear 2+ times (any permutation) within a hot month.
"""
import requests, json
from collections import defaultdict

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

# Monthly mc≥2 dp=0 — the 3 qualifying months
body = {
    "state": "Florida", "game_type": "pick4",
    "target_date": "2019-10-09", "target_tod": "midday",
    "lookback_days": -1, "min_count": 2, "dp_size": 0,
    "dp_seed_mode": "last", "suggested_limit": 999,
    "include_same_day": True, "look_forward_days": 0,
    "grouping": "monthly",
}

r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
data = r.json()

plays = data.get("suggested_plays", [])
top_months = data.get("top_months", [])

print(f"Monthly mc≥2: {len(top_months)} hot months, {len(plays)} candidates")
for m in top_months:
    print(f"  {m['month']}: count={m['count']}")

# For each candidate, check how many times it appears in EACH month
# A candidate is a "duplicate" in month X if it appears 2+ times there
print(f"\n{'='*60}")
print(f"  MLD DUPLICATE FILTER SIMULATION")
print(f"{'='*60}")

# Build: candidate -> { month -> count_of_appearances_in_that_month }
cand_month_counts = defaultdict(lambda: defaultdict(int))

for p in plays:
    c = p["candidate"]
    for dd in p.get("draw_dates", []):
        m = dd.get("month", "")
        if m:
            cand_month_counts[c][m] += 1

# MLD "Repeated" = candidates that appear 2+ times in ANY qualifying month
# (different permutations count — same sorted digits on different dates)
duplicates_only = []
for p in plays:
    c = p["candidate"]
    is_dup = False
    dup_months = []
    for m, count in cand_month_counts[c].items():
        if count >= 2:
            is_dup = True
            dup_months.append(f"{m}({count}x)")
    if is_dup:
        duplicates_only.append({
            "candidate": c,
            "total_appearances": p.get("total_appearances", 0),
            "dup_months": dup_months,
            "month_count": p.get("month_count", 0),
        })

print(f"\nAll candidates (monthly mc≥2): {len(plays)}")
print(f"Duplicates only (2+ in any month): {len(duplicates_only)}")

# Sort by total appearances desc
duplicates_only.sort(key=lambda x: x["total_appearances"], reverse=True)

# Check winner
winner = "0589"
winner_found = any(d["candidate"] == winner for d in duplicates_only)
winner_rank = next((i+1 for i, d in enumerate(duplicates_only) if d["candidate"] == winner), None)

print(f"\nDuplicate candidates:")
for i, d in enumerate(duplicates_only):
    mark = " 🏆 WINNER" if d["candidate"] == winner else ""
    print(f"  #{i+1}: {d['candidate']}  hits={d['total_appearances']}  "
          f"groups={d['month_count']}  dups_in={d['dup_months']}{mark}")

print(f"\nWinner {winner}: found={winner_found}, rank={winner_rank}")

# Compare with MLD's 22 raw / 10 unique
mld_raw = "9072 7920 8950 8590 9171 7911 4164 4641 6144 6184 8614 8247 4872 2758 7825 7933 9373 7933 8396 8639 9793 9937".split()
mld_sorted = sorted(set("".join(sorted(n)) for n in mld_raw))
print(f"\nMLD's 10 unique sorted: {mld_sorted}")

our_set = set(d["candidate"] for d in duplicates_only)
mld_set = set(mld_sorted)

print(f"Our duplicates: {sorted(our_set)}")
print(f"Overlap: {sorted(our_set & mld_set)}")
print(f"In MLD only: {sorted(mld_set - our_set)}")
print(f"In ours only: {sorted(our_set - mld_set)}")

# Now try with cluster_year mc≥2
print(f"\n{'='*60}")
print(f"  CLUSTER_YEAR + DUPLICATE FILTER")
print(f"{'='*60}")

body2 = dict(body, grouping="cluster_year")
r2 = requests.post(api("/api/rbtl/backtest-v2"), json=body2, timeout=60)
d2 = r2.json()
plays2 = d2.get("suggested_plays", [])
top2 = d2.get("top_months", [])

print(f"\ncluster_year mc≥2: {len(top2)} hot years, {len(plays2)} candidates")

# Same duplicate logic but month = year key
cand_year_counts = defaultdict(lambda: defaultdict(int))
for p in plays2:
    c = p["candidate"]
    for dd in p.get("draw_dates", []):
        m = dd.get("month", "")
        if m:
            cand_year_counts[c][m] += 1

dups_cy = []
for p in plays2:
    c = p["candidate"]
    is_dup = False
    dup_groups = []
    for m, count in cand_year_counts[c].items():
        if count >= 2:
            is_dup = True
            dup_groups.append(f"{m}({count}x)")
    if is_dup:
        dups_cy.append({
            "candidate": c,
            "total_appearances": p.get("total_appearances", 0),
            "dup_groups": dup_groups,
            "month_count": p.get("month_count", 0),
        })

dups_cy.sort(key=lambda x: x["total_appearances"], reverse=True)

winner_in_cy = any(d["candidate"] == winner for d in dups_cy)
winner_rank_cy = next((i+1 for i, d in enumerate(dups_cy) if d["candidate"] == winner), None)

print(f"After duplicate filter: {len(dups_cy)} candidates")
print(f"Winner rank: #{winner_rank_cy}")
print(f"\nTop 30:")
for i, d in enumerate(dups_cy[:30]):
    mark = " 🏆" if d["candidate"] == winner else ""
    print(f"  #{i+1}: {d['candidate']}  hits={d['total_appearances']}  "
          f"groups={d['month_count']}  dups_in={d['dup_groups']}{mark}")

print("\nDone!")
