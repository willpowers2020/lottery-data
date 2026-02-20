#!/usr/bin/env python3
"""Quick debug: inspect what /api/rbtl/analyze actually returns."""

import requests
import json

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

url = f"{BASE_URL}/api/rbtl/analyze?db={DB_MODE}"
payload = {
    "game_type": "pick4",
    "states": ["Florida"],
    "start_date": "2019-09-10",
    "end_date": "2019-09-15",
    "tod": "All"
}

resp = requests.post(url, json=payload, timeout=120)
data = resp.json()

print("=== TOP-LEVEL KEYS ===")
for k, v in data.items():
    if isinstance(v, list):
        print(f"  {k}: list of {len(v)} items")
    else:
        print(f"  {k}: {v}")

print("\n=== PAST WINNERS (first 5) ===")
for w in data.get('past_winners', [])[:5]:
    print(f"  {w}")

print("\n=== SAMPLE DRAWS (first 5) ===")
for d in data.get('draws', [])[:5]:
    print(f"  {json.dumps(d, indent=2, default=str)}")

print("\n=== DRAW FIELD NAMES ===")
if data.get('draws'):
    print(f"  {list(data['draws'][0].keys())}")

# Check what normalized seeds look like
seeds = ["5489", "0094", "0201", "9552", "1704", "1876", "8975"]
seed_norms = set(''.join(sorted(s)) for s in seeds)
print(f"\n=== SEED NORMS WE'RE LOOKING FOR ===")
print(f"  {sorted(seed_norms)}")

# Check what norms exist in draws
if data.get('draws'):
    draw_norms = set(d.get('norm', d.get('normalized', '???')) for d in data['draws'][:20])
    print(f"\n=== NORMS IN FIRST 20 DRAWS ===")
    print(f"  {sorted(draw_norms)}")
    
    # Check dates
    print(f"\n=== DATES IN FIRST 5 DRAWS ===")
    for d in data['draws'][:5]:
        print(f"  date={d.get('date')} | type={type(d.get('date')).__name__}")
