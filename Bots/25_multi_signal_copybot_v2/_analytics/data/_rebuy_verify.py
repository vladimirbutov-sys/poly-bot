import json, io, sys, os, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data"
with open(os.path.join(BASE, 'rebuy_events.json'), 'r', encoding='utf-8') as f:
    events = json.load(f)
with open(os.path.join(BASE, 'denizz_closed_positions_raw.json'), 'r', encoding='utf-8') as f:
    closed = json.load(f)
with open(os.path.join(BASE, 'denizz_resolutions.json'), 'r', encoding='utf-8') as f:
    resolutions = json.load(f)

res_map = {}
for c in closed:
    cp = c.get('curPrice')
    if cp not in (0.0, 1.0, 0, 1): continue
    inv = float(c.get('totalBought') or 0)
    pnl = float(c.get('realizedPnl') or 0)
    if inv < 1: continue
    res_map[(c.get('conditionId'), str(c.get('asset')))] = ('closed', pnl / inv)
for cid, r in resolutions.items():
    if not r.get('resolved'): continue
    for tok in r.get('tokens', []):
        k = (cid, str(tok.get('token_id')))
        if k in res_map: continue
        res_map[k] = ('resolution', 1.0 if tok.get('winner') else -1.0)

from collections import defaultdict
leg_rebuy_usd = defaultdict(float)
leg_roi = {}
for ev in events:
    k = (ev['cid'], ev['token'])
    leg_rebuy_usd[k] += ev['rebuy_usd']
    if k in res_map:
        leg_roi[k] = res_map[k]

print(f'Total rebuy events: {len(events)}')
print(f'Unique legs with rebuy: {len(leg_rebuy_usd)}')
print(f'Of those, resolved: {len(leg_roi)}')
print(f'Unresolved legs: {len(leg_rebuy_usd) - len(leg_roi)}')

wins = losses = 0
win_usd = lose_usd = 0
pos_pnl = neg_pnl = 0
for k, (src, roi) in leg_roi.items():
    usd = leg_rebuy_usd[k]
    pnl = usd * roi
    if pnl > 0:
        wins += 1; win_usd += usd; pos_pnl += pnl
    else:
        losses += 1; lose_usd += usd; neg_pnl += pnl
total_pnl = pos_pnl + neg_pnl
total_inv_res = win_usd + lose_usd
print('\nResolved-leg summary (attribution = leg_roi * rebuy_usd):')
print(f'  legs: W={wins} L={losses}  WR={wins/(wins+losses)*100:.1f}%')
print(f'  invested: {total_inv_res:.2f} USD  pnl: {total_pnl:+.2f} USD  ev_per_usd: {total_pnl/total_inv_res:+.3f}')

unres_usd = sum(leg_rebuy_usd[k] for k in leg_rebuy_usd if k not in leg_roi)
print(f'\nUnresolved legs: invested {unres_usd:.2f} USD')
print(f'Total rebuy USD: {sum(leg_rebuy_usd.values()):.2f}')

ev_resolved = [e for e in events if (e['cid'], e['token']) in res_map]
ev_unres = [e for e in events if (e['cid'], e['token']) not in res_map]
ev_wins = sum(1 for e in ev_resolved if res_map[(e['cid'], e['token'])][1] > 0)
ev_losses = sum(1 for e in ev_resolved if res_map[(e['cid'], e['token'])][1] <= 0)
print(f'\nEvent-level: resolved={len(ev_resolved)} unresolved={len(ev_unres)}')
if (ev_wins + ev_losses) > 0:
    print(f'  event-wins: {ev_wins}  event-losses: {ev_losses}  WR={ev_wins/(ev_wins+ev_losses)*100:.1f}%')

rois = [leg_roi[k][1] for k in leg_roi]
if rois:
    print(f'  mean leg ROI (unweighted): {statistics.mean(rois):+.3f}')
    print(f'  median leg ROI: {statistics.median(rois):+.3f}')

# Breakdown of unresolved by size bucket for neutral estimate
print('\nUnresolved legs detail:')
unres_legs = [k for k in leg_rebuy_usd if k not in res_map]
# map cid→title
cid_title = {}
for ev in events:
    if ev['cid'] not in cid_title: cid_title[ev['cid']] = ev.get('title')
for k in sorted(unres_legs, key=lambda x: -leg_rebuy_usd[x])[:10]:
    print(f"  {cid_title.get(k[0],'?')[:60]:<60}  inv=${leg_rebuy_usd[k]:.2f}")

# By price bucket — resolved-only
print('\nResolved rebuy events by price bucket:')
bucket_pnl = defaultdict(lambda: {'n':0,'usd':0,'pnl':0,'w':0,'l':0})
for ev in ev_resolved:
    b = ev['price_bucket']
    roi = res_map[(ev['cid'], ev['token'])][1]
    bucket_pnl[b]['n'] += 1
    bucket_pnl[b]['usd'] += ev['rebuy_usd']
    bucket_pnl[b]['pnl'] += ev['rebuy_usd'] * roi
    if roi > 0: bucket_pnl[b]['w'] += 1
    else: bucket_pnl[b]['l'] += 1
for b in ['0.00-0.15','0.15-0.30','0.30-0.70','0.70-0.85','0.85-0.99']:
    r = bucket_pnl.get(b, {'n':0,'usd':0,'pnl':0,'w':0,'l':0})
    wr = r['w']/(r['w']+r['l']) if (r['w']+r['l']) else 0
    ev_per = r['pnl']/r['usd'] if r['usd']>0 else 0
    print(f"  {b}  n={r['n']:>3}  usd={r['usd']:>7.2f}  W/L={r['w']}/{r['l']}  WR={wr*100:>5.1f}%  pnl={r['pnl']:+.2f}  ev/usd={ev_per:+.3f}")
