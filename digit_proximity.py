#!/usr/bin/env python3
"""
================================================================
  Digit Proximity & Nudge Theory Scanner
================================================================
  Tests: does the next draw tend to be a "nudge" (±1, ±2, etc.)
  away from the previous draw, digit by digit on a 0-9 wheel?

  Two comparison modes tested simultaneously:
    POSITIONAL: Compare digit-by-digit in drawn order
                1792 vs 2897 → [1v2, 7v8, 9v9, 2v7]
    SORTED:     Sort both ascending, then compare
                1279 vs 2789 → [1v2, 2v7, 7v8, 9v9]

  Three relationship types:
    PREV1:   Previous draw → Current draw (sequential)
    PREV2:   Two draws ago → Current draw
    BEST:    Whichever of prev1/prev2 is closest
    SAMEDAY: Same-day midday → evening

  Nudge analysis at every distance (±1 through ±5).

  USAGE:
    python digit_proximity.py
    python digit_proximity.py --start 2019-01 --end 2019-12
================================================================
"""

import argparse
import json
import csv
import sys
import os
import time
from datetime import datetime, timedelta
from calendar import monthrange
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from collections import defaultdict
import random

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"
STATE = "Florida"
GAME_TYPE = "pick4"
DELAY = 0.05


# ── API ────────────────────────────────────────────────────────
def api_post(path, body):
    sep = "&" if "?" in path else "?"
    url = f"{BASE_URL}{path}{sep}db={DB_MODE}"
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def fetch_draws(s, e):
    d = api_post("/api/draws/recent", {"state": STATE, "game_type": GAME_TYPE,
                                        "start_date": s, "end_date": e})
    return d.get("draws", []) if d else []


# ── Digit Math ─────────────────────────────────────────────────
def circ_dist(a, b):
    """Shortest distance on 0-9 circle."""
    d = abs(int(a) - int(b))
    return min(d, 10 - d)

def analyze_pair(seed_val, target_val):
    """
    Full analysis of one seed→target pair.
    Returns dict with both positional and sorted metrics.
    """
    s = str(seed_val).zfill(4)
    t = str(target_val).zfill(4)
    ss = "".join(sorted(s))
    ts = "".join(sorted(t))

    result = {}
    for mode, a, b in [("pos", s, t), ("srt", ss, ts)]:
        dists = [circ_dist(a[i], b[i]) for i in range(4)]
        nudge_counts = {}  # how many digits have distance exactly X
        for nd in range(6):  # 0 through 5
            nudge_counts[nd] = sum(1 for d in dists if d == nd)

        result[f"{mode}_dists"] = dists
        result[f"{mode}_total"] = sum(dists)
        result[f"{mode}_max"] = max(dists)
        result[f"{mode}_changed"] = sum(1 for d in dists if d > 0)
        result[f"{mode}_held"] = sum(1 for d in dists if d == 0)
        result[f"{mode}_nudge_counts"] = nudge_counts  # {0:2, 1:1, 2:0, ...}

        # Key metrics for the theory
        result[f"{mode}_n1"] = nudge_counts.get(1, 0)  # digits that moved ±1
        result[f"{mode}_n2"] = nudge_counts.get(2, 0)  # digits that moved ±2
        result[f"{mode}_n12"] = nudge_counts.get(1, 0) + nudge_counts.get(2, 0)  # ±1 or ±2

    return result


# ── Random Baseline ────────────────────────────────────────────
def compute_random_baseline(n_trials=500000):
    """
    Monte Carlo: generate random pairs and compute same metrics.
    Returns expected distributions.
    """
    print("🎲 Computing random baseline (500k trials)...", end="", flush=True)
    stats = {
        "pos_total": defaultdict(int),
        "srt_total": defaultdict(int),
        "pos_changed": defaultdict(int),
        "srt_changed": defaultdict(int),
        "pos_n1": defaultdict(int),
        "srt_n1": defaultdict(int),
        "pos_n12": defaultdict(int),
        "srt_n12": defaultdict(int),
    }

    for _ in range(n_trials):
        a = f"{random.randint(0,9999):04d}"
        b = f"{random.randint(0,9999):04d}"
        r = analyze_pair(a, b)
        for mode in ["pos", "srt"]:
            stats[f"{mode}_total"][r[f"{mode}_total"]] += 1
            stats[f"{mode}_changed"][r[f"{mode}_changed"]] += 1
            stats[f"{mode}_n1"][r[f"{mode}_n1"]] += 1
            stats[f"{mode}_n12"][r[f"{mode}_n12"]] += 1

    # Normalize to percentages
    base = {}
    for key, dist in stats.items():
        base[key] = {k: v / n_trials * 100 for k, v in sorted(dist.items())}
    print(" ✓")
    return base


# ── Date/Month Helpers ─────────────────────────────────────────
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


# ── Scan ───────────────────────────────────────────────────────
def load_all_draws(start_ym, end_ym):
    print("📥 Loading draws...", flush=True)
    all_d = []
    months = list(month_range(start_ym, end_ym))
    for mi, ym in enumerate(months):
        s, e = month_bounds(ym)
        all_d.extend(fetch_draws(s, e))
        if (mi + 1) % 24 == 0 or mi == len(months) - 1:
            print(f"  {ym} — {len(all_d):,} draws")
        time.sleep(DELAY)

    tod_ord = {"midday": 0, "evening": 1}
    all_d.sort(key=lambda d: (
        d.get("date", ""),
        tod_ord.get((d.get("tod") or d.get("draw_time", "")).lower(), 2)
    ))
    print(f"✅ {len(all_d):,} draws loaded\n")
    return all_d


def analyze_draws(draws):
    """Analyze all consecutive pairs + same-day mid→eve."""
    results = []
    sameday = []

    # Group by date for same-day analysis
    by_date = defaultdict(dict)
    for d in draws:
        dt = d.get("date", "")
        tod = (d.get("tod") or d.get("draw_time", "")).lower()
        by_date[dt][tod] = d.get("value", "")

    # Same-day midday→evening
    print("🔄 Analyzing same-day mid→eve pairs...")
    for dt in sorted(by_date.keys()):
        mid = by_date[dt].get("midday", "")
        eve = by_date[dt].get("evening", "")
        if mid and eve and len(mid) == 4 and len(eve) == 4:
            a = analyze_pair(mid, eve)
            a["date"] = dt
            a["seed"] = mid
            a["seed_tod"] = "midday"
            a["target"] = eve
            a["target_tod"] = "evening"
            a["rel"] = "sameday"
            sameday.append(a)

    # Sequential: every draw vs prev1 and prev2
    print("🔗 Analyzing sequential pairs...")
    for i in range(1, len(draws)):
        cur = draws[i]
        p1 = draws[i - 1]
        p2 = draws[i - 2] if i >= 2 else None

        cv = cur.get("value", "")
        p1v = p1.get("value", "")
        p2v = p2.get("value", "") if p2 else ""
        cdate = cur.get("date", "")
        ctod = (cur.get("tod") or cur.get("draw_time", "")).lower()

        if not cv or len(cv) != 4 or not p1v or len(p1v) != 4:
            continue

        # Prev1
        a1 = analyze_pair(p1v, cv)
        a1["date"] = cdate
        a1["tod"] = ctod
        a1["target"] = cv
        a1["seed"] = p1v
        a1["seed_tod"] = (p1.get("tod") or "").lower()
        a1["seed_date"] = p1.get("date", "")

        # Prev2 + Best
        if p2v and len(p2v) == 4:
            a2 = analyze_pair(p2v, cv)
            # Pick best by: fewer changed digits (pos mode), then lower total
            if (a2["pos_changed"], a2["pos_total"]) < (a1["pos_changed"], a1["pos_total"]):
                best = {**a2, "best_from": "prev2", "best_seed": p2v}
            else:
                best = {**a1, "best_from": "prev1", "best_seed": p1v}
            a1["p2_seed"] = p2v
            a1["p2_pos_total"] = a2["pos_total"]
            a1["p2_srt_total"] = a2["srt_total"]
            a1["p2_pos_n1"] = a2["pos_n1"]
            a1["p2_srt_n1"] = a2["srt_n1"]
            a1["best_from"] = best["best_from"]
            a1["best_seed"] = best["best_seed"]
            a1["best_pos_total"] = best["pos_total"]
            a1["best_srt_total"] = best["srt_total"]
            a1["best_pos_n1"] = best["pos_n1"]
            a1["best_srt_n1"] = best["srt_n1"]
            a1["best_pos_changed"] = best["pos_changed"]
            a1["best_srt_changed"] = best["srt_changed"]
        else:
            a1["p2_seed"] = ""
            a1["best_from"] = "prev1"
            a1["best_seed"] = p1v
            for k in ["best_pos_total","best_srt_total","best_pos_n1","best_srt_n1","best_pos_changed","best_srt_changed"]:
                a1[k] = a1[k.replace("best_","")]

        results.append(a1)

    print(f"📊 {len(results):,} sequential pairs, {len(sameday):,} same-day pairs\n")

    # Print draw log to console
    print("─" * 90)
    print(f" {'Date':<12} {'TOD':<4} {'Prev':>6}  →  {'Drawn':>6}  {'Pos Dists':<12} {'Σ':>3}  {'Srt Dists':<12} {'Σ':>3}  {'±1':>3} {'Held':>4}")
    print("─" * 90)
    for r in results:
        pd = " ".join(str(d) for d in r["pos_dists"])
        sd = " ".join(str(d) for d in r["srt_dists"])
        marker = " ✨" if r["pos_n1"] >= 3 else " ⭐" if r["pos_n1"] >= 2 else ""
        print(f" {r['date']:<12} {r.get('tod','')[:3]:<4} {r['seed']:>6}  →  {r['target']:>6}  [{pd}]  {r['pos_total']:>3}  [{sd}]  {r['srt_total']:>3}  {r['pos_n1']:>3} {r['pos_held']:>4}{marker}")
    print("─" * 90)

    if sameday:
        print(f"\n☀️🌙 Same-Day Midday → Evening:")
        print("─" * 70)
        for r in sameday:
            pd = " ".join(str(d) for d in r["pos_dists"])
            marker = " ✨" if r["pos_n1"] >= 3 else " ⭐" if r["pos_n1"] >= 2 else ""
            print(f" {r['date']:<12} {r['seed']:>6} → {r['target']:>6}  [{pd}]  Σ={r['pos_total']:>2}  ±1={r['pos_n1']}{marker}")
        print("─" * 70)

    print()
    return results, sameday


# ── Stats ──────────────────────────────────────────────────────
def dist_of(results, key):
    d = defaultdict(int)
    for r in results:
        d[r[key]] += 1
    return dict(sorted(d.items()))

def avg_of(results, key):
    vals = [r[key] for r in results]
    return sum(vals) / len(vals) if vals else 0


# ── Report ─────────────────────────────────────────────────────
def write_report(results, sameday, baseline, filepath, start_ym, end_ym):
    n = len(results)
    ns = len(sameday)

    def p(v, d): return f"{v/d*100:.2f}" if d > 0 else "0"
    def p1(v, d): return f"{v/d*100:.1f}" if d > 0 else "0"

    # ── Precompute stats ──
    S = {}
    for mode in ["pos", "srt"]:
        S[f"{mode}_avg_total"] = avg_of(results, f"{mode}_total")
        S[f"{mode}_avg_n1"] = avg_of(results, f"{mode}_n1")
        S[f"{mode}_total_dist"] = dist_of(results, f"{mode}_total")
        S[f"{mode}_changed_dist"] = dist_of(results, f"{mode}_changed")
        S[f"{mode}_n1_dist"] = dist_of(results, f"{mode}_n1")
        S[f"{mode}_n12_dist"] = dist_of(results, f"{mode}_n12")

        # Nudge breakdown: for each nudge distance 0-5, count avg occurrences
        for nd in range(6):
            vals = [r[f"{mode}_nudge_counts"][nd] for r in results]
            S[f"{mode}_nudge{nd}_avg"] = sum(vals) / len(vals) if vals else 0
            S[f"{mode}_nudge{nd}_dist"] = defaultdict(int)
            for v in vals:
                S[f"{mode}_nudge{nd}_dist"][v] += 1

    # Same-day stats
    SD = {}
    for mode in ["pos", "srt"]:
        SD[f"{mode}_avg_total"] = avg_of(sameday, f"{mode}_total") if sameday else 0
        SD[f"{mode}_avg_n1"] = avg_of(sameday, f"{mode}_n1") if sameday else 0
        SD[f"{mode}_n1_dist"] = dist_of(sameday, f"{mode}_n1") if sameday else {}

    # Best-of-both
    B = {}
    B["pos_avg_total"] = avg_of(results, "best_pos_total")
    B["srt_avg_total"] = avg_of(results, "best_srt_total")
    B["pos_avg_n1"] = avg_of(results, "best_pos_n1")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Digit Nudge Theory — {start_ym} to {end_ym}</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=DM+Sans:ital,wght@0,400;0,500;0,700;0,800;1,400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'DM Sans',sans-serif;background:#07080c;color:#dde1ec;padding:20px;line-height:1.6}}
.c{{max-width:1300px;margin:0 auto}}
h1{{font-family:'JetBrains Mono',monospace;font-size:1.5rem;font-weight:800;color:#f0b634;margin-bottom:4px}}
h2{{font-size:.95rem;font-weight:700;margin-bottom:12px;color:#c0c5d4}}
h3{{font-size:.78rem;font-weight:700;color:#6b7390;text-transform:uppercase;letter-spacing:.6px;margin:14px 0 8px}}
.sub{{font-size:.78rem;color:#4d5570;margin-bottom:24px}}
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:24px}}
.hc{{background:linear-gradient(135deg,#10121a,#161a26);border:1px solid #232840;border-radius:12px;padding:16px;text-align:center}}
.hc .v{{font-family:'JetBrains Mono',monospace;font-size:1.6rem;font-weight:800}}
.hc .l{{font-size:.6rem;color:#4d5570;margin-top:3px;text-transform:uppercase;letter-spacing:.7px}}
.hc .x{{font-size:.62rem;color:#4d5570;margin-top:2px}}
.card{{background:#0e1018;border:1px solid #1e2236;border-radius:12px;padding:18px;margin-bottom:14px}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:800px){{.g2{{grid-template-columns:1fr}}}}
table{{width:100%;border-collapse:collapse;font-size:.72rem}}
th{{background:#141722;color:#4d5570;font-weight:700;font-size:.58rem;letter-spacing:.5px;text-transform:uppercase;padding:8px 6px;text-align:left;border-bottom:2px solid #1e2236}}
td{{padding:6px;border-bottom:1px solid #181c2a}}
tr:hover td{{background:rgba(240,182,52,.02)}}
.mono{{font-family:'JetBrains Mono',monospace;font-weight:700;letter-spacing:2px}}
.gr{{color:#2dd4a0}}.ye{{color:#f0b634}}.or{{color:#f09544}}.re{{color:#f0564a}}.bl{{color:#5b8cf0}}.pu{{color:#a78bfa}}
.b{{display:inline-block;padding:2px 6px;border-radius:4px;font-size:.62rem;font-weight:700}}
.bg{{background:#2dd4a022;color:#2dd4a0}}.by{{background:#f0b63422;color:#f0b634}}.br{{background:#f0564a22;color:#f0564a}}
.dial{{display:inline-flex;gap:2px}}
.dd{{width:22px;height:22px;border-radius:5px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:.68rem;font-family:'JetBrains Mono',monospace}}
.d0{{background:#2dd4a033;color:#2dd4a0}}.d1{{background:#5bf0c833;color:#5bf0c8}}.d2{{background:#f0b63433;color:#f0b634}}.d3{{background:#f0954433;color:#f09544}}.d4{{background:#f0564a33;color:#f0564a}}.d5{{background:#e0304033;color:#e03040}}
.bar-bg{{background:#141722;border-radius:3px;height:18px;position:relative;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px;transition:width .3s}}
.bar-label{{position:absolute;right:4px;top:1px;font-size:.58rem;color:#dde1ec;font-family:'JetBrains Mono',monospace}}
.tabs{{display:flex;gap:2px;margin-bottom:14px;background:#141722;border-radius:10px;padding:3px;border:1px solid #1e2236;flex-wrap:wrap}}
.tab{{padding:7px 13px;border-radius:8px;font-size:.72rem;font-weight:700;cursor:pointer;color:#4d5570;border:none;background:transparent;font-family:'DM Sans',sans-serif}}
.tab:hover{{color:#dde1ec}}.tab.active{{background:#f0b634;color:#07080c}}
.tc{{display:none}}.tc.active{{display:block}}
.sy{{max-height:500px;overflow-y:auto}}
.cmp-row{{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid #181c2a;font-size:.78rem}}
.cmp-label{{width:160px;color:#6b7390;font-weight:600;font-size:.72rem}}
.cmp-val{{font-family:'JetBrains Mono',monospace;font-weight:700;min-width:70px}}
.cmp-bar{{flex:1;height:6px;background:#141722;border-radius:3px;overflow:hidden}}
.cmp-fill{{height:100%;border-radius:3px}}
.note{{font-size:.68rem;color:#4d5570;margin-top:8px;font-style:italic}}
.ft{{margin-top:24px;text-align:center;font-size:.66rem;color:#2a3050;padding:16px}}
.verdict{{border-left:3px solid;padding:16px;margin-bottom:18px;border-radius:0 12px 12px 0}}
</style></head><body>
<div class="c">
<h1>🎰 Digit Nudge Theory</h1>
<div class="sub">Are consecutive draws "nudges" of each other? {n:,} sequential pairs + {ns:,} same-day pairs | {start_ym} → {end_ym}</div>
"""

    # ── Hero Stats ──
    html += '<div class="hero">\n'
    for label, actual, rand_key, color in [
        ("Avg Distance (positional)", f"{S['pos_avg_total']:.2f}", "pos_total", "#5b8cf0"),
        ("Avg Distance (sorted)", f"{S['srt_avg_total']:.2f}", "srt_total", "#a78bfa"),
        ("Random Expected", "10.00", None, "#4d5570"),
        ("Avg ±1 Nudges/draw (pos)", f"{S['pos_avg_n1']:.2f}", None, "#2dd4a0"),
        ("Avg ±1 Nudges/draw (srt)", f"{S['srt_avg_n1']:.2f}", None, "#5bf0c8"),
        ("Random ±1 Expected", "0.80", None, "#4d5570"),
    ]:
        html += f'<div class="hc"><div class="v" style="color:{color}">{actual}</div><div class="l">{label}</div></div>\n'
    html += '</div>\n'

    # ── Verdict ──
    pos_ratio = S['pos_avg_total'] / 10.0
    n1_ratio = S['pos_avg_n1'] / 0.8  # random expected ~0.8 nudges per draw

    if n1_ratio > 1.3:
        verdict_text = "🟢 STRONG NUDGE SIGNAL — significantly more ±1 nudges than random"
        vcolor = "#2dd4a0"
    elif n1_ratio > 1.1:
        verdict_text = "🟡 MILD NUDGE SIGNAL — somewhat elevated ±1 nudges"
        vcolor = "#f0b634"
    elif pos_ratio < 0.92:
        verdict_text = "🟡 PROXIMITY SIGNAL — draws are closer than random, but not specifically ±1"
        vcolor = "#f0b634"
    else:
        verdict_text = "🔴 NO SIGNAL — nudge rates match random expectation"
        vcolor = "#f0564a"

    html += f'<div class="card verdict" style="border-color:{vcolor}">\n'
    html += f'<h2 style="color:{vcolor}">{verdict_text}</h2>\n'
    html += f'<div style="font-size:.82rem;color:#8b93a8;margin-top:8px">'
    html += f'Distance ratio: <strong>{pos_ratio:.3f}</strong> (1.0 = random). '
    html += f'±1 nudge ratio: <strong>{n1_ratio:.3f}</strong> (1.0 = random). '
    html += f'Same-day mid→eve avg: <strong>{SD["pos_avg_total"]:.2f}</strong> distance, '
    html += f'<strong>{SD["pos_avg_n1"]:.2f}</strong> ±1 nudges/pair.'
    html += f'</div></div>\n'

    # ── Tabs ──
    html += '<div class="tabs">'
    html += '<button class="tab active" onclick="sw(\'nudge\',this)">🎯 Nudge Counts</button>'
    html += '<button class="tab" onclick="sw(\'dist\',this)">📊 Distance</button>'
    html += '<button class="tab" onclick="sw(\'cmp\',this)">⚔️ Pos vs Sorted</button>'
    html += '<button class="tab" onclick="sw(\'sd\',this)">☀️🌙 Same-Day</button>'
    html += '<button class="tab" onclick="sw(\'best\',this)">🏆 Best Matches</button>'
    html += '<button class="tab" onclick="sw(\'heat\',this)">🔥 Heatmap</button>'
    html += '<button class="tab" onclick="sw(\'log\',this)">📜 Draw Log</button>'
    html += '</div>\n'

    # ═══ TAB: NUDGE COUNTS ═══
    html += '<div class="tc active" id="tab-nudge">\n'
    html += '<div class="card"><h2>🎯 How Many Digits Moved By Each Distance?</h2>\n'
    html += '<div style="font-size:.78rem;color:#6b7390;margin-bottom:14px">For each draw pair, we count how many of the 4 digits moved by exactly ±1, ±2, etc. Then we average across all pairs and compare to random.</div>\n'

    html += '<div class="g2">\n'
    for mode, label in [("pos", "Positional"), ("srt", "Sorted")]:
        html += f'<div><h3>{label} Comparison</h3>'
        html += '<table><thead><tr><th>Nudge ±</th><th>Avg/Draw</th><th>Random</th><th>Ratio</th><th>0 digits</th><th>1 digit</th><th>2 digits</th><th>3 digits</th><th>4 digits</th></tr></thead><tbody>\n'

        # Random expected: P(digit distance = d) on 0-9 circle
        # d=0: 1/10, d=1: 2/10, d=2: 2/10, d=3: 2/10, d=4: 2/10, d=5: 1/10
        # Expected count of digits with distance=d in 4 digits = 4 * P(d)
        rand_per_digit = {0: 0.1, 1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.1}
        rand_expected_4 = {d: 4 * p for d, p in rand_per_digit.items()}

        for nd in range(6):
            avg = S[f"{mode}_nudge{nd}_avg"]
            rnd = rand_expected_4[nd]
            ratio = avg / rnd if rnd > 0 else 0
            col = "#2dd4a0" if ratio > 1.2 else "#f0b634" if ratio > 1.05 else "#f0564a" if ratio < 0.9 else "#6b7390"

            # Distribution: how many draws had 0,1,2,3,4 digits at this distance
            dd = S[f"{mode}_nudge{nd}_dist"]
            cells = ""
            for cnt in range(5):
                c = dd.get(cnt, 0)
                pct_v = c / n * 100 if n else 0
                cells += f'<td>{pct_v:.1f}%</td>'

            dist_label = "held" if nd == 0 else f"±{nd}"
            html += f'<tr><td style="font-weight:700;color:{col}">{dist_label}</td>'
            html += f'<td class="mono" style="color:{col}">{avg:.3f}</td>'
            html += f'<td style="color:#4d5570">{rnd:.2f}</td>'
            html += f'<td style="color:{col};font-weight:700">{ratio:.3f}x</td>'
            html += f'{cells}</tr>\n'

        html += '</tbody></table></div>\n'
    html += '</div>\n'

    # Top nudge examples
    html += '<h3>Top ±1 Nudge Examples (Positional)</h3>\n'
    top_n1 = sorted(results, key=lambda r: (-r["pos_n1"], r["pos_total"]))[:20]
    html += '<table><thead><tr><th>Date</th><th>TOD</th><th>Previous</th><th>→</th><th>Drawn</th><th>Pos Dists</th><th>±1 Count</th><th>Total</th></tr></thead><tbody>\n'
    for r in top_n1:
        pd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["pos_dists"])
        html += f'<tr><td>{r["date"]}</td><td>{r.get("tod","")[:3]}</td>'
        html += f'<td class="mono" style="color:#6b7390">{r["seed"]}</td>'
        html += f'<td style="color:#4d5570">→</td>'
        html += f'<td class="mono gr">{r["target"]}</td>'
        html += f'<td><div class="dial">{pd}</div></td>'
        html += f'<td class="mono ye">{r["pos_n1"]}</td>'
        html += f'<td class="mono">{r["pos_total"]}</td></tr>\n'
    html += '</tbody></table>\n'

    html += '</div></div>\n'

    # ═══ TAB: DISTANCE ═══
    html += '<div class="tc" id="tab-dist"><div class="g2">\n'
    for mode, label in [("pos", "Positional"), ("srt", "Sorted")]:
        html += f'<div class="card"><h2>Total Distance — {label}</h2>\n'
        html += '<table><thead><tr><th>Dist</th><th>Count</th><th>Actual%</th><th>Random%</th><th>Ratio</th><th></th></tr></thead><tbody>\n'
        dist = S[f"{mode}_total_dist"]
        bline = baseline.get(f"{mode}_total", {})
        mx = max(dist.values()) if dist else 1
        for d in sorted(dist.keys()):
            c = dist[d]
            ap = c / n * 100
            rp = bline.get(d, 0)
            ratio = ap / rp if rp > 0.01 else 0
            col = "#2dd4a0" if ratio > 1.3 else "#f0b634" if ratio > 1.1 else "#6b7390"
            w = c / mx * 100
            html += f'<tr><td style="font-weight:700">{d}</td><td>{c:,}</td>'
            html += f'<td style="font-weight:700">{ap:.2f}%</td><td style="color:#4d5570">{rp:.2f}%</td>'
            html += f'<td style="color:{col};font-weight:700">{ratio:.2f}x</td>'
            html += f'<td style="width:30%"><div class="bar-bg"><div class="bar-fill" style="width:{w:.1f}%;background:{col}"></div><div class="bar-label">{c:,}</div></div></td></tr>\n'
        html += '</tbody></table></div>\n'
    html += '</div></div>\n'

    # ═══ TAB: POS vs SORTED ═══
    html += '<div class="tc" id="tab-cmp"><div class="card"><h2>⚔️ Positional vs Sorted Comparison</h2>\n'
    html += '<div style="font-size:.78rem;color:#6b7390;margin-bottom:14px">"Positional" compares digits in drawn order. "Sorted" sorts both numbers ascending first. If sorted is significantly better, digit order doesn\'t matter and it\'s the digit POOL that clusters.</div>\n'
    html += '<table><thead><tr><th>Metric</th><th>Positional</th><th>Sorted</th><th>Winner</th></tr></thead><tbody>\n'

    comparisons = [
        ("Avg Total Distance", S["pos_avg_total"], S["srt_avg_total"], True),
        ("Avg ±1 Nudges", S["pos_avg_n1"], S["srt_avg_n1"], False),
        ("Avg ±1+±2 Nudges", avg_of(results, "pos_n12"), avg_of(results, "srt_n12"), False),
    ]
    for label, pv, sv, lower_wins in comparisons:
        if lower_wins:
            winner = "POS" if pv < sv else "SORT" if sv < pv else "TIE"
        else:
            winner = "POS" if pv > sv else "SORT" if sv > pv else "TIE"
        wcol = "#5b8cf0" if winner == "POS" else "#a78bfa" if winner == "SORT" else "#6b7390"
        html += f'<tr><td style="font-weight:700">{label}</td>'
        html += f'<td class="mono">{pv:.3f}</td><td class="mono">{sv:.3f}</td>'
        html += f'<td style="color:{wcol};font-weight:700">{winner}</td></tr>\n'

    # Digits changed
    for ch in range(5):
        pc = S["pos_changed_dist"].get(ch, 0)
        sc = S["srt_changed_dist"].get(ch, 0)
        html += f'<tr><td>{ch} digits changed</td><td>{p(pc,n)}%</td><td>{p(sc,n)}%</td><td></td></tr>\n'

    html += '</tbody></table>\n'

    # Show examples where pos vs sorted differ most
    html += '<h3>Examples: Biggest Pos vs Sorted Difference</h3>\n'
    diff_examples = sorted(results, key=lambda r: abs(r["pos_total"] - r["srt_total"]), reverse=True)[:15]
    html += '<table><thead><tr><th>Date</th><th>TOD</th><th>Prev</th><th>→</th><th>Drawn</th><th>Pos Dists</th><th>Pos Σ</th><th>Srt Dists</th><th>Srt Σ</th><th>Diff</th></tr></thead><tbody>\n'
    for r in diff_examples:
        pd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["pos_dists"])
        sd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["srt_dists"])
        diff = r["pos_total"] - r["srt_total"]
        dcol = "#2dd4a0" if diff > 0 else "#f0564a" if diff < 0 else "#6b7390"
        html += f'<tr><td>{r["date"]}</td><td>{r.get("tod","")[:3]}</td>'
        html += f'<td class="mono" style="color:#6b7390">{r["seed"]}</td><td style="color:#4d5570">→</td>'
        html += f'<td class="mono gr">{r["target"]}</td>'
        html += f'<td><div class="dial">{pd}</div></td><td class="mono bl">{r["pos_total"]}</td>'
        html += f'<td><div class="dial">{sd}</div></td><td class="mono pu">{r["srt_total"]}</td>'
        html += f'<td class="mono" style="color:{dcol}">{diff:+d}</td></tr>\n'
    html += '</tbody></table>\n'

    html += '</div></div>\n'
    html += '<div class="tc" id="tab-sd"><div class="card"><h2>☀️🌙 Same-Day Midday → Evening</h2>\n'
    html += f'<div style="font-size:.78rem;color:#6b7390;margin-bottom:14px">{ns:,} same-day pairs analyzed. Does the evening draw nudge from the midday draw more than sequential draws?</div>\n'

    if sameday:
        html += '<table><thead><tr><th>Metric</th><th>Same-Day M→E</th><th>Sequential (all)</th><th>Random</th></tr></thead><tbody>\n'
        sd_metrics = [
            ("Avg Distance (pos)", f'{SD["pos_avg_total"]:.3f}', f'{S["pos_avg_total"]:.3f}', "10.000"),
            ("Avg Distance (srt)", f'{SD["srt_avg_total"]:.3f}', f'{S["srt_avg_total"]:.3f}', "10.000"),
            ("Avg ±1 Nudges (pos)", f'{SD["pos_avg_n1"]:.3f}', f'{S["pos_avg_n1"]:.3f}', "0.800"),
            ("Avg ±1 Nudges (srt)", f'{SD["srt_avg_n1"]:.3f}', f'{S["srt_avg_n1"]:.3f}', "0.800"),
        ]
        for label, sd_v, seq_v, rand_v in sd_metrics:
            html += f'<tr><td style="font-weight:700">{label}</td><td class="mono ye">{sd_v}</td><td class="mono bl">{seq_v}</td><td class="mono" style="color:#4d5570">{rand_v}</td></tr>\n'

        html += '</tbody></table>\n'

        # Show some same-day examples with ±1 nudges
        good_sd = sorted(sameday, key=lambda r: (-r["pos_n1"], r["pos_total"]))[:30]
        if good_sd:
            html += '<h3>Top Same-Day Nudge Matches</h3><div class="sy"><table><thead><tr><th>Date</th><th>Midday</th><th>→</th><th>Evening</th><th>Pos Dists</th><th>Srt Dists</th><th>±1 (pos)</th><th>Total</th></tr></thead><tbody>\n'
            for r in good_sd:
                pd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["pos_dists"])
                sd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["srt_dists"])
                html += f'<tr><td>{r["date"]}</td><td class="mono">{r["seed"]}</td><td style="color:#4d5570">→</td>'
                html += f'<td class="mono gr">{r["target"]}</td><td><div class="dial">{pd}</div></td>'
                html += f'<td><div class="dial">{sd}</div></td><td class="mono ye">{r["pos_n1"]}</td>'
                html += f'<td class="mono">{r["pos_total"]}</td></tr>\n'
            html += '</tbody></table></div>\n'
    html += '</div></div>\n'

    # ═══ TAB: BEST MATCHES ═══
    html += '<div class="tc" id="tab-best"><div class="card"><h2>🏆 Closest Sequential Matches</h2>\n'
    html += '<div style="font-size:.78rem;color:#6b7390;margin-bottom:14px">Draws where the previous draw was very close (total distance ≤ 4, positional).</div>\n'

    close = sorted([r for r in results if r["pos_total"] <= 4], key=lambda r: (r["pos_total"], -r["pos_n1"]))
    html += f'<div style="margin-bottom:10px;font-size:.82rem"><strong class="ye">{len(close):,}</strong> draws within distance ≤ 4 ({p1(len(close),n)}%)</div>\n'

    if close:
        html += '<div class="sy"><table><thead><tr><th>Date</th><th>TOD</th><th>Seed</th><th>→</th><th>Drawn</th><th>Positional</th><th>Sorted</th><th>±1</th><th>Total</th></tr></thead><tbody>\n'
        for r in close[:300]:
            pd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["pos_dists"])
            sd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["srt_dists"])
            html += f'<tr><td>{r["date"]}</td><td>{r["tod"][:3]}</td>'
            html += f'<td class="mono">{r["seed"]}</td><td style="color:#4d5570">→</td>'
            html += f'<td class="mono gr">{r["target"]}</td>'
            html += f'<td><div class="dial">{pd}</div></td><td><div class="dial">{sd}</div></td>'
            html += f'<td class="mono ye">{r["pos_n1"]}</td><td class="mono">{r["pos_total"]}</td></tr>\n'
        html += '</tbody></table></div>\n'
    html += '</div></div>\n'

    # ═══ TAB: HEATMAP ═══
    html += '<div class="tc" id="tab-heat"><div class="card"><h2>🔥 Nudge Distance Heatmap By Position</h2>\n'
    html += '<div style="font-size:.78rem;color:#6b7390;margin-bottom:14px">What % of draws have digit N at distance D from the previous draw? Positional comparison.</div>\n'

    html += '<table><thead><tr><th>Distance</th><th>Digit 1 (thousands)</th><th>Digit 2 (hundreds)</th><th>Digit 3 (tens)</th><th>Digit 4 (ones)</th><th>Random</th></tr></thead><tbody>\n'
    rand_pct = {0: 10.0, 1: 20.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 10.0}
    for d in range(6):
        html += f'<tr><td style="font-weight:700">{"held" if d == 0 else f"±{d}"}</td>'
        for pos in range(4):
            count = sum(1 for r in results if r["pos_dists"][pos] == d)
            pv = count / n * 100 if n else 0
            rp = rand_pct[d]
            ratio = pv / rp if rp > 0 else 0
            # Color intensity based on deviation from random
            if ratio > 1.15:
                bg = f"rgba(45,212,160,{min((ratio-1)*2, 0.5):.2f})"
            elif ratio < 0.85:
                bg = f"rgba(240,86,74,{min((1-ratio)*2, 0.5):.2f})"
            else:
                bg = "transparent"
            html += f'<td style="background:{bg};text-align:center;font-family:JetBrains Mono,monospace;font-weight:700;font-size:.72rem">{pv:.1f}%</td>'
        html += f'<td style="color:#4d5570;text-align:center">{rand_pct[d]:.0f}%</td></tr>\n'
    html += '</tbody></table></div></div>\n'

    # ═══ TAB: CHRONOLOGICAL LOG ═══
    html += '<div class="tc" id="tab-log"><div class="card"><h2>📜 Chronological Draw Log</h2>\n'
    html += '<div style="font-size:.78rem;color:#6b7390;margin-bottom:14px">Every draw in sequence with nudge dials showing distance from the previous draw. Both positional and sorted comparisons shown.</div>\n'
    html += '<div class="sy" style="max-height:700px"><table><thead><tr><th>#</th><th>Date</th><th>TOD</th><th>Value</th><th>← Prev</th><th>Pos Dists</th><th>Pos Σ</th><th>Srt Dists</th><th>Srt Σ</th><th>±1</th><th>Held</th></tr></thead><tbody>\n'

    for i, r in enumerate(results):
        pd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["pos_dists"])
        sd = "".join(f'<span class="dd d{d}">{d}</span>' for d in r["srt_dists"])
        n1 = r["pos_n1"]
        held = r["pos_held"]
        tod_lbl = r.get("tod", "")[:3]
        # Highlight rows with good nudges
        row_cls = ""
        if n1 >= 3:
            row_cls = ' style="background:rgba(45,212,160,.1)"'
        elif n1 >= 2:
            row_cls = ' style="background:rgba(240,182,52,.06)"'

        html += f'<tr{row_cls}><td style="color:#4d5570;font-size:.65rem">{i+1}</td>'
        html += f'<td>{r["date"]}</td><td>{tod_lbl}</td>'
        html += f'<td class="mono gr">{r["target"]}</td>'
        html += f'<td class="mono" style="color:#6b7390">{r["seed"]}</td>'
        html += f'<td><div class="dial">{pd}</div></td>'
        html += f'<td class="mono" style="color:#5b8cf0">{r["pos_total"]}</td>'
        html += f'<td><div class="dial">{sd}</div></td>'
        html += f'<td class="mono" style="color:#a78bfa">{r["srt_total"]}</td>'
        html += f'<td class="mono ye">{n1}</td>'
        html += f'<td class="mono" style="color:#2dd4a0">{held}</td></tr>\n'

    html += '</tbody></table></div></div></div>\n'

    # Footer + JS
    html += f"""
<div class="ft">{STATE} {GAME_TYPE} | {n:,} sequential + {ns:,} same-day pairs | {start_ym}→{end_ym} | Circular 0-9 digit distance</div>
</div>
<script>function sw(id,b){{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));b.classList.add('active');document.getElementById('tab-'+id).classList.add('active')}}</script>
</body></html>"""

    with open(filepath, "w") as f:
        f.write(html)
    print(f"📊 Report: {filepath}")


def write_csv_out(results, sameday, filepath):
    if not results: return
    rows = []
    for r in results:
        rows.append({
            "date": r["date"], "tod": r.get("tod",""), "target": r["target"],
            "seed": r["seed"], "seed_date": r.get("seed_date",""),
            "pos_total": r["pos_total"], "pos_changed": r["pos_changed"],
            "pos_n1": r["pos_n1"], "pos_n2": r["pos_n2"], "pos_n12": r["pos_n12"],
            "pos_d1": r["pos_dists"][0], "pos_d2": r["pos_dists"][1],
            "pos_d3": r["pos_dists"][2], "pos_d4": r["pos_dists"][3],
            "srt_total": r["srt_total"], "srt_changed": r["srt_changed"],
            "srt_n1": r["srt_n1"], "srt_n12": r["srt_n12"],
            "best_from": r.get("best_from",""), "best_seed": r.get("best_seed",""),
        })
    with open(filepath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # Same-day CSV
    if sameday:
        sd_path = filepath.replace(".csv", "_sameday.csv")
        sd_rows = [{"date": r["date"], "midday": r["seed"], "evening": r["target"],
                     "pos_total": r["pos_total"], "pos_n1": r["pos_n1"],
                     "srt_total": r["srt_total"], "srt_n1": r["srt_n1"]} for r in sameday]
        with open(sd_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sd_rows[0].keys())
            w.writeheader()
            w.writerows(sd_rows)
        print(f"📄 Same-day CSV: {sd_path}")

    print(f"📄 CSV: {filepath}")


# ── Main ───────────────────────────────────────────────────────
def main():
    pa = argparse.ArgumentParser(description="Digit Nudge Theory Scanner")
    pa.add_argument("--start", default="1990-01")
    pa.add_argument("--end", default="2026-02")
    pa.add_argument("--state", default="Florida")
    pa.add_argument("--game", default="pick4")
    pa.add_argument("--delay", type=float, default=0.05)
    pa.add_argument("--output", default="digit_proximity")
    args = pa.parse_args()

    global STATE, GAME_TYPE, DELAY
    STATE = args.state
    GAME_TYPE = args.game
    DELAY = args.delay

    print("=" * 64)
    print("  🎰 Digit Nudge Theory Scanner")
    print("=" * 64)
    print(f"  State:  {STATE}  |  Game: {GAME_TYPE}")
    print(f"  Range:  {args.start} → {args.end}")
    print(f"  Modes:  Positional + Sorted")
    print(f"  Rels:   Sequential + Same-Day + Best-of-Both")
    print(f"  Nudges: ±1 through ±5")
    print("=" * 64)

    print("\n🔌 Testing API...", end="", flush=True)
    test = api_post("/api/draws/recent", {"state": STATE, "game_type": GAME_TYPE,
                                           "start_date": "2019-10-08", "end_date": "2019-10-09"})
    if not test:
        print(f"\n❌ Cannot reach {BASE_URL}")
        sys.exit(1)
    print(f" ✓\n")

    t0 = time.time()

    baseline = compute_random_baseline()
    draws = load_all_draws(args.start, args.end)
    results, sameday = analyze_draws(draws)

    elapsed = time.time() - t0

    print("=" * 64)
    print(f"  ✅ {len(results):,} sequential + {len(sameday):,} same-day pairs")
    print(f"  📏 Avg distance (pos): {avg_of(results,'pos_total'):.3f}  (random: 10.0)")
    print(f"  📏 Avg distance (srt): {avg_of(results,'srt_total'):.3f}")
    print(f"  🎯 Avg ±1 nudges (pos): {avg_of(results,'pos_n1'):.3f}  (random: 0.8)")
    print(f"  ☀️🌙 Same-day avg dist: {avg_of(sameday,'pos_total'):.3f}" if sameday else "")
    print(f"  ⏱  {elapsed:.0f}s")
    print("=" * 64)

    write_csv_out(results, sameday, f"{args.output}.csv")
    write_report(results, sameday, baseline, f"{args.output}.html", args.start, args.end)
    print(f"\n🎯 Open {args.output}.html")


if __name__ == "__main__":
    main()
