#!/usr/bin/env python3
"""
================================================================
  Cross-Fire Random Date Test
================================================================
  Picks a random historical date, grabs the draws around it,
  then tests: would the nudge + RBTL cross-fire have caught
  the winning number?

  USAGE:
    python crossfire_test.py                # Random date
    python crossfire_test.py --date 2019-10-09 --tod midday  # Specific
    python crossfire_test.py --runs 20      # Run 20 random tests
================================================================
"""

import json, random, sys, argparse, time
from urllib.request import Request, urlopen
from itertools import combinations, product, permutations
from datetime import datetime, timedelta

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

def api_post(path, body):
    sep = "&" if "?" in path else "?"
    url = f"{BASE_URL}{path}{sep}db={DB_MODE}"
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None

def fetch_draws(s, e):
    d = api_post("/api/draws/recent", {"state":"Florida","game_type":"pick4","start_date":s,"end_date":e})
    return d.get("draws",[]) if d else []

# ── Nudge Generators ──────────────────────────────────────────
def circ(d, off): return (int(d) + off) % 10

def gen_1dig(seed):
    s = str(seed).zfill(4)
    c = set([s])
    for p in range(4):
        for o in [-1,1]:
            n = list(s); n[p] = str(circ(s[p],o)); c.add("".join(n))
    return c

def gen_2dig(seed):
    s = str(seed).zfill(4)
    c = set()
    for pair in combinations(range(4), 2):
        for offs in product([-1,1], repeat=2):
            n = list(s)
            for i, p in enumerate(pair): n[p] = str(circ(s[p],offs[i]))
            c.add("".join(n))
    return c | gen_1dig(seed)

def gen_pos1(seed):
    s = str(seed).zfill(4)
    c = set()
    for combo in product(range(-1,2), repeat=4):
        c.add("".join(str(circ(s[i],combo[i])) for i in range(4)))
    return c

def gen_t25(seed):
    """3 digits ±1 + 1 wild (any distance)"""
    s = str(seed).zfill(4)
    cands = set()
    for wild_pos in range(4):
        for wild_off in range(-5, 6):
            new = list(s)
            new[wild_pos] = str(circ(s[wild_pos], wild_off))
            other = [p for p in range(4) if p != wild_pos]
            for offs in product(range(-1, 2), repeat=3):
                final = list(new)
                for i, p in enumerate(other):
                    final[p] = str(circ(s[p], offs[i]))
                cands.add("".join(final))
    return cands

# ── Single Test ────────────────────────────────────────────────
def run_single_test(target_date=None, target_tod=None, verbose=True):
    """Run one cross-fire test. Returns dict with results."""
    
    # Pick random date if not specified
    if not target_date:
        year = random.randint(2000, 2025)
        month = random.randint(1, 12)
        day = random.randint(2, 28)
        target_date = f"{year:04d}-{month:02d}-{day:02d}"
    
    if not target_tod:
        target_tod = random.choice(["midday", "evening"])

    dt = datetime.strptime(target_date, "%Y-%m-%d")
    start = (dt - timedelta(days=2)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

    if verbose:
        print(f"\n{'='*64}")
        print(f"  🎲 CROSS-FIRE TEST: {target_date} {target_tod}")
        print(f"{'='*64}")

    draws = fetch_draws(start, end)
    if not draws:
        if verbose: print(f"  ⚠ No draws found around {target_date}")
        return None

    # Sort
    tod_ord = {"midday": 0, "evening": 1}
    draws.sort(key=lambda d: (d.get("date",""), tod_ord.get(d.get("tod","").lower(), 2)))

    if verbose:
        print(f"\n  Draws in window:")
        for d in draws:
            marker = " ◄◄ TARGET" if d.get("date") == target_date and d.get("tod","").lower() == target_tod else ""
            print(f"    {d.get('date','')} {d.get('tod','').lower():<8} {d.get('value','')}{marker}")

    # Find target and previous draw
    target_val = None
    prev_val = None
    for i, d in enumerate(draws):
        if d.get("date") == target_date and d.get("tod","").lower() == target_tod:
            target_val = d.get("value","")
            if i > 0:
                prev_val = draws[i-1].get("value","")
                prev_info = f"{draws[i-1].get('date','')} {draws[i-1].get('tod','').lower()}"
            break

    if not target_val or not prev_val:
        if verbose: print(f"  ⚠ Missing target or previous draw")
        return None

    if verbose:
        print(f"\n  Seed: {prev_val} ({prev_info})")
        print(f"  Target: {target_val} ({target_date} {target_tod})")

    # Generate nudge tiers
    t1 = gen_1dig(prev_val)
    t2 = gen_2dig(prev_val)
    t3 = gen_pos1(prev_val)
    t25 = gen_t25(prev_val)

    # Nudge results
    tiers = {"T1": t1, "T2": t2, "T3": t3, "T2.5": t25}
    nudge_hits = {}
    
    if verbose: print(f"\n  📊 NUDGE TIERS from {prev_val}:")
    for name in ["T1", "T2", "T3", "T2.5"]:
        cset = tiers[name]
        hit = target_val in cset
        nudge_hits[name] = hit
        if verbose:
            h = "✅ HIT" if hit else "❌"
            print(f"    {name:<22} {len(cset):>5} cands  {h}")

    # RBTL Shadow backtest
    if verbose: print(f"\n  📡 RBTL Shadow for {target_date} {target_tod}...")
    bt = api_post("/api/rbtl/backtest-v2", {
        "state": "Florida", "game_type": "pick4",
        "target_date": target_date, "target_tod": target_tod,
        "lookback_days": -1, "min_count": 2, "dp_size": 0,
        "dp_seed_mode": "last", "suggested_limit": 999,
        "include_same_day": True, "look_forward_days": 0,
    })

    rbtl_candidates = set()
    rbtl_hit = False
    rbtl_rank = None
    rbtl_total = 0

    if bt and not bt.get("error"):
        for c in bt.get("candidates", []):
            v = c.get("value","") if isinstance(c, dict) else str(c)
            if v: rbtl_candidates.add(v)
        rbtl_total = bt.get("total_candidates", len(rbtl_candidates))
        for wr in bt.get("winner_results", []):
            if wr.get("found_in_candidates"):
                rbtl_hit = True
                rbtl_rank = wr.get("rank")
                break
        if verbose:
            h = f"✅ HIT #{rbtl_rank}/{rbtl_total}" if rbtl_hit else f"❌ 0/{rbtl_total}"
            print(f"    RBTL: {rbtl_total} candidates  {h}")
    else:
        if verbose: print(f"    ⚠ RBTL failed")

    # Cross-fire intersections
    cf_results = {}
    target_norm = "".join(sorted(target_val))

    if verbose: print(f"\n  🔥 CROSS-FIRE (Nudge ∩ RBTL):")
    for name in ["T1", "T2", "T3", "T2.5"]:
        overlap = tiers[name] & rbtl_candidates
        # Normalized match
        tier_norms = {"".join(sorted(c)): c for c in tiers[name]}
        rbtl_norms = {"".join(sorted(r)): r for r in rbtl_candidates}
        norm_match = set(tier_norms.keys()) & set(rbtl_norms.keys())
        
        all_overlap = set(overlap)
        for n in norm_match:
            all_overlap.add(rbtl_norms[n])

        cf_hit = any(o == target_val or "".join(sorted(o)) == target_norm for o in all_overlap)
        cf_results[name] = {"size": len(all_overlap), "hit": cf_hit}

        if verbose:
            h = " 🏆 WINNER IN CF!" if cf_hit else ""
            print(f"    {name} ∩ RBTL = {len(all_overlap):>4} candidates{h}")
            if all_overlap and len(all_overlap) <= 25:
                for o in sorted(all_overlap):
                    star = " ★★★" if (o == target_val or "".join(sorted(o)) == target_norm) else ""
                    print(f"      {o}{star}")

    # Summary
    if verbose:
        print(f"\n  {'─'*50}")
        any_cf = any(v["hit"] for v in cf_results.values())
        if any_cf:
            print(f"  🏆 CROSS-FIRE SUCCESS!")
        elif rbtl_hit:
            print(f"  📡 RBTL hit but no cross-fire overlap")
        elif any(nudge_hits.values()):
            print(f"  🎯 Nudge hit but no RBTL confirmation")
        else:
            print(f"  ❌ No hits in this test")

    return {
        "date": target_date, "tod": target_tod,
        "seed": prev_val, "target": target_val,
        "nudge": nudge_hits, "rbtl_hit": rbtl_hit, "rbtl_rank": rbtl_rank,
        "rbtl_total": rbtl_total, "crossfire": cf_results,
    }


# ── Batch Test ─────────────────────────────────────────────────
def run_batch(n_runs, delay=0.5):
    print(f"\n{'='*64}")
    print(f"  🧪 BATCH CROSS-FIRE TEST — {n_runs} random dates")
    print(f"{'='*64}")

    results = []
    for i in range(n_runs):
        print(f"\n[{i+1}/{n_runs}]", end="")
        r = run_single_test(verbose=True)
        if r:
            results.append(r)
        time.sleep(delay)

    if not results:
        print("No valid results")
        return

    n = len(results)
    print(f"\n\n{'='*64}")
    print(f"  📊 BATCH RESULTS — {n} valid tests")
    print(f"{'='*64}")

    # Nudge hit rates
    print(f"\n  NUDGE TIERS:")
    for name in ["T1", "T2", "T3", "T2.5"]:
        hits = sum(1 for r in results if r["nudge"].get(name))
        print(f"    {name:<12} {hits}/{n} hits ({hits/n*100:.1f}%)")

    # RBTL
    rbtl_hits = sum(1 for r in results if r["rbtl_hit"])
    print(f"\n  RBTL:         {rbtl_hits}/{n} hits ({rbtl_hits/n*100:.1f}%)")

    # Cross-fire
    print(f"\n  CROSS-FIRE:")
    for name in ["T1", "T2", "T3", "T2.5"]:
        cf_hits = sum(1 for r in results if r["crossfire"].get(name, {}).get("hit"))
        avg_size = sum(r["crossfire"].get(name, {}).get("size", 0) for r in results) / n
        print(f"    {name} ∩ RBTL: {cf_hits}/{n} hits ({cf_hits/n*100:.1f}%), avg {avg_size:.0f} candidates")

    # Show all results summary
    print(f"\n  {'Date':<12} {'TOD':<8} {'Seed':>6} {'Target':>6} {'RBTL':>6} {'T2.5':>5} {'CF':>5}")
    print(f"  {'─'*55}")
    for r in results:
        rbtl = f"#{r['rbtl_rank']}" if r['rbtl_hit'] else "—"
        t25 = "✅" if r["nudge"].get("T2.5") else "—"
        cf = "🏆" if r["crossfire"].get("T2.5", {}).get("hit") else "—"
        print(f"  {r['date']:<12} {r['tod']:<8} {r['seed']:>6} {r['target']:>6} {rbtl:>6} {t25:>5} {cf:>5}")


# ── Main ───────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Cross-Fire Random Date Test")
    p.add_argument("--date", help="Specific date YYYY-MM-DD (random if omitted)")
    p.add_argument("--tod", help="midday or evening (random if omitted)")
    p.add_argument("--runs", type=int, default=1, help="Number of random tests (default: 1)")
    p.add_argument("--delay", type=float, default=0.5, help="Delay between batch runs")
    args = p.parse_args()

    print("🔌 Testing API...", end="", flush=True)
    test = api_post("/api/draws/recent", {"state":"Florida","game_type":"pick4",
                                           "start_date":"2019-10-08","end_date":"2019-10-09"})
    if not test:
        print(f"\n❌ Cannot reach {BASE_URL}")
        sys.exit(1)
    print(" ✓")

    if args.runs > 1:
        run_batch(args.runs, args.delay)
    else:
        run_single_test(args.date, args.tod, verbose=True)

if __name__ == "__main__":
    main()
