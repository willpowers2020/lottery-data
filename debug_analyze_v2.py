#!/usr/bin/env python3
"""Debug v2: inspect results array from analyze endpoint."""

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

print("=== RESULTS ARRAY ===")
print(f"  Length: {len(data.get('results', []))}")

results = data.get('results', [])
if results:
    print(f"\n=== FIRST RESULT (all fields) ===")
    print(json.dumps(results[0], indent=2, default=str))
    
    print(f"\n=== FIRST 3 RESULTS (key fields) ===")
    for i, r in enumerate(results[:3]):
        print(f"\n  [{i}] keys: {list(r.keys())}")
        for k, v in r.items():
            print(f"      {k}: {v}")

    print(f"\n=== UNIQUE 'norm' or similar VALUES (first 20) ===")
    for key in ['norm', 'normalized', 'actual', 'value']:
        vals = [r.get(key) for r in results[:20] if r.get(key)]
        if vals:
            print(f"  Field '{key}': {vals[:10]}")

    print(f"\n=== DATE FIELDS (first 5) ===")
    for key in ['date', 'draw_date', 'input_date', 'month']:
        vals = [r.get(key) for r in results[:5] if r.get(key)]
        if vals:
            print(f"  Field '{key}': {vals}")

print(f"\n=== PAST WINNERS ACTUAL ===")
print(f"  {data.get('past_winners_actual', [])}")

print(f"\n=== PAST WINNERS ===")
print(f"  {data.get('past_winners', [])}")
