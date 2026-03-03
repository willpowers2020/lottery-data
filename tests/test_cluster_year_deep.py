"""
Deep debug: Why does MLD show 22 candidates for 2013-03 + 2013-10?
"""

import requests, json, sys

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

# Get the raw backtest data for cluster_year mc≥2 dp=0
body = {
    "state": "Florida", "game_type": "pick4",
    "target_date": "2019-10-09", "target_tod": "midday",
    "lookback_days": -1, "min_count": 2, "dp_size": 0,
    "dp_seed_mode": "last", "suggested_limit": 999,
    "include_same_day": True, "look_forward_days": 0,
    "grouping": "cluster_year",
}

r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
data = r.json()

print(f"\nSeeds: {data.get('seed_values', [])}")
print(f"Seed actuals: {data.get('seed_actuals', [])}")

top_months = data.get("top_months", [])
print(f"\nHot years ({len(top_months)}):")
for m in top_months:
    month = m.get("month", "?")
    count = m.get("count", 0)
    inputs = m.get("input_values", [])
    draws_in = m.get("total_draws_in_month", "?")
    unique_in = m.get("unique_actuals_in_month", "?")
    print(f"  {month}: count={count}, inputs={inputs}")
    print(f"    total_draws={draws_in}, unique_actuals={unique_in}")

plays = data.get("suggested_plays", [])
print(f"\nTotal candidates: {len(plays)}")

# Now let's specifically look at 2013
print("\n" + "=" * 60)
print("  FOCUS: What candidates come from 2013?")
print("=" * 60)

from_2013 = []
for p in plays:
    months = p.get("months", [])
    if "2013" in months:
        from_2013.append(p)

print(f"\nCandidates that include 2013 in their groups: {len(from_2013)}")

# Which candidates are ONLY from 2013?
only_2013 = [p for p in from_2013 if p.get("months") == ["2013"]]
print(f"Candidates ONLY from 2013: {len(only_2013)}")

# MLD numbers from screenshot
mld_numbers = "9072 7920 8950 8590 9171 7911 4164 4641 6144 6184 8614 8247 4872 2758 7825 7933 9373 7933 8396 8639 9793 9937".split()
# Normalize (sort digits)
mld_sorted = sorted(set("".join(sorted(n)) for n in mld_numbers))
print(f"\nMLD's 22 numbers (sorted/deduped): {len(mld_sorted)}")
print(f"  {mld_sorted}")

# Check how many of MLD's numbers are in our candidate list
our_candidates = set(p["candidate"] for p in plays)
mld_in_ours = [n for n in mld_sorted if n in our_candidates]
mld_not_in_ours = [n for n in mld_sorted if n not in our_candidates]
print(f"\nMLD numbers found in our candidates: {len(mld_in_ours)}")
print(f"MLD numbers NOT in our candidates: {len(mld_not_in_ours)}")
if mld_not_in_ours:
    print(f"  Missing: {mld_not_in_ours}")

# Check: how many of our candidates come from 2013-03 or 2013-10 ONLY
# We need to look at draw_dates to figure out which specific months
print("\n" + "=" * 60)
print("  DRAW DATE ANALYSIS for 2013 candidates")
print("=" * 60)

cands_with_2013_months = []
for p in from_2013:
    draw_dates = p.get("draw_dates", [])
    months_seen = set()
    for dd in draw_dates:
        m = dd.get("month", "")
        if m.startswith("2013"):
            months_seen.add(m)
    if months_seen:
        cands_with_2013_months.append({
            "candidate": p["candidate"],
            "months_2013": sorted(months_seen),
            "total_months": p.get("months", []),
            "total_appearances": p.get("total_appearances", 0),
        })

print(f"\nCandidates with draws in 2013 months: {len(cands_with_2013_months)}")

# Now filter to ONLY 2013-03 and 2013-10
in_both = [c for c in cands_with_2013_months 
           if "2013-03" in c["months_2013"] or "2013-10" in c["months_2013"]]
print(f"Candidates in 2013-03 or 2013-10: {len(in_both)}")

# Winner check
winner_norm = "0589"
for p in plays:
    if p["candidate"] == winner_norm:
        print(f"\n🏆 Winner {winner_norm}:")
        print(f"  Groups: {p.get('months', [])}")
        print(f"  Total appearances: {p.get('total_appearances', 0)}")
        print(f"  Draw dates: {p.get('draw_dates', [])}")
        break

# KEY INSIGHT: What is MLD actually doing?
print("\n" + "=" * 60)
print("  💡 KEY INSIGHT")
print("=" * 60)
print(f"""
MLD's "Hot month repeated" with Count: 22 means:
  - It selected months 2013-03 and 2013-10
  - It found ALL draws in those 2 months
  - It deduplicated by sorted digits
  - Result: 22 unique sorted numbers

Our cluster_year with mc≥2:
  - Groups by year: 8 years qualify (count≥2 each)
  - Pulls draws from hit-months within ALL 8 years
  - Result: {len(plays)} unique sorted numbers

The difference: MLD only uses 2013 (manually selected).
We use ALL 8 qualifying years.

To match MLD's 22: we'd need a mode that limits to 
just the TOP year or lets the user pick specific years.
""")

# What if we ONLY used 2013?
from_2013_only = set()
for p in plays:
    months = p.get("months", [])
    if "2013" in months:
        from_2013_only.add(p["candidate"])

print(f"If we only used 2013: ~{len(from_2013_only)} unique candidates have 2013 in their groups")
print("(But the actual count from only 2013's hit-months would be smaller)")

# Try monthly mc≥2 to see what months qualify
print("\n" + "=" * 60)
print("  📋 Monthly mc≥2 comparison")
print("=" * 60)

body2 = dict(body, grouping="monthly", min_count=2)
r2 = requests.post(api("/api/rbtl/backtest-v2"), json=body2, timeout=60)
data2 = r2.json()

m_months = data2.get("top_months", [])
print(f"Monthly mc≥2 hot months: {len(m_months)}")
for m in m_months:
    print(f"  {m['month']}: count={m['count']}, draws={m.get('total_draws_in_month','?')}, "
          f"unique={m.get('unique_actuals_in_month','?')}")

m_plays = data2.get("suggested_plays", [])
print(f"Monthly mc≥2 candidates: {len(m_plays)}")

print("\nDone! 🎉")
