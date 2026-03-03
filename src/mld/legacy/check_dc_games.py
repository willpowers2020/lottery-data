#!/usr/bin/env python3
"""Check what DC games look like across all collections"""
from pymongo import MongoClient
MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net"
client = MongoClient(MONGO_URL)

print("=" * 60)
print("  DC GAME NAMES ACROSS ALL COLLECTIONS")
print("=" * 60)

# Check all DC name variants across collections
checks = [
    ('mylottodata', 'lotterypost', 'state', 'game'),
    ('lottery', 'lottery_v2', 'state_name', 'game_name'),
    ('lottery', 'lottery_v2_test', 'state_name', 'game_name'),
]

for db_name, coll_name, state_field, game_field in checks:
    coll = client[db_name][coll_name]
    print(f"\n📦 {db_name}.{coll_name}")
    
    # Find all DC-like state names
    all_states = coll.distinct(state_field)
    dc_states = [s for s in all_states if s and ('wash' in s.lower() or 'dc' in s.lower() or 'd.c' in s.lower())]
    
    for dc_name in dc_states:
        games = coll.distinct(game_field, {state_field: dc_name})
        # Filter to pick5-ish games
        p5_games = [g for g in games if any(x in g.lower() for x in ['5', 'five'])]
        count = coll.count_documents({state_field: dc_name}) if hasattr(coll, 'count_documents') else '?'
        print(f"  State: '{dc_name}' ({count} total records)")
        print(f"  All games: {games}")
        print(f"  Pick5-ish: {p5_games}")
        
        # Check Feb 25 specifically
        from datetime import datetime
        feb25 = coll.find({state_field: dc_name, game_field: {'$in': p5_games}, 'date': datetime(2026, 2, 25)})
        feb25_list = list(feb25)
        print(f"  Feb 25 draws: {len(feb25_list)}")
        for d in feb25_list:
            nums = d.get('winning_numbers', d.get('numbers', d.get('winning_number', '?')))
            tod = d.get('tod', d.get('draw_time', ''))
            gn = d.get(game_field, '')
            print(f"    {gn} | tod={tod} | nums={nums}")
    
    if not dc_states:
        print("  ⚠️  No DC state found!")
