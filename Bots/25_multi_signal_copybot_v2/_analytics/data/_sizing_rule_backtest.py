"""
Backtest proposed sizing rule (scope: NEW ENTRIES, Path A only).
AS IS: skip <$150, log formula otherwise.
TO BE: $100-250 -> $8 fixed, $250-500 -> $15 fixed, >=$500 -> log formula.
Multipliers (price, horizon), MIN_BET_USD=$10 floor still apply.
"""
import json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone

DATA="."
acts=json.load(open(f"{DATA}/denizz_activity_ALL.json",'r',encoding='utf-8'))
resols=json.load(open(f"{DATA}/denizz_resolutions.json",'r',encoding='utf-8'))
closed=json.load(open(f"{DATA}/denizz_closed_positions_raw.json",'r',encoding='utf-8'))

# --- config replica ---
BET_FORMULA_A = 31.75
BET_FORMULA_B = -177
MIN_BET_USD   = 10.0
PRICE_BET_MULTIPLIERS = [(0.00,0.82,1.0),(0.82,0.99,0.65)]
# HORIZON tiers require endDate which we only reliably have for closed positions
HORIZON_TIERS = [(0,30,1.0),(30,60,0.8),(60,90,0.7),(90,120,0.4),(120,99999,0.0)]
PRICE_FILTER  = (0.05, 0.99)

def price_mult(p):
    for lo,hi,m in PRICE_BET_MULTIPLIERS:
        if lo<=p<hi: return m
    return 1.0

def horizon_mult(days):
    if days is None: return 0.9  # neutral assumption when unknown
    for lo,hi,m in HORIZON_TIERS:
        if lo<=days<hi: return m
    return 0.0

def log_formula(invested):
    if invested<=0: return 0.0
    return max(0.0, BET_FORMULA_A*math.log(invested)+BET_FORMULA_B)

# --- build trade stream ---
trades=[t for t in acts if t.get('type')=='TRADE']
trades.sort(key=lambda x:x['timestamp'])

# endDate per condition from closed-positions
end_by_cond={c['conditionId']: c.get('endDate') for c in closed if c.get('endDate')}

# group BUY events into "buy events" (consecutive BUYs by denizz on same asset within a short window)
# Polymarket returns each fill separately; aggregate fills on same asset within 60s into one event.
EVENT_WINDOW_S = 60
events=[]  # each: dict with asset,conditionId,side,price_avg,usd,size,timestamp,title,outcome
cur=None
for t in trades:
    key=(t['asset'],t['side'])
    if cur and cur['_key']==key and t['timestamp']-cur['_last_ts']<=EVENT_WINDOW_S:
        sz=float(t['size']); usd=float(t['usdcSize']); pr=float(t['price'])
        cur['size']+=sz; cur['usd']+=usd
        cur['_last_ts']=t['timestamp']
    else:
        if cur: events.append(cur)
        cur={
          '_key':key,'_last_ts':t['timestamp'],
          'asset':t['asset'],'conditionId':t['conditionId'],
          'side':t['side'],'price':float(t['price']),
          'size':float(t['size']),'usd':float(t['usdcSize']),
          'timestamp':t['timestamp'],'title':t.get('title'),'outcome':t.get('outcome'),
          'outcomeIndex':t.get('outcomeIndex')
        }
if cur: events.append(cur)

buy_events = [e for e in events if e['side']=='BUY']
sell_events = [e for e in events if e['side']=='SELL']
print(f"Total TRADE fills: {len(trades)}")
print(f"Aggregated events: {len(events)} (BUY={len(buy_events)}, SELL={len(sell_events)})")

# --- histogram of BUY event sizes ---
bins=[(0,100),(100,250),(250,500),(500,750),(750,1500),(1500,1e12)]
hist={f"{lo}-{hi}":0 for lo,hi in bins}
for e in buy_events:
    for lo,hi in bins:
        if lo<=e['usd']<hi:
            hist[f"{lo}-{hi}"]+=1; break
print("\nBuy-event size histogram:")
for k,v in hist.items(): print(f"  {k}: {v}")

# --- classify NEW vs TOP-UP ---
# Track denizz open positions by asset; a BUY event is NEW if denizz had 0 size on this asset before it.
pos = defaultdict(float)   # asset -> cumulative size
pos_cost = defaultdict(float)
pos_first_ts = defaultdict(lambda: None)
classified=[]
for e in events:
    a=e['asset']; side=e['side']
    if side=='BUY':
        is_new = pos[a] <= 1e-6
        e['is_new_entry']=is_new
        if is_new: pos_first_ts[a]=e['timestamp']
        pos[a]+=e['size']; pos_cost[a]+=e['usd']
    else: # SELL
        e['is_new_entry']=False
        pos[a]-=e['size']
        if pos[a]<=1e-6:
            pos[a]=0.0; pos_cost[a]=0.0
    classified.append(e)

new_100_250=[e for e in buy_events if e['is_new_entry'] and 100<=e['usd']<250]
new_250_500=[e for e in buy_events if e['is_new_entry'] and 250<=e['usd']<500]
new_500p=[e for e in buy_events if e['is_new_entry'] and e['usd']>=500]
new_150p=[e for e in buy_events if e['is_new_entry'] and e['usd']>=150]
topup_100_250=[e for e in buy_events if (not e['is_new_entry']) and 100<=e['usd']<250]
topup_250_500=[e for e in buy_events if (not e['is_new_entry']) and 250<=e['usd']<500]
print(f"\nNEW entries $100-250: {len(new_100_250)} | TOP-UPs in same bin: {len(topup_100_250)}")
print(f"NEW entries $250-500: {len(new_250_500)} | TOP-UPs in same bin: {len(topup_250_500)}")
print(f"NEW entries >=$500:   {len(new_500p)}")
print(f"NEW entries >=$150 (AS-IS baseline): {len(new_150p)}")

# --- outcome per asset ---
# For each asset that denizz bought, determine our exit:
#   1) denizz SELL on same asset at the nearest subsequent timestamp -> exit at denizz sell price (weighted avg of sells until cumulative size reaches ours)
#   2) if never sold, check resolution: winner_price for that token_id=1.0, else 0.0
#   3) if unresolved and not sold -> mark as OPEN (use curPrice from closed pos if available, else flag)

# Build sell schedule per asset
sells_by_asset=defaultdict(list)
for e in sell_events:
    sells_by_asset[e['asset']].append(e)
for a in sells_by_asset: sells_by_asset[a].sort(key=lambda x:x['timestamp'])

# Resolution by token/asset
token_resolved_price={}
for cond,info in resols.items():
    if info.get('resolved'):
        for tk in info.get('tokens',[]):
            token_resolved_price[tk['token_id']]=float(tk['price'])

# current price from closed positions (for still-open at t=end)
cur_price_by_asset={c['asset']: float(c.get('curPrice') or 0) for c in closed}

NOW_TS = max(t['timestamp'] for t in trades)

def simulate_exit(entry_event, our_base_bet):
    """Return (exit_price, outcome_tag, days_held)."""
    a=entry_event['asset']; cond=entry_event['conditionId']; t0=entry_event['timestamp']
    entry_price=entry_event['price']
    # find first denizz sell after t0
    sells=[s for s in sells_by_asset.get(a,[]) if s['timestamp']>t0]
    if sells:
        # use VWAP of sells (simplification)
        tot_sz=sum(s['size'] for s in sells)
        tot_usd=sum(s['usd'] for s in sells)
        exit_p = tot_usd/tot_sz if tot_sz>0 else entry_price
        days=(sells[-1]['timestamp']-t0)/86400
        # apply stop-loss check: if at any point price dropped -60% before this sell, hit stop
        # (we don't have intraday data — approximate: if final exit < entry*0.4, assume stop triggered at -60%)
        if exit_p < entry_price*0.4:
            return (entry_price*0.4, 'stop_loss', days)
        return (exit_p, 'follow_sell', days)
    # no sell -> resolution
    if a in token_resolved_price:
        rp=token_resolved_price[a]
        days=(NOW_TS-t0)/86400
        tag='resolved_win' if rp>0.5 else 'resolved_loss'
        return (rp, tag, days)
    # unresolved & open
    cp=cur_price_by_asset.get(a, entry_price)
    days=(NOW_TS-t0)/86400
    if cp < entry_price*0.4:
        return (entry_price*0.4, 'stop_loss_open', days)
    return (cp, 'open_mark_to_market', days)

def compute_bet_to_be(usd_event, price, days_to_end, invested_total):
    """Apply TO-BE sizing rule w/ multipliers and MIN_BET_USD floor."""
    if usd_event < 100: return 0.0, 'skip_<100'
    if 100<=usd_event<250: base=8.0; tag='fixed_8'
    elif 250<=usd_event<500: base=15.0; tag='fixed_15'
    else: base=log_formula(invested_total if invested_total>0 else usd_event); tag='formula'
    bet=base * price_mult(price) * horizon_mult(days_to_end)
    if bet < MIN_BET_USD: return 0.0, f'{tag}_below_min'
    return bet, tag

def compute_bet_as_is(usd_event, price, days_to_end, invested_total):
    if usd_event < 150: return 0.0,'skip_<150'
    base=log_formula(invested_total if invested_total>0 else usd_event)
    bet=base*price_mult(price)*horizon_mult(days_to_end)
    if bet<MIN_BET_USD: return 0.0,'below_min'
    return bet,'formula'

# Days-to-end per event
def days_to_end(e):
    ed=end_by_cond.get(e['conditionId'])
    if not ed: return None
    try:
        d=datetime.fromisoformat(ed.replace('Z','+00:00'))
        return (d.timestamp()-e['timestamp'])/86400
    except Exception:
        return None

# Track invested-total-on-market PER DENIZZ (for formula input)
denizz_invested = defaultdict(float)  # asset -> cumulative usd
denizz_size     = defaultdict(float)

# Re-simulate in chrono order producing AS-IS and TO-BE signal lists
as_is_trades=[]
to_be_trades=[]
added_trades=[]  # TO-BE only (new signals that AS-IS would skip)

# also price filter: denizz 0.05-0.99
for e in sorted(events, key=lambda x:x['timestamp']):
    a=e['asset']
    if e['side']=='BUY':
        # update denizz invested BEFORE sizing, invested-total refers to BEFORE this event
        inv_before = denizz_invested[a]
        dte=days_to_end(e)
        px=e['price']
        # price filter
        price_ok = (PRICE_FILTER[0] <= px <= PRICE_FILTER[1])
        is_new = e['is_new_entry']
        # AS IS logic — only NEW entries under scope; top-ups go separate path (out of scope for this change)
        if is_new and price_ok:
            bet_asis, tag_asis = compute_bet_as_is(e['usd'], px, dte, inv_before if inv_before>0 else e['usd'])
            bet_tobe, tag_tobe = compute_bet_to_be(e['usd'], px, dte, inv_before if inv_before>0 else e['usd'])
            if bet_asis>0:
                as_is_trades.append({'event':e,'bet':bet_asis,'tag':tag_asis})
            if bet_tobe>0:
                to_be_trades.append({'event':e,'bet':bet_tobe,'tag':tag_tobe})
                if bet_asis<=0:
                    added_trades.append({'event':e,'bet':bet_tobe,'tag':tag_tobe})
        # update denizz cumulative
        denizz_invested[a]+=e['usd']
        denizz_size[a]+=e['size']
    else:
        denizz_size[a]-=e['size']
        if denizz_size[a]<=1e-6:
            denizz_size[a]=0; denizz_invested[a]=0

print(f"\nAS-IS new-entry signals: {len(as_is_trades)}")
print(f"TO-BE new-entry signals: {len(to_be_trades)}")
print(f"Added signals (delta):   {len(added_trades)}")

# --- PnL simulation ---
def simulate(list_trades, label):
    pnls=[]; rois=[]; tags=[]; capital_timeseries=[]
    slots_open=defaultdict(float)  # asset -> our bet USD (rough slot tracking)
    slot_close_ts={}  # asset -> close timestamp
    total_deployed=0.0
    peak_slots=0
    equity=0.0
    eq_curve=[]
    for tr in sorted(list_trades, key=lambda x:x['event']['timestamp']):
        e=tr['event']; bet=tr['bet']
        # close any slot whose asset has resolved/sold before current ts
        to_close=[k for k,ts in slot_close_ts.items() if ts<=e['timestamp']]
        for k in to_close:
            slots_open.pop(k,None); slot_close_ts.pop(k,None)
        exit_p, outcome, days = simulate_exit(e, bet)
        gross_pnl = bet * (exit_p - e['price']) / e['price']
        # fee/slippage approx: 0.4% in+out on notional
        fee = bet * 0.004 * 2
        net = gross_pnl - fee
        pnls.append(net); rois.append(net/bet if bet>0 else 0); tags.append(outcome)
        total_deployed += bet
        # slot window
        slots_open[e['asset']]=bet
        # close at denizz sell ts or NOW
        sells=[s for s in sells_by_asset.get(e['asset'],[]) if s['timestamp']>e['timestamp']]
        close_ts = sells[-1]['timestamp'] if sells else NOW_TS
        slot_close_ts[e['asset']]=close_ts
        # peak slots snapshot
        active=sum(1 for ts in slot_close_ts.values() if ts>=e['timestamp'])
        peak_slots=max(peak_slots, active)
        equity+=net
        eq_curve.append(equity)
    wins=sum(1 for p in pnls if p>0)
    wr = wins/len(pnls) if pnls else 0
    avg_roi = sum(rois)/len(rois) if rois else 0
    avg_pnl = sum(pnls)/len(pnls) if pnls else 0
    total_pnl = sum(pnls)
    max_loss = min(pnls) if pnls else 0
    sd = statistics.pstdev(pnls) if len(pnls)>1 else 0
    sharpe = (avg_pnl/sd) if sd>0 else 0
    # max drawdown on equity curve
    peak=0; mdd=0
    for v in eq_curve:
        if v>peak: peak=v
        dd=peak-v
        if dd>mdd: mdd=dd
    # tag dist
    tag_c=defaultdict(int)
    for t in tags: tag_c[t]+=1
    return {
      'label':label,'n':len(pnls),'wr':wr,'avg_roi':avg_roi,'avg_pnl':avg_pnl,
      'total_pnl':total_pnl,'total_deployed':total_deployed,'max_loss':max_loss,
      'std':sd,'sharpe':sharpe,'max_dd':mdd,'peak_slots':peak_slots,'tags':dict(tag_c)
    }

r_asis = simulate(as_is_trades,'AS_IS')
r_tobe = simulate(to_be_trades,'TO_BE')
r_added= simulate(added_trades,'ADDED_ONLY')

def pr(r):
    print(f"\n=== {r['label']} ===")
    for k in ['n','wr','avg_roi','avg_pnl','total_pnl','total_deployed','max_loss','std','sharpe','max_dd','peak_slots']:
        v=r[k]
        if isinstance(v,float):
            print(f"  {k}: {v:.3f}")
        else:
            print(f"  {k}: {v}")
    print("  tags:", r['tags'])

pr(r_asis); pr(r_tobe); pr(r_added)

# Sample trade dump
print("\n--- SAMPLE simulated ADDED trade ---")
if added_trades:
    s=added_trades[0]; e=s['event']
    exit_p,outcome,days=simulate_exit(e,s['bet'])
    gross=s['bet']*(exit_p-e['price'])/e['price']
    fee=s['bet']*0.008
    print(json.dumps({
      'ts':datetime.fromtimestamp(e['timestamp'],tz=timezone.utc).isoformat(),
      'title':e['title'][:80] if e['title'] else None,
      'outcome':e['outcome'],
      'denizz_usd_event':round(e['usd'],2),
      'denizz_price':round(e['price'],4),
      'our_bet':round(s['bet'],2),
      'tag':s['tag'],
      'exit_price':round(exit_p,4),
      'exit_tag':outcome,
      'days_held':round(days,1),
      'gross_pnl':round(gross,3),
      'net_pnl':round(gross-fee,3)
    }, indent=2))

# Save full results
out={
  'hist':hist,
  'counts':{
    'new_100_250':len(new_100_250),'new_250_500':len(new_250_500),
    'new_500p':len(new_500p),'new_150p':len(new_150p),
    'topup_100_250':len(topup_100_250),'topup_250_500':len(topup_250_500),
    'asis_signals':len(as_is_trades),'tobe_signals':len(to_be_trades),
    'added':len(added_trades)
  },
  'asis':r_asis,'tobe':r_tobe,'added':r_added
}
json.dump(out, open('sizing_rule_backtest_results.json','w'), indent=2, default=str)
print("\nSaved sizing_rule_backtest_results.json")
