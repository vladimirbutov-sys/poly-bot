"""Analysis: does liquidity affect denizz's profitability?
Outputs:
  - _analytics/data/denizz_liquidity_backtest.json
  - _analytics/data/denizz_liquidity_historical.json (sampled density proxy)
Run once. Heavy on CPU, light on network (<=100 API calls).
"""
import json, os, time, urllib.request, math, statistics
from collections import defaultdict
from datetime import datetime, timezone

BASE = r'c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2'
DATA = BASE + '/_analytics/data'

def load(name):
    with open(f'{DATA}/{name}','r',encoding='utf-8') as f:
        return json.load(f)

trades = load('denizz_trades_ALL.json')
resolutions = load('denizz_resolutions.json')
markets = load('denizz_markets_cache.json')

print(f'trades={len(trades)} resolutions={len(resolutions)} markets={len(markets)}')

# --- reconstruct positions: key = (cid, asset) ---
pos = defaultdict(lambda: {
    'buys_shares':0.0,'buys_usd':0.0,
    'sells_shares':0.0,'sells_usd':0.0,
    'first_ts':None,'last_ts':None,
    'cid':None,'asset':None,'title':None,'outcome':None,'outcomeIndex':None,'slug':None,
    'buy_trades':[],
})
for t in trades:
    k = (t['conditionId'], t['asset'])
    p = pos[k]
    p['cid']=t['conditionId']; p['asset']=t['asset']
    p['title']=t.get('title'); p['outcome']=t.get('outcome'); p['outcomeIndex']=t.get('outcomeIndex')
    p['slug']=t.get('slug')
    ts = t['timestamp']
    if p['first_ts'] is None or ts<p['first_ts']: p['first_ts']=ts
    if p['last_ts'] is None or ts>p['last_ts']: p['last_ts']=ts
    sz = float(t['size']); px = float(t['price']); usd = sz*px
    if t['side']=='BUY':
        p['buys_shares']+=sz; p['buys_usd']+=usd
        p['buy_trades'].append({'ts':ts,'size':sz,'price':px,'usd':usd})
    else:
        p['sells_shares']+=sz; p['sells_usd']+=usd

positions = list(pos.values())
print(f'positions reconstructed: {len(positions)}')

# --- attach resolution + PnL ---
# outcome index mapping: resolutions[cid] -> {winning_outcome:'Yes'/'No', tokens:[yes_id, no_id]?}
def resolve(p):
    r = resolutions.get(p['cid'])
    if not r or not r.get('resolved'):
        return None  # unresolved
    win = r.get('winning_outcome')
    # determine if this position's outcome won
    # position has 'outcome' text. Compare.
    if p['outcome'] and win:
        won = (str(p['outcome']).lower() == str(win).lower())
    else:
        # fallback via outcomeIndex if tokens list in same order
        won = None
    return won

# compute pnl per position
resolved_cnt=0; open_cnt=0; unknown_cnt=0
for p in positions:
    avg_buy_px = p['buys_usd']/p['buys_shares'] if p['buys_shares']>0 else 0
    avg_sell_px = p['sells_usd']/p['sells_shares'] if p['sells_shares']>0 else 0
    held_shares = p['buys_shares']-p['sells_shares']
    p['avg_buy_px']=avg_buy_px
    p['held_shares']=held_shares
    p['capital_in']=p['buys_usd']  # total USD put in over lifetime
    p['peak_position_usd']=avg_buy_px * p['buys_shares']  # = buys_usd (same thing)
    # PnL
    r = resolutions.get(p['cid'])
    if r and r.get('resolved'):
        won = resolve(p)
        if won is True:
            # unsold shares pay $1 each; sold shares already realized
            realized = p['sells_usd'] - avg_buy_px*p['sells_shares']
            unrealized = held_shares*1.0 - avg_buy_px*held_shares
            p['pnl']=realized+unrealized
            p['outcome_known']=True
            p['won']=True
        elif won is False:
            realized = p['sells_usd'] - avg_buy_px*p['sells_shares']
            unrealized = 0 - avg_buy_px*held_shares
            p['pnl']=realized+unrealized
            p['outcome_known']=True
            p['won']=False
        else:
            p['pnl']=None; p['outcome_known']=False; p['won']=None
    else:
        # unresolved: use sells as realized, mark unrealized nan
        if held_shares>0.001:
            p['pnl']=None; p['outcome_known']=False; p['won']=None
            open_cnt+=1
        else:
            # fully exited
            realized = p['sells_usd'] - avg_buy_px*p['sells_shares']
            p['pnl']=realized
            p['outcome_known']=True
            p['won']=(realized>0)
    if p['outcome_known']: resolved_cnt+=1
    else: unknown_cnt+=1
    p['roi']=(p['pnl']/p['capital_in']) if (p['pnl'] is not None and p['capital_in']>0) else None

print(f'resolved_or_exited={resolved_cnt} unresolved={unknown_cnt} open={open_cnt}')

# --- Q2: bucket by peak_position_usd ---
def bucket(usd):
    if usd<5000: return 'thin'
    if usd<50000: return 'medium'
    return 'deep'

buckets = {'thin':[], 'medium':[], 'deep':[]}
for p in positions:
    buckets[bucket(p['peak_position_usd'])].append(p)

def summarize(name, lst):
    tot=len(lst)
    cap=sum(x['capital_in'] for x in lst)
    resolved=[x for x in lst if x['pnl'] is not None]
    wins=[x for x in resolved if x['won']]
    losses=[x for x in resolved if x['won'] is False]
    pnl=sum(x['pnl'] for x in resolved)
    rois=[x['roi'] for x in resolved if x['roi'] is not None]
    avg_roi = statistics.mean(rois) if rois else None
    med_roi = statistics.median(rois) if rois else None
    hold=[(x['last_ts']-x['first_ts'])/86400.0 for x in lst if x['last_ts'] and x['first_ts']]
    avg_hold = statistics.mean(hold) if hold else None
    return {
        'bucket':name,'N':tot,'capital':round(cap,0),
        'resolved_N':len(resolved),'wins':len(wins),'losses':len(losses),
        'WR': (len(wins)/len(resolved)) if resolved else None,
        'pnl':round(pnl,0),
        'avg_roi':avg_roi,'median_roi':med_roi,
        'avg_hold_days':avg_hold,
        'avg_capital':round(cap/tot,0) if tot else 0,
    }

q2 = {n:summarize(n,l) for n,l in buckets.items()}
print('\n--- Q2: profitability by liquidity bucket ---')
for n in ['thin','medium','deep']:
    s=q2[n]
    wr = f"{s['WR']*100:.1f}%" if s['WR'] is not None else 'n/a'
    ar = f"{s['avg_roi']*100:+.1f}%" if s['avg_roi'] is not None else 'n/a'
    mr = f"{s['median_roi']*100:+.1f}%" if s['median_roi'] is not None else 'n/a'
    ah = f"{s['avg_hold_days']:.1f}d" if s['avg_hold_days'] is not None else 'n/a'
    print(f"{n:6s} N={s['N']:3d} resolved={s['resolved_N']:3d} WR={wr:>6s} avgROI={ar:>8s} medROI={mr:>8s} PnL=${s['pnl']:>12,.0f} cap=${s['capital']:>12,.0f} hold={ah}")

# --- Q1: ceiling-hit ratio per denizz buy ---
# For each individual BUY trade, ratio = buy_usd / peak_position_usd_on_same_cidtoken
# (if the buy equals the peak size, it was THE dominant size contribution).
# Also compute a "scaled" ratio: buy_usd / (peak_position + neighbor_volume_24h) — needs API.
ratios = []
for p in positions:
    peak = p['peak_position_usd']
    for b in p['buy_trades']:
        r = b['usd']/max(peak,1)
        ratios.append({'ratio':r,'usd':b['usd'],'bucket':bucket(peak),'cid':p['cid'],'ts':b['ts']})

r_gt05 = sum(1 for r in ratios if r['ratio']>0.5)
r_gt08 = sum(1 for r in ratios if r['ratio']>0.8)
print(f'\n--- Q1: ceiling-hit (buy_usd / peak_position_usd) ---')
print(f'total_buys={len(ratios)} ratio>0.5: {r_gt05} ({r_gt05/len(ratios)*100:.1f}%) ratio>0.8: {r_gt08} ({r_gt08/len(ratios)*100:.1f}%)')
by_b = defaultdict(lambda:[0,0,0])  # [total, gt05, gt08]
for r in ratios:
    by_b[r['bucket']][0]+=1
    if r['ratio']>0.5: by_b[r['bucket']][1]+=1
    if r['ratio']>0.8: by_b[r['bucket']][2]+=1
for b,(t,g5,g8) in by_b.items():
    print(f'  {b}: total={t} >0.5: {g5} ({g5/t*100:.1f}%) >0.8: {g8} ({g8/t*100:.1f}%)')

# --- sample API proxy: density for 50 thin and 50 deep trades (capped) ---
print('\n--- sampling density proxy (API <=100 calls) ---')
thin_samples = [p for p in positions if p['peak_position_usd']<5000 and p['buy_trades']][:40]
deep_samples = [p for p in positions if p['peak_position_usd']>=50000 and p['buy_trades']][:40]
med_samples = [p for p in positions if 5000<=p['peak_position_usd']<50000 and p['buy_trades']][:20]

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent':'liq-density/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8','ignore')
    except Exception as e:
        return None, str(e)[:200]

density_cache = {}
calls=0; max_calls=100
for lst in [thin_samples, med_samples, deep_samples]:
    for p in lst:
        if calls>=max_calls: break
        b = p['buy_trades'][0]  # first buy
        key = f"{p['cid']}|{b['ts']}"
        cid = p['cid']; ts = b['ts']
        url = f"https://data-api.polymarket.com/trades?market={cid}&startTs={ts-3600}&endTs={ts+3600}&limit=500"
        code, body = http_get(url); calls+=1
        if code==200:
            try:
                arr = json.loads(body)
                vol_usd = sum(t['size']*t['price'] for t in arr if t.get('asset')==p['asset'])
                density_cache[key] = {'cid':cid,'asset':p['asset'],'ts':ts,'buy_usd':b['usd'],
                                      'neighbor_trades':len(arr),'neighbor_vol_usd_sameToken':vol_usd,
                                      'peak_position_usd':p['peak_position_usd'],
                                      'bucket':bucket(p['peak_position_usd'])}
            except Exception as e:
                density_cache[key] = {'err':str(e)[:80]}
        else:
            density_cache[key] = {'err':f'http{code}'}
        time.sleep(0.55)
    if calls>=max_calls: break
print(f'density samples collected: {len(density_cache)} (API calls: {calls})')
# summarize density by bucket
by_b_density = defaultdict(list)
for v in density_cache.values():
    if 'bucket' in v:
        ratio = v['buy_usd']/max(v['neighbor_vol_usd_sameToken'],1)
        by_b_density[v['bucket']].append(ratio)
for b,rs in by_b_density.items():
    print(f'  {b}: N={len(rs)} median buy_usd/neighborVol1h = {statistics.median(rs)*100:.1f}% mean={statistics.mean(rs)*100:.1f}%')

# save historical cache
with open(f'{DATA}/denizz_liquidity_historical.json','w',encoding='utf-8') as f:
    json.dump(density_cache, f, indent=2)

# --- Q3: backtest V2 bot sizing with/without M_liquidity ---
# V2 sizing approx: base=$80 × multipliers, cap $200. We mimic a simple baseline where
# each denizz BUY triggers our $80 copy. Profit for our position follows denizz's ROI
# (we ride the same market outcome with same avg_buy_px approximately).
# This is a simplification — we don't model follow-sell tiers because denizz ALL positions
# include sells. We compute our pnl per position as: our_bet * position_roi.
# Then apply M_liquidity candidates and compare.
def our_pnl(p, base=80, liq_mult=1.0, cap=200, min_bet=10):
    if p['roi'] is None: return 0.0, 0.0
    bet = min(base*liq_mult, cap)
    bet = max(bet, min_bet) if bet>0 else 0
    # Apply filter: only copy when denizz buy_usd >= 500 (typical copybot filter)
    if p['capital_in']<500: return 0.0, 0.0
    return bet, bet*p['roi']

def backtest(liq_mults):
    """liq_mults: dict bucket->multiplier."""
    total_bet=0.0; total_pnl=0.0; n=0
    per_b = defaultdict(lambda:{'bet':0,'pnl':0,'n':0})
    for p in positions:
        m = liq_mults[bucket(p['peak_position_usd'])]
        bet, pnl = our_pnl(p, liq_mult=m)
        if bet==0: continue
        total_bet+=bet; total_pnl+=pnl; n+=1
        b = bucket(p['peak_position_usd'])
        per_b[b]['bet']+=bet; per_b[b]['pnl']+=pnl; per_b[b]['n']+=1
    return {'total_bet':total_bet,'total_pnl':total_pnl,'roi': total_pnl/total_bet if total_bet else 0,'n':n,'per_bucket':dict(per_b)}

baseline = backtest({'thin':1.0,'medium':1.0,'deep':1.0})
print(f'\n--- Q3: Backtest baseline (no M_liquidity) ---')
print(f"n={baseline['n']} total_bet=${baseline['total_bet']:.0f} total_pnl=${baseline['total_pnl']:.0f} roi={baseline['roi']*100:+.1f}%")
for b,v in baseline['per_bucket'].items():
    print(f"  {b}: n={v['n']} bet=${v['bet']:.0f} pnl=${v['pnl']:.0f} roi={(v['pnl']/v['bet']*100) if v['bet'] else 0:+.1f}%")

# Candidate M_liquidity tables based on Q2 results: size UP on best bucket, DOWN on worst
# We derive candidates from bucket ROI signals.
thin_roi = q2['thin']['avg_roi'] or 0
med_roi = q2['medium']['avg_roi'] or 0
deep_roi = q2['deep']['avg_roi'] or 0

candidates = {
  'size_up_thin_1.3x': {'thin':1.3,'medium':1.0,'deep':1.0},
  'size_up_thin_1.5x_down_deep_0.7x': {'thin':1.5,'medium':1.0,'deep':0.7},
  'size_up_deep_1.3x': {'thin':1.0,'medium':1.0,'deep':1.3},
  'size_down_thin_0.5x': {'thin':0.5,'medium':1.0,'deep':1.0},
  'skip_thin': {'thin':0.0,'medium':1.0,'deep':1.0},
  'skip_deep':  {'thin':1.0,'medium':1.0,'deep':0.0},
}
results=[]
for name,mults in candidates.items():
    r = backtest(mults)
    delta_usd = r['total_pnl']-baseline['total_pnl']
    delta_pct = (r['total_pnl']/baseline['total_pnl']-1)*100 if baseline['total_pnl'] else 0
    results.append({'name':name,'mults':mults,**r,'delta_usd':delta_usd,'delta_pct':delta_pct})
    print(f"\n{name:35s} bet=${r['total_bet']:>6.0f} pnl=${r['total_pnl']:>7.0f} roi={r['roi']*100:+.1f}% delta=${delta_usd:+.0f} ({delta_pct:+.1f}%)")

# save full backtest
out = {
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'positions_count': len(positions),
    'buckets': q2,
    'q1_ceiling': {
        'total_buys': len(ratios),
        'pct_ratio_gt_0.5': r_gt05/len(ratios),
        'pct_ratio_gt_0.8': r_gt08/len(ratios),
        'by_bucket': {b:{'total':t,'gt05':g5,'gt08':g8} for b,(t,g5,g8) in by_b.items()},
    },
    'baseline': baseline,
    'candidates': results,
    'density_sample_stats': {b:{'n':len(rs),'median':statistics.median(rs),'mean':statistics.mean(rs)} for b,rs in by_b_density.items()},
}
with open(f'{DATA}/denizz_liquidity_backtest.json','w',encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)
print('\nSaved:', f'{DATA}/denizz_liquidity_backtest.json')
print('Saved:', f'{DATA}/denizz_liquidity_historical.json')
