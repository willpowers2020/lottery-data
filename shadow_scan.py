#!/usr/bin/env python3
"""
================================================================
  Shadow Strategy Viability Scanner
================================================================
  Tests whether the Win #2 "Shadow" prediction algorithm works
  as a repeatable strategy across ALL of Florida Pick 4 history.

  For EVERY draw in history, the script:
    1. Calls /api/rbtl/backtest-v2 with shadow profile settings
    2. The API automatically picks the most recent seeds before
       that draw (handles 1-draw and 2-draw eras seamlessly)
    3. Checks if the actual drawn number appears in candidates
    4. Records hit/miss, rank, candidate count

  This is the true viability test: if you ran this strategy
  every single day, how often would it have hit?

  USAGE:
    python shadow_scan.py                        # Full history
    python shadow_scan.py --start 2019-01 --end 2019-12
    python shadow_scan.py --tod midday           # Midday only
    python shadow_scan.py --delay 0.1            # Faster

  Background:
    nohup python shadow_scan.py > scan.log 2>&1 &
    tail -f scan.log
================================================================
"""

import argparse
import json
import time
import csv
import sys
import os
from datetime import datetime, timedelta
from calendar import monthrange
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── Config ─────────────────────────────────────────────────────
BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"
STATE = "Florida"
GAME_TYPE = "pick4"

# Shadow profile — exact Win #2 settings
SHADOW = {
    "min_count": 2,
    "dp_size": 0,
    "lookback_days": -1,       # shadow mode: API picks seeds
    "dp_seed_mode": "last",
    "suggested_limit": 999,
    "include_same_day": True,
    "look_forward_days": 0,
}

DELAY = 0.3          # between API calls
BATCH_DELAY = 1.0    # between months
AUTOSAVE_EVERY = 50  # months


# ── API ────────────────────────────────────────────────────────
def api_url(path):
    sep = "&" if "?" in path else "?"
    return f"{BASE_URL}{path}{sep}db={DB_MODE}"


def api_post(path, body):
    url = api_url(path)
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, Exception) as e:
        return None


def fetch_draws(start_date, end_date):
    body = {"state": STATE, "game_type": GAME_TYPE,
            "start_date": start_date, "end_date": end_date}
    data = api_post("/api/draws/recent", body)
    return data.get("draws", []) if data else []


def run_shadow(target_date, target_tod):
    body = {
        "state": STATE, "game_type": GAME_TYPE,
        "target_date": target_date, "target_tod": target_tod,
        **SHADOW,
    }
    return api_post("/api/rbtl/backtest-v2", body)


# ── Dates ──────────────────────────────────────────────────────
def month_range(s, e):
    sy, sm = map(int, s.split("-"))
    ey, em = map(int, e.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12: m, y = 1, y + 1


def month_bounds(ym):
    y, m = map(int, ym.split("-"))
    _, ld = monthrange(y, m)
    return f"{ym}-01", f"{ym}-{ld:02d}"


# ── Scanner ────────────────────────────────────────────────────
def scan_month(ym, results, stats, test_tods):
    """
    Fetch every draw in the month. Each one becomes a target.
    Let the API's shadow mode auto-select seeds.
    """
    start, end = month_bounds(ym)
    draws = fetch_draws(start, end)
    if not draws:
        print(f"  No draws for {ym}")
        return

    # Sort chronologically
    draws.sort(key=lambda d: (d.get("date", ""), d.get("tod", "")))

    tested = 0
    hit_count = 0

    for draw in draws:
        dt = draw.get("date") or draw.get("input_date", "")
        tod = (draw.get("tod") or draw.get("draw_time", "")).lower()
        val = draw.get("value", "")

        if not dt or not tod or not val:
            continue
        if tod not in test_tods:
            continue

        tested += 1
        stats["total"] += 1
        tod_lbl = "mid" if tod == "midday" else "eve"

        print(f"    {dt} {tod_lbl} ({val})...", end="", flush=True)

        bt = run_shadow(dt, tod)
        time.sleep(DELAY)

        if not bt or bt.get("error"):
            err = (bt or {}).get("error", "no response")
            print(f" ⚠ {err}")
            stats["errors"] += 1
            continue

        candidates = bt.get("total_candidates", 0)
        hot_months = bt.get("selected_month_count", 0)
        seeds_used = bt.get("seed_count", 0)
        seed_vals = bt.get("seed_values", [])

        hit = False
        rank = None
        for wr in bt.get("winner_results", []):
            if wr.get("found_in_candidates"):
                hit = True
                rank = wr.get("rank")
                break

        if hit:
            hit_count += 1
            stats["hits"] += 1
            print(f" ✅ #{rank}/{candidates} (seeds:{seeds_used}, hot:{hot_months})")
        else:
            print(f" ❌ —/{candidates}")

        results.append({
            "date": dt,
            "tod": tod,
            "value": val,
            "normalized": "".join(sorted(val)),
            "seeds_used": seeds_used,
            "seed_values": "|".join(seed_vals),
            "hot_months": hot_months,
            "candidates": candidates,
            "hit": hit,
            "rank": rank,
        })

    print(f"  ✓ {ym}: {tested} draws tested, {hit_count} hits")


# ── Report ─────────────────────────────────────────────────────
def pct(n, d):
    return f"{n/d*100:.1f}" if d > 0 else "0"


def write_csv(results, path):
    if not results: return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)
    print(f"📄 CSV: {path}")


def write_report(results, stats, path, start_ym, end_ym):
    tot = stats["total"]
    hits = stats["hits"]
    errs = stats["errors"]
    hr = [r for r in results if r["hit"]]
    avg_c = sum(r["candidates"] for r in results) / len(results) if results else 0
    avg_r = sum(r["rank"] for r in hr if r["rank"]) / len(hr) if hr else 0

    # Breakdowns
    mid_r = [r for r in results if r["tod"] == "midday"]
    eve_r = [r for r in results if r["tod"] == "evening"]
    mid_h = len([r for r in mid_r if r["hit"]])
    eve_h = len([r for r in eve_r if r["hit"]])

    # Yearly
    yrs = {}
    for r in results:
        y = r["date"][:4]
        if y not in yrs: yrs[y] = {"t": 0, "h": 0}
        yrs[y]["t"] += 1
        if r["hit"]: yrs[y]["h"] += 1

    # Monthly (for chart)
    mos = {}
    for r in results:
        m = r["date"][:7]
        if m not in mos: mos[m] = {"t": 0, "h": 0}
        mos[m]["t"] += 1
        if r["hit"]: mos[m]["h"] += 1

    # Streaks
    max_dry = 0
    cur_dry = 0
    for r in results:
        if r["hit"]:
            cur_dry = 0
        else:
            cur_dry += 1
            max_dry = max(max_dry, cur_dry)

    # Rank distribution
    rank_buckets = {"1-10": 0, "11-50": 0, "51-100": 0, "101-200": 0, "200+": 0}
    for r in hr:
        rk = r["rank"] or 9999
        if rk <= 10: rank_buckets["1-10"] += 1
        elif rk <= 50: rank_buckets["11-50"] += 1
        elif rk <= 100: rank_buckets["51-100"] += 1
        elif rk <= 200: rank_buckets["101-200"] += 1
        else: rank_buckets["200+"] += 1

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shadow Strategy Viability — {start_ym} to {end_ym}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0c0e14;color:#e4e8f1;padding:20px;line-height:1.5}}
.c{{max-width:1400px;margin:0 auto}}
h1{{font-size:1.6rem;font-weight:800;background:linear-gradient(135deg,#f0b634,#f09544);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}}
.sub{{font-size:.82rem;color:#8b93a8;margin-bottom:24px}}
.sg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:24px}}
.s{{background:#13161f;border:1px solid #2a3042;border-radius:10px;padding:14px;text-align:center}}
.s .v{{font-size:1.4rem;font-weight:800;font-family:'Courier New',monospace}}
.s .l{{font-size:.64rem;color:#5c6478;margin-top:3px;text-transform:uppercase;letter-spacing:.5px}}
.s .x{{font-size:.58rem;color:#5c6478}}
.cd{{background:#13161f;border:1px solid #2a3042;border-radius:12px;padding:16px;margin-bottom:16px;overflow-x:auto}}
.cd h2{{font-size:.92rem;font-weight:700;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;font-size:.74rem}}
th{{background:#1a1e2a;color:#8b93a8;font-weight:700;text-transform:uppercase;font-size:.62rem;letter-spacing:.5px;padding:8px 6px;text-align:left;border-bottom:2px solid #2a3042;position:sticky;top:0}}
td{{padding:6px;border-bottom:1px solid #222736}}
tr:hover td{{background:rgba(240,182,52,.03)}}
tr.hit td{{background:rgba(45,212,160,.08)}}
.m{{font-family:'Courier New',monospace;font-weight:700;letter-spacing:2px}}
.b{{display:inline-block;padding:2px 7px;border-radius:5px;font-size:.66rem;font-weight:700}}
.bh{{background:rgba(45,212,160,.15);color:#2dd4a0}}
.bx{{background:rgba(240,86,74,.1);color:#f0564a}}
.bmd{{background:rgba(91,140,240,.1);color:#5b8cf0}}
.be{{background:rgba(167,139,250,.1);color:#a78bfa}}
.sy{{max-height:600px;overflow-y:auto}}
.tabs{{display:flex;gap:2px;margin-bottom:14px;background:#1a1e2a;border-radius:10px;padding:3px;border:1px solid #2a3042;flex-wrap:wrap}}
.tab{{padding:8px 14px;border-radius:8px;font-size:.74rem;font-weight:700;cursor:pointer;color:#5c6478;border:none;background:transparent}}
.tab:hover{{color:#e4e8f1}}.tab.active{{background:#f0b634;color:#0c0e14}}
.tc{{display:none}}.tc.active{{display:block}}
.yg{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}}
.yc{{padding:6px 12px;border-radius:8px;font-size:.72rem;font-weight:700;font-family:'Courier New',monospace;border:1px solid #2a3042;background:#1a1e2a}}
.rg{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}}
.rc{{padding:8px 14px;border-radius:8px;font-size:.78rem;font-weight:700;font-family:'Courier New',monospace;background:#1a1e2a;border:1px solid #2a3042;text-align:center}}
.rc .rv{{font-size:1.1rem;color:#f0b634}}.rc .rl{{font-size:.6rem;color:#5c6478;margin-top:2px}}
.ft{{margin-top:24px;text-align:center;font-size:.7rem;color:#5c6478;padding:16px}}
</style></head><body>
<div class="c">
<h1>🔬 Shadow Strategy — Viability Report</h1>
<div class="sub">Every draw tested as a target | API auto-selects seeds (shadow mode) | {start_ym} → {end_ym} | {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>

<div class="sg">
<div class="s"><div class="v" style="color:#5b8cf0">{tot}</div><div class="l">Draws Tested</div></div>
<div class="s"><div class="v" style="color:#2dd4a0">{hits}</div><div class="l">Hits</div></div>
<div class="s"><div class="v" style="color:#f0b634">{pct(hits,tot)}%</div><div class="l">Hit Rate</div></div>
<div class="s"><div class="v" style="color:#a78bfa">{avg_c:.0f}</div><div class="l">Avg Candidates</div></div>
<div class="s"><div class="v" style="color:#f09544">{avg_r:.0f}</div><div class="l">Avg Hit Rank</div></div>
<div class="s"><div class="v" style="color:#5b8cf0">{mid_h}/{len(mid_r)}</div><div class="l">Midday</div><div class="x">{pct(mid_h,len(mid_r))}%</div></div>
<div class="s"><div class="v" style="color:#a78bfa">{eve_h}/{len(eve_r)}</div><div class="l">Evening</div><div class="x">{pct(eve_h,len(eve_r))}%</div></div>
<div class="s"><div class="v" style="color:#f0564a">{max_dry}</div><div class="l">Max Dry Streak</div></div>
</div>

<!-- Rank distribution -->
<div class="cd"><h2>🎯 Hit Rank Distribution</h2>
<div class="rg">
"""
    for bucket, count in rank_buckets.items():
        html += f'<div class="rc"><div class="rv">{count}</div><div class="rl">Rank {bucket}</div></div>\n'
    html += '</div></div>\n'

    # Yearly
    html += '<div class="cd"><h2>📅 By Year</h2><div class="yg">\n'
    for y in sorted(yrs.keys()):
        ys = yrs[y]
        yp = (ys["h"] / ys["t"] * 100) if ys["t"] > 0 else 0
        col = "#2dd4a0" if yp > 2 else "#f0b634" if yp > 0 else "#5c6478"
        html += f'<div class="yc" style="color:{col};border-color:{col}33">{y} {ys["h"]}/{ys["t"]} ({yp:.1f}%)</div>\n'
    html += '</div></div>\n'

    # Tabs
    html += f'<div class="tabs">'
    html += f'<button class="tab active" onclick="sw(\'h\',this)">🏆 Hits ({hits})</button>'
    html += f'<button class="tab" onclick="sw(\'a\',this)">📋 All ({len(results)})</button>'
    html += f'<button class="tab" onclick="sw(\'m\',this)">📆 Monthly</button>'
    html += f'</div>\n'

    # Hits tab
    html += '<div class="tc active" id="tab-h">\n'
    html += '<div class="cd" style="border-left:3px solid #2dd4a0"><h2>🏆 Hits</h2>\n'
    if hr:
        html += '<div class="sy">' + _tbl(hr) + '</div>'
    else:
        html += '<div style="padding:30px;text-align:center;color:#5c6478">No hits found.</div>'
    html += '</div></div>\n'

    # All tab
    html += '<div class="tc" id="tab-a"><div class="cd"><h2>📋 All Draws</h2>\n'
    html += '<div class="sy">' + _tbl(results) + '</div></div></div>\n'

    # Monthly tab
    html += '<div class="tc" id="tab-m"><div class="cd"><h2>📆 Monthly Summary</h2>\n'
    html += '<table><thead><tr><th>Month</th><th>Draws</th><th>Hits</th><th>Rate</th></tr></thead><tbody>\n'
    for mo in sorted(mos.keys()):
        ms = mos[mo]
        mp = (ms["h"] / ms["t"] * 100) if ms["t"] > 0 else 0
        col = "#2dd4a0" if mp > 2 else "#f0b634" if mp > 0 else "#f0564a"
        html += f'<tr><td>{mo}</td><td>{ms["t"]}</td><td style="color:{col};font-weight:700">{ms["h"]}</td>'
        html += f'<td style="color:{col}">{mp:.1f}%</td></tr>\n'
    html += '</tbody></table></div></div>\n'

    html += f"""<div class="ft">{STATE} {GAME_TYPE} | shadow min≥{SHADOW['min_count']} dp=0 | {tot} draws {hits} hits ({pct(hits,tot)}%) | {errs} errors | {stats.get('runtime','?')}</div>
</div>
<script>function sw(id,b){{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));b.classList.add('active');document.getElementById('tab-'+id).classList.add('active')}}</script>
</body></html>"""

    with open(path, "w") as f:
        f.write(html)
    print(f"📊 Report: {path}")


def _tbl(rows):
    h = '<table><thead><tr><th>Date</th><th>TOD</th><th>Value</th><th>Seeds</th><th>Hot Mo.</th><th>Cand.</th><th>Rank</th><th>Result</th></tr></thead><tbody>\n'
    for r in rows:
        c = 'hit' if r['hit'] else ''
        bg = '<span class="b bh">✅</span>' if r['hit'] else '<span class="b bx">❌</span>'
        td = '<span class="b bmd">MID</span>' if r["tod"] == "midday" else '<span class="b be">EVE</span>'
        rk = f"#{r['rank']}/{r['candidates']}" if r['rank'] else f"—/{r['candidates']}"
        sv = r.get("seed_values", "").replace("|", ", ")
        if len(sv) > 30: sv = sv[:28] + "…"
        h += f'<tr class="{c}"><td>{r["date"]}</td><td>{td}</td><td class="m">{r["value"]}</td>'
        h += f'<td style="font-size:.65rem;color:#8b93a8">{sv}</td>'
        h += f'<td style="color:#5b8cf0;font-weight:700">{r["hot_months"]}</td>'
        h += f'<td>{r["candidates"]}</td><td class="m">{rk}</td><td>{bg}</td></tr>\n'
    h += '</tbody></table>\n'
    return h


# ── Main ───────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Shadow Strategy Viability Scanner")
    p.add_argument("--start", default="1990-01")
    p.add_argument("--end", default="2026-02")
    p.add_argument("--state", default="Florida")
    p.add_argument("--game", default="pick4")
    p.add_argument("--tod", default="both", choices=["midday", "evening", "both"])
    p.add_argument("--min-count", type=int, default=2)
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument("--output", default="shadow_viability")
    args = p.parse_args()

    global STATE, GAME_TYPE, DELAY
    STATE = args.state
    GAME_TYPE = args.game
    SHADOW["min_count"] = args.min_count
    DELAY = args.delay

    tods = ["midday", "evening"] if args.tod == "both" else [args.tod]

    print("=" * 64)
    print("  🔬 Shadow Strategy Viability Scanner")
    print("=" * 64)
    print(f"  State:    {STATE}")
    print(f"  Game:     {GAME_TYPE}")
    print(f"  Range:    {args.start} → {args.end}")
    print(f"  TODs:     {', '.join(tods)}")
    print(f"  Seeds:    Auto (API shadow mode)")
    print(f"  Min Hot:  ≥ {SHADOW['min_count']}")
    print(f"  API:      {BASE_URL}")
    print("=" * 64)

    # Test
    print("\n🔌 Testing API...", end="", flush=True)
    test = api_post("/api/draws/recent", {
        "state": STATE, "game_type": GAME_TYPE,
        "start_date": "2019-10-08", "end_date": "2019-10-09"
    })
    if not test:
        print(f"\n❌ Cannot reach {BASE_URL}")
        sys.exit(1)
    td = test.get("draws", [])
    print(f" ✓ ({len(td)} draws)")

    results = []
    stats = {"total": 0, "hits": 0, "errors": 0}
    t0 = time.time()

    months = list(month_range(args.start, args.end))
    N = len(months)
    print(f"\n📅 {N} months to scan\n")

    for mi, ym in enumerate(months):
        el = time.time() - t0
        eta = ""
        if mi > 2 and stats["total"] > 0:
            per_mo = el / (mi + 1)
            rem = per_mo * (N - mi - 1)
            eta = f" | ETA ~{rem/60:.0f}m" if rem > 60 else f" | ~{rem:.0f}s"

        print(f"[{mi+1}/{N}] ({mi*100//N}%) 📆 {ym} | {stats['hits']}/{stats['total']} hits{eta}")

        try:
            scan_month(ym, results, stats, tods)
        except KeyboardInterrupt:
            print("\n⚡ Interrupted — saving...")
            break
        except Exception as e:
            print(f"  ⚠ {ym}: {e}")
            stats["errors"] += 1

        time.sleep(BATCH_DELAY)

        if (mi + 1) % AUTOSAVE_EVERY == 0 and results:
            stats["runtime"] = f"{time.time()-t0:.0f}s"
            write_csv(results, f"{args.output}_partial.csv")
            print(f"  💾 Auto-saved ({len(results)} rows, {stats['hits']} hits)")

    elapsed = time.time() - t0
    stats["runtime"] = f"{elapsed:.0f}s ({elapsed/60:.1f}min)"

    print("\n" + "=" * 64)
    if stats["total"] > 0:
        print(f"  ✅ {stats['total']} draws, {stats['hits']} hits ({stats['hits']/stats['total']*100:.2f}%)")
    else:
        print("  ✅ 0 draws tested")
    print(f"  ⏱  {elapsed:.0f}s ({elapsed/60:.1f}min) | Errors: {stats['errors']}")
    print("=" * 64)

    write_csv(results, f"{args.output}.csv")
    write_report(results, stats, f"{args.output}.html", args.start, args.end)

    partial = f"{args.output}_partial.csv"
    if os.path.exists(partial):
        os.remove(partial)

    print(f"\n🎯 Open {args.output}.html to view results.")


if __name__ == "__main__":
    main()
