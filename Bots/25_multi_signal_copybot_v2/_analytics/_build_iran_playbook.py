"""Build support/resistance, event impact, triggers, backtest from fetched data."""
import json, os, statistics
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'iran_range_data.json')
OUT = os.path.join(HERE, 'iran_playbook_built.json')

with open(DATA, 'r', encoding='utf-8') as f:
    markets = json.load(f)

# Known events (UTC midnight timestamps, will check +/- 2h window)
EVENTS = [
    ('2026-04-12', 'islamabad_talks_failed', 'hawkish'),
    ('2026-04-13', 'us_blockade_begins', 'hawkish'),
    ('2026-04-15', 'pentagon_blockade_working', 'hawkish'),
    ('2026-04-17', 'iran_hormuz_open_declared', 'mixed'),
    ('2026-04-18', 'iran_closes_hormuz_fires', 'hawkish'),
    ('2026-04-19', 'touska_seized', 'hawkish'),
    ('2026-04-20', 'pentagon_policy_indo_pacific', 'hawkish'),
    ('2026-04-21', 'tifani_seized', 'hawkish'),
]

def iso_to_ts(s):
    return int(datetime.fromisoformat(s+'T12:00:00+00:00').timestamp())

EVENT_TS = [(iso_to_ts(d), name, kind) for d, name, kind in EVENTS]

def support_resistance(prices_side):
    """Find levels where price bounced >=3x. Round to nearest 2¢."""
    if len(prices_side) < 20:
        return [], []
    rounded = [round(p*50)/50 for p in prices_side]  # 2¢ buckets
    # find local minima (3-point) and local maxima
    minima = []
    maxima = []
    for i in range(2, len(prices_side)-2):
        window = prices_side[i-2:i+3]
        if prices_side[i] == min(window):
            minima.append(rounded[i])
        if prices_side[i] == max(window):
            maxima.append(rounded[i])
    # count occurrences
    from collections import Counter
    min_c = Counter(minima)
    max_c = Counter(maxima)
    supports = sorted([p for p, c in min_c.items() if c >= 3])
    resists = sorted([p for p, c in max_c.items() if c >= 3], reverse=True)
    return supports[:3], resists[:3]

def event_impact(history_full, outcome):
    """For each event, compute move in first 2h after event_ts."""
    if not history_full or len(history_full) < 5:
        return {}
    out = {}
    for ev_ts, name, kind in EVENT_TS:
        # find price just before event and 2h after
        pre = None; post = None
        for h in history_full:
            t = h.get('t', 0)
            if t <= ev_ts:
                pre = h
            elif t <= ev_ts + 7200 and pre is not None:
                post = h
                break
        if pre and post:
            p_pre = float(pre['p']); p_post = float(post['p'])
            if outcome == 'No':
                p_pre = 1 - p_pre; p_post = 1 - p_post
            move = (p_post - p_pre) * 100  # in percentage points
            out[name] = round(move, 2)
    return out

def backtest(history_full, outcome, support, resistance, median):
    """Simulate: BUY when price <= 0.95*median (i.e. 5% below median), SELL when price >= 1.05*median.
    Apply 2% slippage. Track cycles."""
    if not history_full or len(history_full) < 20:
        return None
    prices = []
    for h in history_full:
        p = float(h['p'])
        if outcome == 'No':
            p = 1 - p
        prices.append(p)
    buy_thr = median * 0.92  # 8% below median (min edge)
    sell_thr = median * 1.08  # 8% above median
    pnl = 0.0
    position = 0  # 0 = flat, 1 = long
    entries = 0; exits = 0
    entry_price = 0
    SLIP = 0.02
    for p in prices:
        if position == 0 and p <= buy_thr:
            entry_price = p * (1 + SLIP/2)  # pay slip up on buy
            position = 1
            entries += 1
        elif position == 1 and p >= sell_thr:
            exit_price = p * (1 - SLIP/2)  # get slip down on sell
            pnl += (exit_price - entry_price)  # per share
            position = 0
            exits += 1
    # if still holding, mark to last
    if position == 1:
        pnl += (prices[-1]*(1-SLIP/2) - entry_price)
    # scale by $25 bet -> shares = 25/entry
    # we'll just report pnl per $1 of buy
    return dict(entries=entries, exits=exits, pnl_per_share=round(pnl, 4))

def classify_zone(current, p_min, p_max, median):
    if p_max <= p_min:
        return 'flat'
    rel = (current - p_min) / (p_max - p_min)
    if rel < 0.20:
        return 'near_support'
    if rel > 0.80:
        return 'near_resistance'
    return 'mid_range'

for m in markets:
    stats = m.get('stats')
    if not stats or not m.get('history'):
        m['triggers'] = None
        continue
    history = m['history']
    outcome = m.get('outcome')
    prices_side = [(1-float(h['p'])) if outcome=='No' else float(h['p']) for h in history]
    sup, res = support_resistance(prices_side)
    imp = event_impact(history, outcome)
    bt = backtest(history, outcome, sup, res, stats['median'])
    zone = classify_zone(stats['current'], stats['min'], stats['max'], stats['median'])
    m['supports'] = sup
    m['resistances'] = res
    m['event_impact_pp'] = imp
    m['backtest'] = bt
    m['zone'] = zone
    # triggers
    median = stats['median']
    m['buy_trigger'] = round(median * 0.92, 3)
    m['sell_trigger'] = round(median * 1.08, 3)
    m['extreme_buy'] = round(stats['min'] + (stats['max']-stats['min'])*0.15, 3)
    m['extreme_sell'] = round(stats['min'] + (stats['max']-stats['min'])*0.85, 3)
    # current state
    curr = stats['current']
    if curr <= m['buy_trigger']:
        m['state'] = 'BUY_TRIGGER_HIT'
    elif curr >= m['sell_trigger']:
        m['state'] = 'SELL_TRIGGER_HIT'
    else:
        m['state'] = 'WAIT'

# Strip heavy history from output but keep stats
for m in markets:
    if 'history' in m:
        del m['history']

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(markets, f, indent=2, ensure_ascii=False)

# Summary
print('='*80)
print('TOP 5 BY VOLATILITY SCORE (stdev/median)')
print('='*80)
sorted_vol = sorted([m for m in markets if m.get('stats')],
                     key=lambda m: m['stats']['vol_score'], reverse=True)
for m in sorted_vol[:5]:
    s = m['stats']
    print(f"{m['outcome']:3} | {m['title'][:70]:70} | vol={s['vol_score']:.3f} | "
          f"range={s['min']:.2f}-{s['max']:.2f} | curr={s['current']:.3f} | {m.get('state')}")

print()
print('CURRENT BUY TRIGGERS HIT:')
for m in markets:
    if m.get('state') == 'BUY_TRIGGER_HIT':
        print(f"  {m['outcome']} | {m['title'][:70]} | curr={m['stats']['current']:.3f} <= buy={m['buy_trigger']}")
print()
print('CURRENT SELL TRIGGERS HIT:')
for m in markets:
    if m.get('state') == 'SELL_TRIGGER_HIT':
        print(f"  {m['outcome']} | {m['title'][:70]} | curr={m['stats']['current']:.3f} >= sell={m['sell_trigger']}")

# total edge estimate: sum pnl_per_share * (typical $25 bet / entry)
total_edge = 0
for m in markets:
    bt = m.get('backtest')
    if not bt: continue
    entry = m['stats']['median'] * 0.92
    if entry <= 0: continue
    shares_per_bet = 25 / entry
    total_edge += bt['pnl_per_share'] * shares_per_bet
print(f'\n20d backtest total edge (portfolio, $25/cycle): ${total_edge:.2f}')
print(f'Extrapolated 30d edge: ${total_edge * 30/20:.2f}')
