#!/usr/bin/env python3
"""
Check Pick 5 data for Feb 25, 2026 against expected values
"""

import json
from datetime import datetime
from pymongo import MongoClient

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

EXPECTED_NORMALIZED = [
    "01358", "01456", "02348", "03577", "04568", "05899",
    "11149", "12256", "12457", "13499", "23448", "24499",
    "24788", "33589", "34589", "34788", "45889", "46789"
]

def parse_numbers(raw):
    if isinstance(raw, list): return [str(n) for n in raw]
    if isinstance(raw, str):
        try:
            p = json.loads(raw)
            if isinstance(p, list): return [str(n) for n in p]
        except: pass
    return []

def run():
    client = MongoClient(MONGO_URL)
    test_coll = client["lottery"]["lottery_v2_test"]
    lp_coll = client["mylottodata"]["lotterypost"]
    old_coll = client["lottery"]["lottery_v2"]
    
    feb25 = datetime(2026, 2, 25)
    
    print("=" * 70)
    print("  PICK 5 — Feb 25, 2026 — Expected vs Actual")
    print("=" * 70)
    
    # ── What does lotterypost have? ──
    print("\n📊 LOTTERYPOST (source of truth):")
    lp_docs = list(lp_coll.find({"date": feb25}).sort([("state_name", 1), ("game_name", 1)]))
    lp_pick5 = []
    for doc in lp_docs:
        nums = parse_numbers(doc.get("numbers"))
        if len(nums) == 5 and all(isinstance(n, str) and len(n) == 1 and n.isdigit() for n in nums):
            norm = "".join(sorted(nums))
            state = doc.get("state_name", "")
            game = doc.get("game_name", "")
            tod = doc.get("tod", "")
            lp_pick5.append({"state": state, "game": game, "tod": tod, "nums": nums, "norm": norm, "value": "".join(nums)})
    
    print(f"  Total Pick 5 records: {len(lp_pick5)}")
    for r in sorted(lp_pick5, key=lambda x: (x["state"], x["game"], x["tod"])):
        in_expected = "✅" if r["norm"] in EXPECTED_NORMALIZED else "⚠️"
        is_germany = " [GERMANY]" if r["state"] == "Germany" else ""
        print(f"  {in_expected} {r['state']} / {r['game']} / tod={r['tod']} → {r['value']} (norm: {r['norm']}){is_germany}")
    
    lp_norms = sorted(set(r["norm"] for r in lp_pick5 if r["state"] != "Germany"))
    print(f"\n  Normalized (excl Germany): {lp_norms}")
    print(f"  Count: {len(lp_norms)}")
    
    # ── Compare against expected ──
    print(f"\n📋 EXPECTED ({len(EXPECTED_NORMALIZED)} values, excl Germany):")
    expected_set = set(EXPECTED_NORMALIZED)
    lp_set = set(lp_norms)
    
    missing_from_lp = expected_set - lp_set
    extra_in_lp = lp_set - expected_set
    
    if not missing_from_lp and not extra_in_lp:
        print(f"  ✅ PERFECT MATCH with lotterypost")
    else:
        if missing_from_lp:
            print(f"  ❌ Expected but NOT in lotterypost: {sorted(missing_from_lp)}")
        if extra_in_lp:
            print(f"  ⚠️  In lotterypost but NOT expected: {sorted(extra_in_lp)}")
    
    # ── What does lottery_v2_test have? ──
    print(f"\n📊 LOTTERY_V2_TEST (new format):")
    test_docs = list(test_coll.find({"date": feb25}).sort([("state_name", 1), ("game_name", 1)]))
    test_pick5 = []
    for doc in test_docs:
        gt = doc.get("game_type", "")
        if gt != "pick5":
            continue
        nums = parse_numbers(doc.get("numbers"))
        norm = doc.get("normalized", "".join(sorted(nums)) if nums else "")
        state = doc.get("state_name", "")
        game = doc.get("game_name", "")
        tod = doc.get("tod", "")
        test_pick5.append({"state": state, "game": game, "tod": tod, "norm": norm, "value": "".join(nums)})
    
    print(f"  Total Pick 5 records: {len(test_pick5)}")
    for r in sorted(test_pick5, key=lambda x: (x["state"], x["game"], x["tod"])):
        in_expected = "✅" if r["norm"] in EXPECTED_NORMALIZED else ("⚠️" if r["state"] == "Germany" else "❌")
        print(f"  {in_expected} {r['state']} / {r['game']} / tod={r['tod']} → {r['value']} (norm: {r['norm']})")
    
    test_norms = sorted(set(r["norm"] for r in test_pick5 if r["state"] != "Germany"))
    print(f"\n  Normalized (excl Germany): {test_norms}")
    print(f"  Count: {len(test_norms)}")
    
    missing_from_test = expected_set - set(test_norms)
    extra_in_test = set(test_norms) - expected_set
    
    if not missing_from_test and not extra_in_test:
        print(f"  ✅ PERFECT MATCH with expected")
    else:
        if missing_from_test:
            print(f"  ❌ Expected but MISSING from test: {sorted(missing_from_test)}")
        if extra_in_test:
            print(f"  ⚠️  In test but NOT expected: {sorted(extra_in_test)}")
    
    # ── What does old lottery_v2 have? ──
    print(f"\n📊 LOTTERY_V2 (old/current):")
    old_docs = list(old_coll.find({"date": feb25}).sort([("state_name", 1), ("game_name", 1)]))
    old_pick5 = []
    for doc in old_docs:
        gt = doc.get("game_type", "")
        if gt != "pick5":
            continue
        nums = parse_numbers(doc.get("numbers"))
        norm = doc.get("normalized", "".join(sorted(nums)) if nums else "")
        state = doc.get("state_name", "")
        game = doc.get("game_name", "")
        tod = doc.get("tod", "")
        old_pick5.append({"state": state, "game": game, "tod": tod, "norm": norm, "value": "".join(nums)})
    
    print(f"  Total Pick 5 records: {len(old_pick5)}")
    for r in sorted(old_pick5, key=lambda x: (x["state"], x["game"], x["tod"])):
        in_expected = "✅" if r["norm"] in EXPECTED_NORMALIZED else "⚠️"
        print(f"  {in_expected} {r['state']} / {r['game']} / tod={r['tod']} → {r['value']} (norm: {r['norm']})")
    
    old_norms = sorted(set(r["norm"] for r in old_pick5 if r["state"] != "Germany"))
    print(f"\n  Normalized (excl Germany): {old_norms}")
    print(f"  Count: {len(old_norms)}")
    
    missing_from_old = expected_set - set(old_norms)
    if missing_from_old:
        print(f"  ❌ Expected but MISSING from old: {sorted(missing_from_old)}")
    
    # ── Summary ──
    print(f"\n{'=' * 70}")
    print("📊 COMPARISON SUMMARY — Feb 25 Pick 5 (excl Germany)")
    print(f"{'=' * 70}")
    print(f"  Expected:        {len(EXPECTED_NORMALIZED)} normalized values")
    print(f"  Lotterypost:     {len(lp_norms)} {'✅' if len(lp_norms) >= 17 else '❌'}")
    print(f"  lottery_v2_test: {len(test_norms)} {'✅' if set(test_norms) == expected_set else '❌'}")
    print(f"  lottery_v2 old:  {len(old_norms)} {'✅' if set(old_norms) == expected_set else '❌'}")
    
    client.close()

if __name__ == "__main__":
    run()
