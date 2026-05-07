"""Portfolio audit: analyze every open position and recommend actions."""
import sys, io, json, os, time, requests
from datetime import datetime, timezone
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv('../98_sure_bot/.env')
W = os.getenv('POLYMARKET_WALLET','').lower()

PLAYERS = {
    'Car':    '0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b',
    'aenews2':'0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1',
    'denizz': '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73',
}

BANKROLL = 2000.0
RESERVE = 150.0
MAX_CONCURRENT = 40

# Load tracker
with open('positions.json', encoding='utf-8') as f:
    data = json.load(f)

# On-chain positions
print('Fetching on-chain positions...')
r = requests.get('https://data-api.polymarket.com/positions',
    params={'user':W,'limit':500,'sizeThreshold':0}, timeout=20)
onchain = {(p.get('conditionId',''), p.get('asset','')): p for p in r.json()}

# USDC balance
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('https://polygon.drpc.org'))
USDC = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
abi = [{'inputs':[{'name':'account','type':'address'}],'name':'balanceOf','outputs':[{'name':'','type':'uint256'}],'stateMutability':'view','type':'function'}]
c = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=abi)
usdc_balance = c.functions.balanceOf(Web3.to_checksum_address(W)).call() / 1e6

# Player position cache — fetch per cid
player_cache = {}
def get_player_pos(player_name, cid, token):
    key = (player_name, cid, token)
    if key in player_cache:
        return player_cache[key]
    wallet = PLAYERS.get(player_name)
    if not wallet:
        player_cache[key] = None
        return None
    try:
        rr = requests.get('https://data-api.polymarket.com/positions',
            params={'user':wallet,'market':cid,'sizeThreshold':0}, timeout=15)
        if rr.ok:
            for p in rr.json():
                if p.get('asset','')==token:
                    player_cache[key] = p
                    return p
                # same outcome — maybe player is on opposite side
            # not found on same token
            all_on_market = [p for p in rr.json() if p.get('conditionId','')==cid]
            player_cache[key] = {'_on_other_side': all_on_market}
            return player_cache[key]
    except Exception as e:
        pass
    player_cache[key] = None
    return None

# Market info cache
market_cache = {}
def get_market_info(cid):
    if cid in market_cache: return market_cache[cid]
    try:
        rr = requests.get(f'https://clob.polymarket.com/markets/{cid}', timeout=10)
        if rr.ok:
            market_cache[cid] = rr.json()
            return market_cache[cid]
    except: pass
    market_cache[cid] = None
    return None

# Analyze each open position
opens = []
for oid, p in data.get('positions',{}).items():
    if p.get('status') not in ('open','filled'): continue
    opens.append((oid, p))

print(f'Open positions: {len(opens)}')
print(f'USDC balance: ${usdc_balance:.2f}')
print(f'Fetching player data...')

audits = []
now_ts = datetime.now(timezone.utc)
for oid, p in opens:
    cid = p.get('condition_id','')
    tok = p.get('token_id','')
    sp = p.get('signal_player','') or 'unknown'
    title = p.get('title','')[:55]
    outcome = p.get('outcome','')

    # Tracker values
    tracker_shares = float(p.get('size_shares',0) or 0)
    cost = float(p.get('cost_usd',0) or 0)
    our_avg = float(p.get('avg_entry') or p.get('entry_price',0) or 0)
    ts_str = p.get('timestamp','')
    tier = p.get('tier','?')
    manual_hold = p.get('manual_hold', False)

    # On-chain
    oc = onchain.get((cid, tok))
    oc_shares = float(oc.get('size',0) or 0) if oc else 0
    cur_price = float(oc.get('curPrice',0) or 0) if oc else 0
    cashPnl_api = float(oc.get('cashPnl',0) or 0) if oc else 0
    end_date = oc.get('endDate','') if oc else ''

    # Calc PnL
    cur_val = tracker_shares * cur_price if cur_price else 0
    unr_pnl = tracker_shares * (cur_price - our_avg) if (cur_price and our_avg and tracker_shares) else 0

    # Drift detection
    drift = abs(tracker_shares - oc_shares)

    # Player state
    player_pos = get_player_pos(sp, cid, tok) if sp in PLAYERS else None
    player_active = False
    player_avg = 0
    player_size = 0
    player_opposite = 0
    if player_pos and not player_pos.get('_on_other_side'):
        player_size = float(player_pos.get('size',0) or 0)
        player_avg = float(player_pos.get('avgPrice',0) or 0)
        player_active = player_size > 0.1
    elif player_pos and player_pos.get('_on_other_side'):
        # player is ON OPPOSITE side
        for pp in player_pos['_on_other_side']:
            if pp.get('outcome','').lower() != outcome.lower():
                player_opposite = float(pp.get('size',0) or 0)

    # Mult
    mult = our_avg / player_avg if player_avg > 0 else 0

    # Days to resolution
    days_to_resolve = None
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z','+00:00'))
            days_to_resolve = (end_dt - now_ts).total_seconds() / 86400
        except: pass

    # Days since entry
    days_held = None
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z','+00:00'))
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
            days_held = (now_ts - ts).total_seconds() / 86400
        except: pass

    # Decision logic
    action = ''
    reason = ''

    # Priority 1: drift
    if drift > 1.0 and oc:
        action = 'RECONCILE'
        reason = f'tracker={tracker_shares:.1f} vs on-chain={oc_shares:.1f}'
    # Priority 2: player dead
    elif sp in PLAYERS and not player_active and player_size == 0 and player_opposite == 0:
        action = 'SELL FULL'
        reason = f'{sp} no longer holds — signal dead'
    # Priority 3: player on OPPOSITE side
    elif player_opposite > 100:
        action = 'SELL FULL'
        reason = f'{sp} now on OPPOSITE side ({player_opposite:.0f} sh)'
    # Priority 4: our PnL is big profit (>30%)
    elif cost > 0 and unr_pnl / cost > 0.30:
        action = 'SELL PARTIAL 50%'
        reason = f'locked gain +{unr_pnl/cost*100:.0f}% on {cost:.0f}'
    # Priority 5: big drawdown (>40%) + player also in loss
    elif cost > 0 and unr_pnl / cost < -0.40 and player_avg > cur_price:
        action = 'HOLD (deep loss)'
        reason = f'-{abs(unr_pnl/cost*100):.0f}%, but {sp} also underwater'
    # Priority 6: resolution imminent (<2d) + in profit
    elif days_to_resolve is not None and days_to_resolve < 2 and unr_pnl > 5:
        action = 'HOLD TO RESOLVE'
        reason = f'{days_to_resolve:.1f}d to resolve, +${unr_pnl:.0f}'
    # Priority 7: manual_hold respect
    elif manual_hold:
        action = 'HOLD (manual flag)'
        reason = p.get('manual_hold_reason', 'user-set hold')
    # Default
    elif player_active and mult > 0 and mult <= 1.3:
        action = 'HOLD'
        reason = f'on-time entry (mult {mult:.2f}x), {sp} still in'
    elif player_active and mult > 1.5:
        action = 'HOLD + MONITOR'
        reason = f'late entry mult {mult:.1f}x, {sp} in but we overpaid'
    else:
        action = 'HOLD'
        reason = 'normal state'

    audits.append({
        'oid': oid[:14], 'title': title, 'sp': sp, 'outcome': outcome,
        'tracker_shares': tracker_shares, 'oc_shares': oc_shares, 'drift': drift,
        'cost': cost, 'our_avg': our_avg, 'cur_price': cur_price,
        'cur_val': cur_val, 'unr_pnl': unr_pnl,
        'player_size': player_size, 'player_avg': player_avg,
        'player_opposite': player_opposite, 'mult': mult,
        'days_held': days_held, 'days_to_resolve': days_to_resolve,
        'tier': tier, 'manual_hold': manual_hold,
        'action': action, 'reason': reason,
        'end_date': end_date,
    })

# Totals
total_cost = sum(a['cost'] for a in audits)
total_unr = sum(a['unr_pnl'] for a in audits)
total_cur_val = sum(a['cur_val'] for a in audits)

# Drift / zombie analysis
drifting = [a for a in audits if a['drift'] > 1.0]
dead_signals = [a for a in audits if a['action'] == 'SELL FULL' and 'no longer holds' in a['reason']]
opposite = [a for a in audits if 'OPPOSITE' in a['reason']]

# Concentration
by_topic = defaultdict(lambda: {'n':0, 'cost':0, 'pnl':0})
for a in audits:
    topic = 'Iran' if any(k in a['title'].lower() for k in ['iran','israel','hezbollah','yemen','hamas','houthi','hormuz','gaza','tehran','khamenei','netanyahu','pahlavi']) else 'other'
    by_topic[topic]['n'] += 1
    by_topic[topic]['cost'] += a['cost']
    by_topic[topic]['pnl'] += a['unr_pnl']

# Write report
lines = []
lines.append(f'# Portfolio audit — {now_ts.strftime("%Y-%m-%d %H:%M UTC")}')
lines.append('')
lines.append('## Executive Summary')
lines.append('')
lines.append(f'- **Open positions:** {len(audits)} / max {MAX_CONCURRENT}')
lines.append(f'- **Total cost basis:** ${total_cost:,.2f}')
lines.append(f'- **Current value:** ${total_cur_val:,.2f}')
lines.append(f'- **Unrealized PnL:** ${total_unr:+,.2f} ({total_unr/total_cost*100 if total_cost>0 else 0:+.1f}%)')
lines.append(f'- **USDC free:** ${usdc_balance:.2f} (reserve ${RESERVE})')
lines.append(f'- **Free for new bets:** ${max(0, usdc_balance - RESERVE):.2f}')
lines.append(f'- **Bankroll utilization:** {total_cost/BANKROLL*100:.0f}% ({total_cost:.0f}/{BANKROLL:.0f})')
lines.append('')
lines.append('### Actions required')
lines.append(f'- 🔴 Drift (tracker≠on-chain): **{len(drifting)}**')
lines.append(f'- 💀 Dead signals (player exited): **{len(dead_signals)}**')
lines.append(f'- ⚠️ Player flipped to opposite: **{len(opposite)}**')
lock_wins = [a for a in audits if 'locked gain' in a['reason']]
lines.append(f'- 💰 Profit-taking candidates: **{len(lock_wins)}**')
lines.append('')

lines.append('## Concentration by theme')
lines.append('')
lines.append('| Theme | N | Cost | PnL |')
lines.append('|-------|---|------|-----|')
for topic, s in sorted(by_topic.items(), key=lambda x:-x[1]['cost']):
    lines.append(f'| {topic} | {s["n"]} | ${s["cost"]:,.0f} | ${s["pnl"]:+,.0f} |')
lines.append('')

lines.append('## Per-position audit')
lines.append('')
lines.append('| # | OID | Player | Out | Cost | Cur | Unr | Mult | Days | Action | Reason | Title |')
lines.append('|---|-----|--------|-----|------|-----|-----|------|------|--------|--------|-------|')
audits.sort(key=lambda a: -a['cost'])
for i, a in enumerate(audits, 1):
    days_s = f'{a["days_held"]:.1f}' if a['days_held'] else '-'
    mult_s = f'{a["mult"]:.2f}x' if a['mult'] else '-'
    lines.append(f"| {i} | {a['oid']} | {a['sp']} | {a['outcome']} | ${a['cost']:.0f} | {a['cur_price']:.3f} | ${a['unr_pnl']:+.1f} | {mult_s} | {days_s} | **{a['action']}** | {a['reason'][:35]} | {a['title']} |")
lines.append('')

lines.append('## Actionable items (priority order)')
lines.append('')
priority_actions = [a for a in audits if a['action'] in ('RECONCILE','SELL FULL','SELL PARTIAL 50%')]
if priority_actions:
    for i, a in enumerate(priority_actions, 1):
        lines.append(f'{i}. **{a["action"]}** — {a["title"]}')
        lines.append(f'   - Cost ${a["cost"]:.0f}, Unr PnL ${a["unr_pnl"]:+.1f}, Player: {a["sp"]} ({a["player_size"]:.0f} sh, avg ${a["player_avg"]:.3f})')
        lines.append(f'   - Reason: {a["reason"]}')
        lines.append('')
else:
    lines.append('No urgent actions.')
    lines.append('')

# Risk budget
max_loss = sum(a['cost'] for a in audits)  # everything resolves No
lines.append('## Risk budget')
lines.append('')
lines.append(f'- **Max loss if all wrong:** -${max_loss:.0f} ({max_loss/BANKROLL*100:.0f}% of bankroll)')
lines.append(f'- **Current unrealized:** ${total_unr:+.0f}')
lines.append(f'- **Free cash + positions value:** ${usdc_balance + total_cur_val:,.2f}')
lines.append('')

report_path = '_analytics/2026-04-09_portfolio-audit.md'
with open(report_path,'w',encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'\nReport: {report_path}')
print(f'Positions: {len(audits)}')
print(f'Total cost: ${total_cost:.2f}  unr: ${total_unr:+.2f}')
print(f'Actions: {len([a for a in audits if a["action"] not in ("HOLD","HOLD (normal state)","HOLD + MONITOR","HOLD TO RESOLVE","HOLD (manual flag)","HOLD (deep loss)")])} non-hold')
