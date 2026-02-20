"""
Test: Are MLD's 22 numbers the ones that appear in MULTIPLE months within the year?
i.e., the intersection / repeated numbers across 2013-03 AND 2013-10
"""

import requests, json

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

# Get monthly mc≥1 dp=0 to see ALL months and all candidates
body = {
    "state": "Florida", "game_type": "pick4",
    "target_date": "2019-10-09", "target_tod": "midday",
    "lookback_days": -1, "min_count": 1, "dp_size": 0,
    "dp_seed_mode": "last", "suggested_limit": 999,
    "include_same_day": True, "look_forward_days": 0,
    "grouping": "monthly",
}

r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
data = r.json()

plays = data.get("suggested_plays", [])
print(f"Total candidates (monthly mc≥1 dp=0): {len(plays)}")

# Build: for each candidate, which months was it drawn in?
# The draw_dates field has month info
cand_months = {}  # candidate -> set of months
for p in plays:
    c = p["candidate"]
    months = set()
    for dd in p.get("draw_dates", []):
        months.add(dd.get("month", ""))
    cand_months[c] = months

# Now check: which candidates appear in BOTH 2013-03 AND 2013-10?
in_2013_03 = set(c for c, ms in cand_months.items() if "2013-03" in ms)
in_2013_10 = set(c for c, ms in cand_months.items() if "2013-10" in ms)
in_both = in_2013_03 & in_2013_10

print(f"\nCandidates in 2013-03: {len(in_2013_03)}")
print(f"Candidates in 2013-10: {len(in_2013_10)}")
print(f"Candidates in BOTH (intersection): {len(in_both)}")
print(f"  → {sorted(in_both)}")

# MLD's numbers for comparison
mld_raw = "9072 7920 8950 8590 9171 7911 4164 4641 6144 6184 8614 8247 4872 2758 7825 7933 9373 7933 8396 8639 9793 9937".split()
mld_sorted = sorted(set("".join(sorted(n)) for n in mld_raw))
print(f"\nMLD's numbers (sorted/unique): {len(mld_sorted)}")
print(f"  → {mld_sorted}")

# Compare
match = set(mld_sorted) & in_both
only_mld = set(mld_sorted) - in_both
only_ours = in_both - set(mld_sorted)

print(f"\nOverlap: {len(match)}")
print(f"In MLD but not intersection: {only_mld}")
print(f"In intersection but not MLD: {only_ours}")

# Now check: what about the Repeated column in MLD?
# MLD's "Repeated" for a month = all OTHER draws in that month 
# (not the seed inputs themselves)
# So "Repeated" for 2013-03 = all draws in March 2013 except the seed-matching inputs
# And "Hot month repeated" = union of Repeated from selected months

# Let's get the seed inputs for each month
top_months = data.get("top_months", [])
seed_inputs = {}
for m in top_months:
    seed_inputs[m["month"]] = set(m.get("input_values", []))

print(f"\nSeed inputs in 2013-03: {seed_inputs.get('2013-03', set())}")
print(f"Seed inputs in 2013-10: {seed_inputs.get('2013-10', set())}")

# The "Repeated" = draws in month that are NOT the seed inputs
# But wait — MLD shows the Repeated column per month
# Let's look at it differently

# Actually, MLD's Repeated column shows:
# For month 2013-03: "6144 4164 9793 7933 *7933 9937 *7933"
# For month 2013-10: "7920 9072 8396 8639"  
# And the "Hot month repeated" = UNION of all Repeated values from selected months

# So it's NOT an intersection. It's a UNION of the Repeated columns.
# The Repeated column = all draws in that month EXCLUDING the Inputs

# Let me check: how many candidates are in 2013-03 OR 2013-10 (union)?
in_either = in_2013_03 | in_2013_10
print(f"\nCandidates in 2013-03 OR 2013-10 (union): {len(in_either)}")

# But subtract the seed inputs (which are in the Inputs column, not Repeated)
seed_actuals = set(data.get("seed_actuals", []))
print(f"Seed actuals: {seed_actuals}")

# Get ALL input values across qualifying months
all_inputs_2013 = set()
for m in top_months:
    if m["month"] in ("2013-03", "2013-10"):
        for iv in m.get("input_values", []):
            all_inputs_2013.add("".join(sorted(iv)))
print(f"Seed input actuals in 2013-03/10: {all_inputs_2013}")

# Repeated = candidates from those months MINUS the seed inputs
repeated = in_either - all_inputs_2013
print(f"'Repeated' (union minus inputs): {len(repeated)}")
print(f"  → {sorted(repeated)[:30]}...")

# Now check if this matches MLD's 22 raw numbers / 10 unique
# Wait - MLD says Count: 22 but that's 22 RAW entries not unique sorted
# The raw list has duplicates (7933 appears twice in input)
# Let's count raw

print(f"\nMLD raw count: {len(mld_raw)} (before dedup)")
print(f"MLD unique sorted: {len(mld_sorted)}")

# Hmm, 22 raw but only 10 unique sorted... that's a lot of permutations
# Let me check which MLD numbers are inputs vs repeated
for n in mld_raw:
    ns = "".join(sorted(n))
    is_input = ns in all_inputs_2013
    in_03 = ns in in_2013_03
    in_10 = ns in in_2013_10
    print(f"  {n} → {ns}  input={'✓' if is_input else ' '}  "
          f"in 2013-03={'✓' if in_03 else ' '}  in 2013-10={'✓' if in_10 else ' '}")

print("\n" + "=" * 60)
print("  💡 CONCLUSION")
print("=" * 60)
print(f"""
MLD's 22 = raw Repeated values from 2013-03 + 2013-10 (with duplicates)
         = {len(mld_sorted)} unique sorted values

Our system groups by year and pulls draws from ALL hit-months in ALL 
qualifying years (8 years × multiple months each).

To get a 22-candidate list, we'd need:
  Option A: top_n_years=1 parameter (only use best year)
  Option B: A "repeated-only" mode that excludes seed inputs
  Option C: MLD-style manual year/month selection in the UI
""")
