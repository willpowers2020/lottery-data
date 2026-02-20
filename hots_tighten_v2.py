#!/usr/bin/env python3
"""
🌶️ Hots Tightening v2 — Target the 200-400 candidate gap
==========================================================
Focuses on strategies that could be profitable:
- Dynamic sum centering (median, weighted avg, peak)
- Asymmetric TD ranges (tight low, wide high or vice versa)
- Combined type+sum+TD combos
- Profit-focused analysis with box payout tiers
"""

import requests, json, argparse, csv, sys
from datetime import datetime, timedelta
from itertools import combinations_with_replacement
from collections import Counter

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"

def api(path, data=None):
    url = f"{BASE_URL}{path}?db={DB_MODE}"
    r = requests.post(url, json=data, timeout=60) if data else requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()

def digit_sum(n): return sum(int(c) for c in n)
def get_2dp(n):
    c=list(n); return {c[i]+c[j] for i in range(len(c)) for j in range(i+1,len(c))}
def classify(n):
    c=sorted(Counter(n).values(),reverse=True)
    if c[0]==4:return 'Q'
    if c[0]==3:return 'T'
    if c[0]==2 and len(c)>1 and c[1]==2:return 'DD'
    if c[0]==2:return 'D'
    return 'S'

def gen_cands(digits, s_min, s_max, td_map, t_min=0, t_max=999, types=None):
    cands=[]
    for combo in combinations_with_replacement(sorted(digits),4):
        n=''.join(str(d) for d in combo)
        ds=digit_sum(n)
        if ds<s_min or ds>s_max: continue
        td=td_map.get(n,0)
        if td<t_min or td>t_max: continue
        if types and classify(n) not in types: continue
        cands.append(n)
    return cands

def analyze_seeds(seed_values, td_map):
    sums,tds,digits=[],[],Counter()
    for val in seed_values:
        norm=''.join(sorted(val))
        sums.append(digit_sum(norm))
        tds.append(td_map.get(norm,0))
        for c in set(norm): digits[c]+=1
    tds_nz=[t for t in tds if t>0]
    s_sorted=sorted(sums)
    t_sorted=sorted(tds_nz) if tds_nz else [20,40]
    return {
        'digits':[int(d) for d in digits.keys()],
        's_min':min(sums),'s_max':max(sums),
        's_avg':sum(sums)/len(sums),'s_med':s_sorted[len(s_sorted)//2],
        's_q1':s_sorted[len(s_sorted)//4],'s_q3':s_sorted[3*len(s_sorted)//4],
        't_min':t_sorted[0],'t_max':t_sorted[-1],
        't_avg':sum(t_sorted)/len(t_sorted),'t_med':t_sorted[len(t_sorted)//2],
        't_q1':t_sorted[len(t_sorted)//4],'t_q3':t_sorted[3*len(t_sorted)//4],
    }

def build_strategies():
    S={}
    
    # === GROUP 1: Full range sum, various TD windows (baseline) ===
    for sp in [0,1,2,3]:
        for tp in [0,2]:
            for ty,tn in [(None,''),({'S','D'},'SD')]:
                k=f"g1_s{sp}_t{tp}_{tn or 'all'}"
                S[k]={'name':f"Σ±{sp} TD±{tp}{' '+tn if tn else ''}",'group':'Baseline',
                       'sum':'range','sp':sp,'td':'range','tp':tp,'types':ty,'dig':'hot'}

    # === GROUP 2: Median-centered sum (tighter) ===
    for sw in [4,6,8,10,12]:
        for tp in [0,2]:
            for ty,tn in [(None,''),({'S','D'},'SD')]:
                k=f"g2_sw{sw}_t{tp}_{tn or 'all'}"
                S[k]={'name':f"Σ med±{sw//2} TD±{tp}{' '+tn if tn else ''}",'group':'Med-Center',
                       'sum':'median','sw':sw,'td':'range','tp':tp,'types':ty,'dig':'hot'}

    # === GROUP 3: Q1-Q3 sum (interquartile) ===
    for sp in [0,1,2,3]:
        for tp in [0,2]:
            k=f"g3_iqr_s{sp}_t{tp}"
            S[k]={'name':f"Σ IQR±{sp} TD±{tp}",'group':'IQR-Sum',
                   'sum':'iqr','sp':sp,'td':'range','tp':tp,'types':None,'dig':'hot'}
            k2=f"g3_iqr_s{sp}_t{tp}_SD"
            S[k2]={'name':f"Σ IQR±{sp} TD±{tp} SD",'group':'IQR-Sum',
                    'sum':'iqr','sp':sp,'td':'range','tp':tp,'types':{'S','D'},'dig':'hot'}

    # === GROUP 4: Asymmetric TD — tight bottom, wide top ===
    for sp in [1,2,3]:
        k=f"g4_s{sp}_td_tight_bot"
        S[k]={'name':f"Σ±{sp} TD[q1→max+5]",'group':'Asym-TD',
               'sum':'range','sp':sp,'td':'asym_top','types':None,'dig':'hot'}
        k2=f"g4_s{sp}_td_tight_bot_SD"
        S[k2]={'name':f"Σ±{sp} TD[q1→max+5] SD",'group':'Asym-TD',
                'sum':'range','sp':sp,'td':'asym_top','types':{'S','D'},'dig':'hot'}

    # === GROUP 5: Median TD centered ===
    for sp in [1,2,3]:
        for tw in [10,15,20]:
            k=f"g5_s{sp}_tmed{tw}"
            S[k]={'name':f"Σ±{sp} TD med±{tw//2}",'group':'Med-TD',
                   'sum':'range','sp':sp,'td':'median','tw':tw,'types':None,'dig':'hot'}
            k2=f"g5_s{sp}_tmed{tw}_SD"
            S[k2]={'name':f"Σ±{sp} TD med±{tw//2} SD",'group':'Med-TD',
                    'sum':'range','sp':sp,'td':'median','tw':tw,'types':{'S','D'},'dig':'hot'}

    # === GROUP 6: All digits with tight params ===
    for sp in [1,2]:
        for tp in [0,2]:
            for ty,tn in [(None,''),({'S','D'},'SD')]:
                k=f"g6_all_s{sp}_t{tp}_{tn or 'all'}"
                S[k]={'name':f"All10 Σ±{sp} TD±{tp}{' '+tn if tn else ''}",'group':'All-Digits',
                       'sum':'range','sp':sp,'td':'range','tp':tp,'types':ty,'dig':'all'}

    return S

def get_ranges(strat, a):
    """Compute sum and TD ranges for a strategy given seed analysis."""
    # Sum range
    if strat['sum']=='median':
        sw=strat['sw']
        s_min=max(0,int(a['s_med']-sw//2))
        s_max=min(36,int(a['s_med']+sw//2))
    elif strat['sum']=='iqr':
        sp=strat['sp']
        s_min=max(0,a['s_q1']-sp)
        s_max=min(36,a['s_q3']+sp)
    else:
        sp=strat['sp']
        s_min=max(0,a['s_min']-sp)
        s_max=min(36,a['s_max']+sp)
    
    # TD range
    if strat['td']=='asym_top':
        t_min=a['t_q1']
        t_max=a['t_max']+5
    elif strat['td']=='median':
        tw=strat['tw']
        t_min=max(0,int(a['t_med']-tw//2))
        t_max=int(a['t_med']+tw//2)
    else:
        tp=strat.get('tp',0)
        t_min=max(0,a['t_min']-tp)
        t_max=a['t_max']+tp
    
    return s_min,s_max,t_min,t_max

def run(state,game,start,end,pw=5):
    print(f"\n{'='*80}")
    print(f"🌶️  HOTS TIGHTENING v2 — Targeting 200-400 Candidate Sweet Spot")
    print(f"{'='*80}")
    print(f"State: {state} | Dates: {start} → {end} | PW: {pw} days\n")
    
    # Pre-load TD
    print("📈 Pre-loading TD map...")
    all_combos=[''.join(str(d) for d in c) for c in combinations_with_replacement(range(10),4)]
    td_map={}
    for i in range(0,len(all_combos),500):
        chunk=all_combos[i:i+500]
        try:
            td=api('/api/td/lookup',{'candidates':chunk,'state':state,'game_type':game})
            td_map.update(td.get('td',{}))
        except Exception as e: print(f"  ⚠️ {e}")
    print(f"✅ TD loaded: {len(td_map)} (max TD: {max(td_map.values()) if td_map else 0})\n")
    
    strategies=build_strategies()
    print(f"Testing {len(strategies)} parameter combos...\n")
    
    R={k:{'hits':0,'winners':0,'cands':0,'dates':0} for k in strategies}
    miss_data=[]
    
    cur=datetime.strptime(start,'%Y-%m-%d')
    end_d=datetime.strptime(end,'%Y-%m-%d')
    dc=0
    
    while cur<=end_d:
        td_str=cur.strftime('%Y-%m-%d')
        ss=(cur-timedelta(days=pw)).strftime('%Y-%m-%d')
        se=(cur-timedelta(days=1)).strftime('%Y-%m-%d')
        try:
            seeds=api('/api/draws/recent',{'state':state,'game_type':game,'start_date':ss,'end_date':se}).get('draws',[])
            winners=api('/api/draws/recent',{'state':state,'game_type':game,'start_date':td_str,'end_date':td_str}).get('draws',[])
        except: cur+=timedelta(days=1); continue
        
        if len(seeds)<2 or not winners: cur+=timedelta(days=1); continue
        dc+=1
        a=analyze_seeds([s['value'] for s in seeds],td_map)
        w_norms=[w['actual'] for w in winners]
        
        sys.stdout.write(f"\r  [{dc}] {td_str} | Seeds:{len(seeds)} Winners:{len(winners)}")
        sys.stdout.flush()
        
        for sk,st in strategies.items():
            digits=list(range(10)) if st['dig']=='all' else a['digits']
            s_min,s_max,t_min,t_max=get_ranges(st,a)
            cands=set(gen_cands(digits,s_min,s_max,td_map,t_min,t_max,st.get('types')))
            hits=sum(1 for w in w_norms if w in cands)
            R[sk]['hits']+=hits; R[sk]['winners']+=len(winners)
            R[sk]['cands']+=len(cands); R[sk]['dates']+=1
        
        # Miss tracking for best baseline
        s_min_b=max(0,a['s_min']-2); s_max_b=min(36,a['s_max']+2)
        t_min_b=max(0,a['t_min']-2); t_max_b=a['t_max']+2
        for w in winners:
            wn=w['actual']; ws=digit_sum(wn); wt=td_map.get(wn,0)
            in_s=s_min_b<=ws<=s_max_b; in_t=t_min_b<=wt<=t_max_b
            if not (in_s and in_t):
                miss_data.append({'date':td_str,'winner':w['value'],'norm':wn,
                    'type':classify(wn),'sum':ws,'td':wt,
                    'seed_s':f"{a['s_min']}-{a['s_max']}",'seed_t':f"{a['t_min']}-{a['t_max']}",
                    'miss_s':not in_s,'miss_t':not in_t})
        cur+=timedelta(days=1)
    
    # ── Results ─────────────────────────────────────────────────────────
    total_w=R[list(R.keys())[0]]['winners']
    print(f"\n\n{'='*80}")
    print(f"📊 RESULTS — {dc} dates, {total_w} winners")
    print(f"{'='*80}\n")
    
    # Sort: prioritize strategies in the profitable zone
    scored=[]
    for sk,r in R.items():
        if r['dates']==0: continue
        rate=r['hits']/r['winners']*100 if r['winners']>0 else 0
        avg_c=r['cands']/r['dates']
        # Expected profit per draw: (rate/100 * winners_per_day * $200_payout) - cost
        # Simplified: rate/100 * $400 (2 winners/day avg) - avg_cands
        ev=(rate/100)*400-avg_c
        scored.append((sk,rate,avg_c,ev,r))
    
    scored.sort(key=lambda x:(-x[3],x[2]))  # Sort by EV desc, then cands asc
    
    # Print top performers by EV
    print(f"{'Strategy':<30} {'Rate':>6} {'Hits':>8} {'Cands':>6} {'EV/Draw':>8} {'Group':<12}")
    print(f"{'-'*80}")
    
    shown=set()
    for sk,rate,avg_c,ev,r in scored[:50]:
        st=strategies[sk]
        flag=''
        if ev>0: flag=' 💰'
        elif ev>-50: flag=' 💎'
        elif rate>=70 and avg_c<=300: flag=' ⭐'
        
        # Skip near-duplicates
        sig=f"{round(rate)}-{round(avg_c,-1)}"
        if sig in shown and not flag: continue
        shown.add(sig)
        
        print(f"{st['name']:<30} {rate:>5.1f}% {r['hits']:>3}/{r['winners']:<3} {int(avg_c):>6} {ev:>+7.0f} {st['group']:<12}{flag}")
    
    # ── Pareto ──────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"💎 PARETO FRONTIER")
    print(f"{'='*80}\n")
    
    tiers=[(0,100),(101,200),(201,300),(301,400),(401,500),(501,700)]
    print(f"{'Cands':<10} {'Strategy':<30} {'Rate':>6} {'EV':>8}")
    print(f"{'-'*60}")
    for lo,hi in tiers:
        best=None
        for sk,rate,avg_c,ev,r in scored:
            if lo<=avg_c<=hi and (best is None or rate>best[1]):
                best=(sk,rate,avg_c,ev)
        if best:
            print(f"{lo}-{hi:<6} {strategies[best[0]]['name']:<30} {best[1]:>5.1f}% {best[3]:>+7.0f}")
    
    # ── Profit Zone ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"💰 PROFIT ZONE (EV > 0 strategies)")
    print(f"{'='*80}\n")
    
    profitable=[x for x in scored if x[3]>0]
    if profitable:
        for sk,rate,avg_c,ev,r in profitable:
            st=strategies[sk]
            daily_cost=avg_c
            daily_rev=rate/100*400  # ~2 winners/day * $200 box
            print(f"  {st['name']:<30} Rate:{rate:.1f}% Cands:{int(avg_c)} Cost:${int(daily_cost)} Rev:${int(daily_rev)} Profit:${int(ev)}/day")
    else:
        print("  No strategies with positive EV at $1/play $200/box payout.")
        print("  Closest to breakeven:")
        for sk,rate,avg_c,ev,r in scored[:5]:
            st=strategies[sk]
            print(f"  {st['name']:<30} Rate:{rate:.1f}% Cands:{int(avg_c)} EV:{ev:+.0f}")
        print(f"\n  💡 To be profitable at $200 box payout:")
        print(f"     Need rate/100 × $400 > avg_cands")
        print(f"     e.g. 80% rate needs < 320 cands, 60% needs < 240 cands")
    
    # ── Miss Analysis ───────────────────────────────────────────────────
    if miss_data:
        print(f"\n{'='*80}")
        print(f"❌ MISS PATTERNS (Σ±2 TD±2 baseline: {len(miss_data)} misses)")
        print(f"{'='*80}\n")
        sm=sum(1 for m in miss_data if m['miss_s'])
        tm=sum(1 for m in miss_data if m['miss_t'])
        both=sum(1 for m in miss_data if m['miss_s'] and m['miss_t'])
        print(f"  Sum-only miss: {sm-both}  |  TD-only miss: {tm-both}  |  Both: {both}")
        
        # Analyze miss distances
        s_dists=[]; t_dists=[]
        for m in miss_data:
            sr=m['seed_s'].split('-'); s_lo,s_hi=int(sr[0]),int(sr[1])
            if m['miss_s']:
                if m['sum']<s_lo-2: s_dists.append(s_lo-2-m['sum'])
                elif m['sum']>s_hi+2: s_dists.append(m['sum']-s_hi-2)
            tr=m['seed_t'].split('-'); t_lo,t_hi=int(tr[0]),int(tr[1])
            if m['miss_t']:
                if m['td']<t_lo-2: t_dists.append(t_lo-2-m['td'])
                elif m['td']>t_hi+2: t_dists.append(m['td']-t_hi-2)
        
        if s_dists:
            print(f"  Sum miss distance: avg {sum(s_dists)/len(s_dists):.1f}, max {max(s_dists)}")
        if t_dists:
            print(f"  TD miss distance:  avg {sum(t_dists)/len(t_dists):.1f}, max {max(t_dists)}")
        
        print(f"\n  💡 Widening sum ±3 would catch {sm-both} more ({sum(1 for d in s_dists if d<=1)}/{len(s_dists)} are within 1)")
        print(f"  💡 Widening TD ±5 would catch {sum(1 for d in t_dists if d<=3)}/{len(t_dists)} of TD misses")
    
    # Save CSV
    csv_path=f"hots_tighten_v2_{state.lower()}_{start}_{end}.csv"
    rows=[{'strategy':strategies[sk]['name'],'group':strategies[sk]['group'],
           'rate':round(rate,1),'hits':r['hits'],'winners':r['winners'],
           'avg_cands':round(avg_c),'ev':round(ev,1)} for sk,rate,avg_c,ev,r in scored]
    with open(csv_path,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"\n📄 Saved: {csv_path}")

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--start',default='2026-01-01')
    p.add_argument('--end',default='2026-02-20')
    p.add_argument('--state',default='Florida')
    p.add_argument('--game',default='pick4')
    p.add_argument('--pw',type=int,default=5)
    p.add_argument('--url',default='http://localhost:5001')
    a=p.parse_args(); BASE_URL=a.url
    
    try: requests.get(f"{BASE_URL}/api/rbtl/data-stats/Florida/pick4?db={DB_MODE}",timeout=5); print("✅ Connected")
    except: print("❌ Flask not running"); sys.exit(1)
    
    run(a.state,a.game,a.start,a.end,a.pw)
