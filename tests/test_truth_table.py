"""
Test: Truth Table ∩ RBTL Backtest Integration
==============================================
Tests the truth_table_seed parameter on the backtest-v2 endpoint.
Runs Win #1, Win #2, and the 0371 FL July 2024 scenario.
"""
import requests, json

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

def test(label, target_date, target_tod, tt_seed, state="Florida",
         grouping="monthly", min_count=2, dp_size=0):
    body = {
        "state": state, "game_type": "pick4",
        "target_date": target_date, "target_tod": target_tod,
        "lookback_days": -1, "min_count": min_count, "dp_size": dp_size,
        "dp_seed_mode": "last", "suggested_limit": 999,
        "include_same_day": True, "look_forward_days": 0,
        "grouping": grouping, "truth_table_seed": tt_seed,
    }
    r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
    d = r.json()

    if d.get("error"):
        print(f"\n  ❌ {label}: ERROR — {d['error']}")
        return

    plays = d.get("suggested_plays", [])
    winners = d.get("winner_results", [])
    tt_combos = d.get("truth_table_combos", 0)
    tt_unique = d.get("truth_table_unique", 0)

    found = False
    rank = 0
    for wr in winners:
        if wr.get("found_in_candidates"):
            found = True
            rank = wr.get("rank", 0)

    status = f"✅ #{rank}/{len(plays)}" if found else f"❌ ({len(plays)} candidates)"
    print(f"\n  {label}")
    print(f"    TT seed: {tt_seed} → {tt_combos} combos, {tt_unique} unique sorted")
    print(f"    Grouping: {grouping}, mc≥{min_count}, dp={dp_size}")
    print(f"    Result: {status}")
    if found:
        cost = len(plays)
        print(f"    Cost: ${cost} → $5,000 payout = {5000/cost:.0f}x ROI")

    # Also test without TT for comparison
    body2 = dict(body, truth_table_seed="")
    r2 = requests.post(api("/api/rbtl/backtest-v2"), json=body2, timeout=60)
    d2 = r2.json()
    plays2 = d2.get("suggested_plays", [])
    found2 = any(wr.get("found_in_candidates") for wr in d2.get("winner_results", []))
    print(f"    Without TT: {len(plays2)} candidates, found={found2}")
    print(f"    TT reduction: {len(plays2)} → {len(plays)} ({(1-len(plays)/max(len(plays2),1))*100:.0f}% cut)")


print("=" * 60)
print("  🔢 TRUTH TABLE ∩ RBTL INTEGRATION TEST")
print("=" * 60)

# Test 1: Win #1 — FL 2019-09-15 evening
# Seed for TT: need the last draw before 2019-09-15 evening
test("Win #1: Sniper + TT (seed=6899 from target)",
     "2019-09-15", "evening", "6899",
     grouping="monthly", min_count=1, dp_size=2)

# Test 2: Win #2 — FL 2019-10-09 midday
test("Win #2: Shadow + TT (seed=4426 from 10/08 eve)",
     "2019-10-09", "midday", "4426",
     grouping="monthly", min_count=2, dp_size=0)

# Test 3: Win #2 with cluster_year
test("Win #2: cluster_year + TT",
     "2019-10-09", "midday", "4426",
     grouping="cluster_year", min_count=2, dp_size=0)

# Test 4: 0371 FL 2024-07-17
test("FL 2024-07-17: monthly + TT (seed=0371)",
     "2024-07-17", "", "0371",
     grouping="monthly", min_count=1, dp_size=0)

test("FL 2024-07-17: cluster_year + TT (seed=0371)",
     "2024-07-17", "", "0371",
     grouping="cluster_year", min_count=2, dp_size=0)

# Test 5: Solo TT (no RBTL, just mc≥1 to get all months, then intersect)
test("FL 2024-07-17: mc≥1 + TT only (seed=0371)",
     "2024-07-17", "midday", "0371",
     grouping="monthly", min_count=1, dp_size=0)

print(f"\n{'='*60}")
print("  Done! 🎉")
