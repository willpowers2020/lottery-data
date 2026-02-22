# MyLottoData (MLD) — Database Reference

## Connection
- **Type:** MongoDB Atlas
- **URI:** `mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/`
- **Database:** `lottery`
- **Collections:**
  - `lottery_v2` — Optimized schema (current / preferred)
  - `lotterypost` — Original schema (legacy)

## App
- **Framework:** Python (Flask)
- **Local URL:** http://localhost:5001
- **DB Mode:** `mongo_v2`
- **Project path:** `/Users/british.williams/mylottodata-query-tool/`
- **Main file:** `app.py`
- **Sync script:** `lottery_master_sync.py`

## lottery_v2 Document Schema (Pick 5 example)
```json
{
  "_id": "6974db97f4fefd3c4e1ed28c",
  "country": "United States",
  "state": "pa",
  "state_name": "Pennsylvania",
  "game": "pick-5-evening",
  "game_name": "Pick 5 Evening",
  "game_type": "pick5",
  "date": "2008-09-02 00:00:00",
  "numbers": "[\"8\", \"6\", \"6\", \"9\", \"1\"]",
  "number_str": "86691",
  "normalized": "16689",
  "digits_sum": 30,
  "pairs_2dp": ["16", "18", "19", "66", "68", "69", "89"],
  "triples_3dp": ["166", "168", "169", "189", "668", "669", "689"],
  "tod": "Evening",
  "num_digits": 5,
  "source": "sqlite"
}
```

## Key Fields
| Field | Description |
|-------|-------------|
| `game_type` | `"pick5"` or `"pick4"` |
| `state` | 2-letter lowercase code (e.g. `"pa"`) |
| `state_name` | Full name (e.g. `"Pennsylvania"`) |
| `date` | Draw date as string `"YYYY-MM-DD HH:MM:SS"` |
| `number_str` | Raw 5-digit draw (e.g. `"86691"`) |
| `normalized` | Digits sorted ascending (e.g. `"16689"`) |
| `digits_sum` | Sum of all digits (pre-calculated) |
| `tod` | Time of day: `"Evening"`, `"Midday"`, `"Day"`, etc. |
| `numbers` | JSON string array of individual digits |
| `pairs_2dp` | All 2-digit pair combos (sorted) |
| `triples_3dp` | All 3-digit triple combos (sorted) |

## Computed Fields (NOT in DB — must calculate)
- **TD (Total Differences):** Sum of absolute differences between consecutive digits
  - e.g. `86691` → |8-6| + |6-6| + |6-9| + |9-1| = 2+0+3+8 = 13
- **ΔSums TD:** `digits_sum - TD`
- **Sums:** Same as `digits_sum` (already in DB)

## Querying Pick 5 All States
```python
from pymongo import MongoClient
client = MongoClient('mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/')
db = client['lottery']
coll = db['lottery_v2']

# All Pick 5 draws in date range
results = coll.find({
    'game_type': 'pick5',
    'date': {
        '$gte': '2024-01-01',
        '$lte': '2025-02-21'
    }
}).sort('date', 1)
```

## Notes
- Date is stored as a string, so string comparison works for range queries
- `digits_sum` is pre-calculated in DB (no need to compute Sums)
- TD must be computed client-side from `number_str`
- Environment variable: `MONGO_URL` holds the connection string
