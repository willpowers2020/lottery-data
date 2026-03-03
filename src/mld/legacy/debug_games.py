#!/usr/bin/env python3
"""
Debug script to see all game names for problematic Pick5 states.
Run this to find out what game names exist in your MongoDB.
"""

import os
from pymongo import MongoClient

# Get MongoDB URL from environment or use default
MONGO_URL = os.environ.get('MONGO_URL', '')

if not MONGO_URL:
    print("ERROR: MONGO_URL environment variable not set!")
    print("Run: export MONGO_URL='your_mongodb_connection_string'")
    exit(1)

# Connect to MongoDB
client = MongoClient(MONGO_URL)
db = client['lottery']
collection = db['lottery_v2']

# States to check
states = ["Delaware", "Washington DC", "Georgia", "Pennsylvania"]

print("=" * 80)
print("GAME NAMES DEBUG REPORT")
print("=" * 80)

for state in states:
    print(f"\n{'='*40}")
    print(f"STATE: {state}")
    print(f"{'='*40}")
    
    # Get all unique game names for this state
    pipeline = [
        {"$match": {"state_name": state}},
        {"$group": {
            "_id": "$game_name",
            "count": {"$sum": 1},
            "sample_numbers": {"$first": "$numbers"},
            "sample_date": {"$first": "$date"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = list(collection.aggregate(pipeline))
    
    if not results:
        print(f"  ** NO DATA FOUND FOR {state} **")
        continue
    
    for r in results:
        game_name = r['_id']
        count = r['count']
        sample = r.get('sample_numbers', 'N/A')
        date = r.get('sample_date', 'N/A')
        
        # Try to determine number of digits
        if isinstance(sample, list):
            num_digits = len(sample)
        elif isinstance(sample, str):
            # Try to parse
            if sample.startswith('['):
                import json
                try:
                    parsed = json.loads(sample)
                    num_digits = len(parsed)
                except:
                    num_digits = '?'
            else:
                num_digits = len(sample.replace('-', '').replace(' ', ''))
        else:
            num_digits = '?'
        
        print(f"  Game: {game_name}")
        print(f"    Records: {count}, Digits: {num_digits}, Sample: {sample}")
        print()

print("\n" + "=" * 80)
print("SUMMARY: Copy the 5-digit game names above and add them to the pick5 patterns")
print("=" * 80)

client.close()
# EOF
