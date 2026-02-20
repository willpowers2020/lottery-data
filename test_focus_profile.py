"""
Test Focus profile: cluster_year + top_n_clusters=1 + client-side minTotalHits≥2
"""
import requests

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

# Focus profile: cluster_year, mc≥2, dp=0, top 1 year only
body = {
    "state": "Florida", "game_type": "pick4",
    "target_date": "2019-10-09", "target_tod": "midday",
    "lookback_days": -1, "min_count": 2, "dp_size": 0,
    "dp_seed_mode": "last", "suggested_limit": 999,
    "include_same_day": True, "look_forward_days": 0,
    "grouping": "cluster_year",
    "top_n_clusters": 1,  # Only use THE top year
}

r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
data = r.json()

if data.get("error"):
    print(f"ERROR: {data['error']}")
    exit()

plays = data.get("suggested_plays", [])
top_months = data.get("top_months", [])
winners = data.get("winner_results", [])

print(f"Seeds: {data.get('seed_values', [])}")
print(f"Grouping: {data.get('grouping', '?')}")
print(f"Hot groups used: {data.get('selected_month_count', '?')} / {data.get('total_hot_months', '?')}")
print(f"Top year(s): {[m['month'] for m in top_months]}")
for m in top_months:
    print(f"  {m['month']}: count={m['count']}, draws={m.get('total_draws_in_month','?')}, "
          f"unique={m.get('unique_actuals_in_month','?')}")

print(f"\n--- ALL candidates from top year: {len(plays)} ---")

# Client-side filter: minTotalHits ≥ 2 (like the UI dropdown)
filtered = [p for p in plays if p.get("total_appearances", 0) >= 2]
print(f"--- After minTotalHits ≥ 2: {len(filtered)} ---")

# Show the filtered list
for i, p in enumerate(filtered[:30]):
    c = p["candidate"]
    is_winner = any(wr.get("target_actual") == c for wr in winners)
    months = p.get("months", [])
    hits = p.get("total_appearances", 0)
    mc = p.get("month_count", 0)
    mark = " 🏆 WINNER" if is_winner else ""
    print(f"  #{i+1}: {c}  hits={hits}  groups={mc}  months={months}{mark}")

# Check winner
print("\n--- Winner status ---")
for wr in winners:
    found = wr.get("found_in_candidates", False)
    rank = wr.get("rank", "N/A")
    val = wr.get("target_actual", "?")
    hits = wr.get("total_appearances", 0)
    filt = wr.get("filter_reason", "")
    print(f"  {val}: found={found}, rank={rank}, hits={hits}")
    if filt:
        print(f"    filter_reason: {filt}")

# Check if winner survives minTotalHits≥2 filter
winner_norm = "0589"
winner_in_filtered = any(p["candidate"] == winner_norm for p in filtered)
print(f"\n  Winner in minTotalHits≥2 list: {winner_in_filtered}")
if winner_in_filtered:
    rank_in_filtered = next(i+1 for i, p in enumerate(filtered) if p["candidate"] == winner_norm)
    print(f"  Rank in filtered list: #{rank_in_filtered} / {len(filtered)}")
    print(f"  Cost: ${len(filtered)}")

# Also try top_n=2
print("\n\n=== ALSO: top_n_clusters=2 ===")
body2 = dict(body, top_n_clusters=2)
r2 = requests.post(api("/api/rbtl/backtest-v2"), json=body2, timeout=60)
d2 = r2.json()
p2 = d2.get("suggested_plays", [])
f2 = [p for p in p2 if p.get("total_appearances", 0) >= 2]
tm2 = d2.get("top_months", [])
print(f"Top 2 years: {[m['month'] for m in tm2]}")
print(f"All candidates: {len(p2)}")
print(f"After minTotalHits≥2: {len(f2)}")
w_in = any(p["candidate"] == winner_norm for p in f2)
print(f"Winner in list: {w_in}")
if w_in:
    wr = next(i+1 for i, p in enumerate(f2) if p["candidate"] == winner_norm)
    print(f"Winner rank: #{wr}/{len(f2)}, cost=${len(f2)}")

print("\nDone!")
