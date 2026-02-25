#!/usr/bin/env python3
"""Check what states and pick5 game names exist in MongoDB."""
import os
from pymongo import MongoClient

MONGO_URL = os.environ.get('MONGO_URL', '')
client = MongoClient(MONGO_URL)
db = client['lottery']

# Check both collections
for coll_name in ['lottery_v2', 'lotterypost']:
    coll = db[coll_name]
    print(f"\n{'='*60}")
    print(f"Collection: {coll_name}")
    print(f"{'='*60}")
    
    states = coll.distinct('state_name')
    print(f"\nAll states ({len(states)}):")
    for s in sorted(states):
        print(f"  {s}")
    
    # Check pick5-related games per state
    pick5_keywords = ['pick 5', 'pick5', 'play 5', 'daily 5', 'dc 5', 'georgia five', 'cash 5']
    print(f"\nPick 5 games by state:")
    for state in sorted(states):
        games = coll.distinct('game_name', {'state_name': state})
        p5 = [g for g in games if any(k in g.lower() for k in pick5_keywords)]
        if p5:
            count = coll.count_documents({'state_name': state, 'game_name': {'$in': p5}})
            print(f"  {state}: {p5} ({count} draws)")
    
    # Specifically check DE, MD, DC
    print(f"\nSpecific state checks:")
    for needle in ['Delaware', 'delaware', 'DE', 'Maryland', 'maryland', 'MD', 
                   'Washington', 'washington', 'DC', 'District']:
        matches = [s for s in states if needle.lower() in s.lower()]
        if matches:
            print(f"  '{needle}' → {matches}")
