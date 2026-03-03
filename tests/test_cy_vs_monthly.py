"""
Quick test: Does cluster_year find winners that monthly misses?
Tests across Sep 15 - Oct 31, 2019 Florida Pick 4
"""
import requests, sys

base = input("Flask URL [http://localhost:5001]: ").strip() or "http://localhost:5001"
db = input("DB mode [mongo_v2]: ").strip() or "mongo_v2"

def api(path):
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}db={db}"

# Get all draws in range
r = requests.post(api("/api/draws/recent"), json={
    "state": "Florida", "game_type": "pick4",
    "start_date": "2019-09-15", "end_date": "2019-10-31"
}, timeout=15)
all_draws = r.json().get("draws", [])

# Filter to evening + midday
targets = [d for d in all_draws if (d.get("tod") or "").lower() in ("evening", "midday")]
targets.sort(key=lambda d: (d["date"], d.get("tod", "")))

print(f"Testing {len(targets)} draws from 2019-09-15 to 2019-10-31\n")

# For each draw, test: monthly mc≥2 dp=0 vs cluster_year mc≥2 dp=0
results = []
for i, t in enumerate(targets):
    tdate = t["date"]
    ttod = (t.get("tod") or "").lower()
    tactual = t.get("actual", "?")

    sys.stdout.write(f"\r  [{i+1}/{len(targets)}] {tdate} {ttod}...          ")
    sys.stdout.flush()

    row = {"date": tdate, "tod": ttod, "actual": tactual}

    for grouping in ["monthly", "cluster_year"]:
        body = {
            "state": "Florida", "game_type": "pick4",
            "target_date": tdate, "target_tod": ttod,
            "lookback_days": -1, "min_count": 2, "dp_size": 0,
            "dp_seed_mode": "last", "suggested_limit": 999,
            "include_same_day": True, "look_forward_days": 0,
            "grouping": grouping,
        }
        try:
            r = requests.post(api("/api/rbtl/backtest-v2"), json=body, timeout=60)
            data = r.json()
            if data.get("error"):
                row[grouping] = {"found": False, "error": True}
                continue

            plays = data.get("suggested_plays", [])
            winner_results = data.get("winner_results", [])

            found = False
            rank = 0
            for wr in winner_results:
                if wr.get("found_in_candidates"):
                    found = True
                    rank = wr.get("rank", 0)

            row[grouping] = {"found": found, "rank": rank, "total": len(plays)}
        except:
            row[grouping] = {"found": False, "error": True}

    results.append(row)

print(f"\r  ✅ Done testing {len(targets)} draws                    \n")

# Summary
print(f"{'Date':<12}{'TOD':<9}{'Winner':<8}{'Monthly mc≥2':<20}{'cluster_year mc≥2':<20}{'Better?'}")
print("-" * 80)

monthly_wins = 0
cy_wins = 0
cy_only = 0
monthly_only = 0
both = 0
cy_better = 0

for r in results:
    m = r.get("monthly", {})
    c = r.get("cluster_year", {})

    m_str = f"#{m['rank']}/{m['total']}" if m.get("found") else "❌"
    c_str = f"#{c['rank']}/{c['total']}" if c.get("found") else "❌"

    better = ""
    if m.get("found"):
        monthly_wins += 1
    if c.get("found"):
        cy_wins += 1

    if c.get("found") and not m.get("found"):
        cy_only += 1
        better = "🟢 CY saves"
    elif m.get("found") and not c.get("found"):
        monthly_only += 1
        better = "🔵 Monthly saves"
    elif m.get("found") and c.get("found"):
        both += 1
        if c["total"] < m["total"]:
            cy_better += 1
            better = f"📉 CY tighter ({c['total']} vs {m['total']})"
        elif c["rank"] < m["rank"]:
            better = f"📈 CY higher rank"

    print(f"{r['date']:<12}{r['tod']:<9}{r['actual']:<8}{m_str:<20}{c_str:<20}{better}")

print(f"\n{'='*60}")
print(f"Monthly mc≥2 finds winner: {monthly_wins}/{len(results)}")
print(f"cluster_year mc≥2 finds:   {cy_wins}/{len(results)}")
print(f"cluster_year SAVES (monthly missed): {cy_only}")
print(f"Monthly SAVES (cy missed):           {monthly_only}")
print(f"Both find, cy has smaller list:      {cy_better}/{both}")
