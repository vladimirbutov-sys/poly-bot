"""
Full historical backtest of Denizz trader: bet sizing ratio analysis.
Fetches ALL trades, resolves market outcomes via CLOB API, reconstructs
positions with correct PnL (including resolution payouts).

Output: _analytics/2026-04-11_denizz-full-backtest.md
"""
import sys
import io
import os
import json
import time
import math
import requests
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from statistics import median

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DENIZZ = '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73'
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_analytics', 'data')
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_analytics', '2026-04-11_denizz-full-backtest.md')
os.makedirs(DATA_DIR, exist_ok=True)

NOW = int(datetime.now(timezone.utc).timestamp())

# ============ FETCH ============

def fetch_paginated(endpoint, params_extra, cache_file=None, max_records=50000):
    if cache_file:
        path = os.path.join(DATA_DIR, cache_file)
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            if NOW - mtime < 1800:
                print(f'  [cache hit] {cache_file}')
                with open(path, encoding='utf-8') as f:
                    return json.load(f)
    out = []
    off = 0
    while True:
        p = {'user': DENIZZ, 'limit': 500, 'offset': off}
        p.update(params_extra)
        try:
            r = requests.get(f'https://data-api.polymarket.com/{endpoint}',
                             params=p, timeout=30)
        except Exception as e:
            print(f'  network err at offset {off}: {e}')
            break
        if not r.ok:
            print(f'  HTTP {r.status_code} at offset {off}')
            break
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        print(f'  {endpoint}: fetched {len(out)} records (offset {off})...')
        if len(batch) < 500:
            break
        off += 500
        if len(out) >= max_records:
            break
        time.sleep(0.3)
    if cache_file and out:
        with open(os.path.join(DATA_DIR, cache_file), 'w', encoding='utf-8') as f:
            json.dump(out, f)
    return out


def fetch_market_resolution(condition_id):
    """Fetch resolution data from CLOB API. Returns dict with winner outcome."""
    try:
        r = requests.get(f'https://clob.polymarket.com/markets/{condition_id}', timeout=15)
        if r.ok:
            data = r.json()
            tokens = data.get('tokens', [])
            closed = data.get('closed', False)
            for tok in tokens:
                if tok.get('winner'):
                    return {
                        'resolved': True,
                        'closed': closed,
                        'winning_outcome': tok.get('outcome', ''),
                        'tokens': tokens,
                    }
            # Market is closed but no winner yet or resolved to No for all
            if closed:
                return {'resolved': True, 'closed': True, 'winning_outcome': None, 'tokens': tokens}
            return {'resolved': False, 'closed': closed, 'winning_outcome': None, 'tokens': tokens}
    except Exception as e:
        pass
    return None


print('='*60)
print('DENIZZ FULL BACKTEST - Fetching ALL historical data')
print('='*60)

print('\n[1/3] Fetching ALL trades...')
all_trades = fetch_paginated('trades', {}, cache_file='denizz_trades_ALL.json', max_records=50000)
print(f'  => Total trades: {len(all_trades)}')

print('\n[2/3] Fetching current open positions...')
positions = fetch_paginated('positions', {'sizeThreshold': 0}, cache_file='denizz_positions_ALL.json', max_records=5000)
print(f'  => Total open positions: {len(positions)}')

# ============ PARSE HELPERS ============

def parse_usd(trade):
    try:
        return float(trade.get('price', 0)) * float(trade.get('size', 0))
    except:
        return 0.0

def parse_ts(trade):
    ts = trade.get('timestamp') or trade.get('createdAt') or '0'
    try:
        if isinstance(ts, (int, float)):
            return int(ts)
        if 'T' in str(ts):
            dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
            return int(dt.timestamp())
        return int(ts)
    except:
        return 0

# Sort all trades chronologically
all_trades.sort(key=lambda t: parse_ts(t))

if all_trades:
    first_ts = parse_ts(all_trades[0])
    last_ts = parse_ts(all_trades[-1])
    first_dt = datetime.fromtimestamp(first_ts, tz=timezone.utc)
    last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
    days_span = (last_ts - first_ts) / 86400
    print(f'\n  Date range: {first_dt:%Y-%m-%d} to {last_dt:%Y-%m-%d} ({days_span:.0f} days)')

# ============ BUILD PER-MARKET TRADE DATA ============

def get_cid(t):
    return t.get('conditionId') or ''

def get_side(t):
    s = (t.get('side') or '').upper()
    return 'BUY' if s == 'BUY' else 'SELL'

def get_price(t):
    try:
        return float(t.get('price', 0))
    except:
        return 0.0

def get_outcome(t):
    return str(t.get('outcome') or t.get('outcomeIndex') or '')

# Group trades by (conditionId, outcome)
market_trades = defaultdict(list)
for t in all_trades:
    cid = get_cid(t)
    if not cid:
        continue
    outcome = get_outcome(t)
    market_trades[(cid, outcome)].append(t)

print(f'\n  Unique market-outcome pairs: {len(market_trades)}')

# Build open positions index
open_pos = {}
for p in positions:
    cid = p.get('conditionId') or ''
    outcome = str(p.get('outcome') or '')
    key = (cid, outcome)
    try:
        size = float(p.get('size', 0))
    except:
        size = 0
    try:
        cur_price = float(p.get('curPrice') or p.get('price') or 0)
    except:
        cur_price = 0
    open_pos[key] = {
        'size': size,
        'cur_price': cur_price,
        'title': p.get('title') or p.get('groupTitle') or '',
        'cur_value': size * cur_price,
    }

print(f'  Open positions with data: {len(open_pos)}')

# ============ FETCH RESOLUTION DATA FOR CLOSED POSITIONS ============

# Collect unique conditionIds that are NOT in open positions
unique_cids = set()
for (cid, outcome) in market_trades.keys():
    unique_cids.add(cid)

open_cids = set(p.get('conditionId','') for p in positions)
closed_cids = unique_cids - open_cids

print(f'\n[3/3] Fetching resolution data for {len(closed_cids)} closed markets...')

# Cache resolution data
resolution_cache_file = os.path.join(DATA_DIR, 'denizz_resolutions.json')
resolution_data = {}
if os.path.exists(resolution_cache_file):
    mtime = os.path.getmtime(resolution_cache_file)
    if NOW - mtime < 3600:
        with open(resolution_cache_file, encoding='utf-8') as f:
            resolution_data = json.load(f)
        print(f'  [cache hit] {len(resolution_data)} resolutions cached')

need_fetch = [cid for cid in closed_cids if cid not in resolution_data]
print(f'  Need to fetch: {len(need_fetch)} markets')

for i, cid in enumerate(need_fetch):
    res = fetch_market_resolution(cid)
    if res:
        resolution_data[cid] = res
    else:
        resolution_data[cid] = {'resolved': False, 'closed': False, 'winning_outcome': None}
    if (i + 1) % 50 == 0:
        print(f'    ... fetched {i+1}/{len(need_fetch)}')
    time.sleep(0.15)

# Save cache
with open(resolution_cache_file, 'w', encoding='utf-8') as f:
    json.dump(resolution_data, f)

resolved_yes = sum(1 for v in resolution_data.values() if v.get('winning_outcome'))
print(f'  Markets with known winner: {resolved_yes}')

# ============ RECONSTRUCT PER-MARKET PnL ============

class MarketPosition:
    def __init__(self, key, trades):
        self.cid = key[0]
        self.outcome = key[1]
        self.trades = sorted(trades, key=lambda t: parse_ts(t))

        self.total_bought_usd = 0.0
        self.total_sold_usd = 0.0
        self.total_bought_shares = 0.0
        self.total_sold_shares = 0.0
        self.buy_prices = []
        self.sell_prices = []
        self.buy_events = []
        self.title = ''

        self.first_ts = parse_ts(self.trades[0]) if self.trades else 0
        self.last_ts = parse_ts(self.trades[-1]) if self.trades else 0

        cumulative_bought = 0.0

        for t in self.trades:
            side = get_side(t)
            usd = parse_usd(t)
            price = get_price(t)
            shares = float(t.get('size', 0))
            if not self.title:
                self.title = t.get('title', '')

            if side == 'BUY':
                self.total_bought_usd += usd
                self.total_bought_shares += shares
                self.buy_prices.append((price, usd))
                self.buy_events.append({
                    'ts': parse_ts(t),
                    'usd': usd,
                    'price': price,
                    'cumulative_before': cumulative_bought,
                })
                cumulative_bought += usd
            else:
                self.total_sold_usd += usd
                self.total_sold_shares += shares
                self.sell_prices.append((price, usd))

        self.net_shares = self.total_bought_shares - self.total_sold_shares
        self.peak_position_usd = cumulative_bought

        # Is position still open?
        self.is_open = (self.cid, self.outcome) in open_pos

        # Current value if open
        if self.is_open:
            op = open_pos[(self.cid, self.outcome)]
            self.current_value = op['cur_value']
            if op.get('title'):
                self.title = op['title']
        else:
            self.current_value = 0.0

        # For closed positions with remaining shares, check resolution
        self.resolution_payout = 0.0
        self.resolution_status = 'unknown'
        if not self.is_open and self.net_shares > 0.5:
            res = resolution_data.get(self.cid, {})
            winning_outcome = res.get('winning_outcome', '')
            if winning_outcome:
                # Check if Denizz's outcome matches the winner
                denizz_outcome = self.outcome.lower().strip()
                winner = winning_outcome.lower().strip()
                if denizz_outcome == winner or \
                   (denizz_outcome in ('yes', '1', 'true') and winner in ('yes', '1', 'true')) or \
                   (denizz_outcome in ('no', '0', 'false') and winner in ('no', '0', 'false')):
                    # Won! Payout = net_shares * $1
                    self.resolution_payout = self.net_shares
                    self.resolution_status = 'won'
                else:
                    # Lost. Payout = $0
                    self.resolution_payout = 0.0
                    self.resolution_status = 'lost'
            elif res.get('closed') or res.get('resolved'):
                # Market closed but no winner found - likely resolved No
                self.resolution_status = 'lost'
            else:
                self.resolution_status = 'unknown'

        # PnL = sold + current_value + resolution_payout - bought
        self.net_pnl = (self.total_sold_usd + self.current_value +
                        self.resolution_payout - self.total_bought_usd)

        # ROI
        if self.total_bought_usd > 0:
            self.roi = self.net_pnl / self.total_bought_usd
        else:
            self.roi = 0.0

        # Average buy price (USD-weighted)
        total_w = sum(w for _, w in self.buy_prices)
        if total_w > 0:
            self.avg_buy_price = sum(p * w for p, w in self.buy_prices) / total_w
        else:
            self.avg_buy_price = 0

        # Average sell price
        total_sw = sum(w for _, w in self.sell_prices)
        if total_sw > 0:
            self.avg_sell_price = sum(p * w for p, w in self.sell_prices) / total_sw
        else:
            self.avg_sell_price = 0

        self.is_winner = self.net_pnl > 0


# Build all positions
all_positions = []
for key, trades in market_trades.items():
    if not trades:
        continue
    mp = MarketPosition(key, trades)
    if mp.total_bought_usd < 0.5:
        continue
    all_positions.append(mp)

all_positions.sort(key=lambda p: p.first_ts)

print(f'\n  Positions reconstructed: {len(all_positions)}')
open_count = sum(1 for p in all_positions if p.is_open)
closed_count = len(all_positions) - open_count
print(f'  Open: {open_count}, Closed: {closed_count}')

# Resolution stats
res_won = sum(1 for p in all_positions if p.resolution_status == 'won')
res_lost = sum(1 for p in all_positions if p.resolution_status == 'lost')
res_unknown = sum(1 for p in all_positions if p.resolution_status == 'unknown' and not p.is_open)
print(f'  Resolution: won={res_won}, lost={res_lost}, unknown={res_unknown}')

total_pnl = sum(p.net_pnl for p in all_positions)
total_bought = sum(p.total_bought_usd for p in all_positions)
total_sold = sum(p.total_sold_usd for p in all_positions)
total_current = sum(p.current_value for p in all_positions)
total_resolution = sum(p.resolution_payout for p in all_positions)
winners = sum(1 for p in all_positions if p.is_winner)
losers = sum(1 for p in all_positions if p.net_pnl < 0)
breakeven = len(all_positions) - winners - losers

print(f'\n  Total bought:     ${total_bought:,.2f}')
print(f'  Total sold:       ${total_sold:,.2f}')
print(f'  Open value:       ${total_current:,.2f}')
print(f'  Resolution payout:${total_resolution:,.2f}')
print(f'  Net PnL:          ${total_pnl:,.2f}')
print(f'  Winners: {winners}, Losers: {losers}, Breakeven: {breakeven}')
if all_positions:
    print(f'  Win rate: {winners/len(all_positions)*100:.1f}%')

# ============ CUMULATIVE PORTFOLIO TIMELINE ============

timeline = []
for mp in all_positions:
    for t in mp.trades:
        side = get_side(t)
        usd = parse_usd(t)
        ts = parse_ts(t)
        timeline.append((ts, side, usd, mp.cid, mp.outcome))

timeline.sort(key=lambda x: x[0])

active_capital = defaultdict(float)
deployed_at_time = {}
peak_deployed = 0.0

for ts, side, usd, cid, outcome in timeline:
    key = (cid, outcome)
    if side == 'BUY':
        active_capital[key] += usd
    else:
        active_capital[key] = max(0, active_capital[key] - usd)
    total_active = sum(active_capital.values())
    deployed_at_time[ts] = total_active
    peak_deployed = max(peak_deployed, total_active)

print(f'  Peak capital deployed: ${peak_deployed:,.2f}')

# Compute ratio for each position
for mp in all_positions:
    if mp.buy_events:
        first_buy_ts = mp.buy_events[0]['ts']
        portfolio_at_entry = deployed_at_time.get(first_buy_ts, 0)
        first_buy_usd = mp.buy_events[0]['usd']
        portfolio_before = max(portfolio_at_entry - first_buy_usd, 0)
        if portfolio_before > 0:
            mp.ratio = mp.total_bought_usd / portfolio_before
        else:
            mp.ratio = 999.0
        mp.portfolio_at_entry = portfolio_before if portfolio_before > 0 else mp.total_bought_usd
    else:
        mp.ratio = 0
        mp.portfolio_at_entry = 0

# ============ ANALYSIS TABLES ============

def wr(pos_list):
    if not pos_list:
        return 0
    return sum(1 for p in pos_list if p.is_winner) / len(pos_list) * 100

def avg_roi(pos_list):
    if not pos_list:
        return 0
    return sum(p.roi for p in pos_list) / len(pos_list) * 100

def med_roi(pos_list):
    if not pos_list:
        return 0
    return median(p.roi for p in pos_list) * 100

def total_pnl_f(pos_list):
    return sum(p.net_pnl for p in pos_list)

# TABLE A: Ratio buckets
ratio_buckets = [
    ('< 5%', 0, 0.05),
    ('5-15%', 0.05, 0.15),
    ('15-30%', 0.15, 0.30),
    ('30-50%', 0.30, 0.50),
    ('50-80%', 0.50, 0.80),
    ('80-100%', 0.80, 1.00),
    ('> 100%', 1.00, 9999),
]

print('\n\n=== TABLE A: Ratio Buckets vs Outcomes ===')
print(f'{"Ratio":<12} {"Count":>6} {"WR%":>7} {"AvgROI%":>9} {"MedROI%":>9} {"TotalPnL":>12}')
print('-'*58)
table_a_rows = []
for label, lo, hi in ratio_buckets:
    grp = [p for p in all_positions if lo <= p.ratio < hi]
    row = (label, len(grp), wr(grp), avg_roi(grp), med_roi(grp), total_pnl_f(grp)) if grp else (label, 0, 0, 0, 0, 0)
    table_a_rows.append(row)
    print(f'{row[0]:<12} {row[1]:>6} {row[2]:>7.1f} {row[3]:>9.1f} {row[4]:>9.1f} ${row[5]:>11,.2f}')

# TABLE B: Portfolio size buckets
portfolio_buckets_full = [
    ('< $100', 0, 100),
    ('$100-500', 100, 500),
    ('$500-2K', 500, 2000),
    ('$2K-5K', 2000, 5000),
    ('$5K-20K', 5000, 20000),
    ('$20K-50K', 20000, 50000),
    ('$50K-100K', 50000, 100000),
    ('$100K+', 100000, 99999999),
]

print('\n\n=== TABLE B: Portfolio Size at Entry vs Outcomes ===')
print(f'{"Portfolio":<14} {"Count":>6} {"WR%":>7} {"AvgROI%":>9} {"MedROI%":>9} {"TotalPnL":>12}')
print('-'*60)
table_b_rows = []
for label, lo, hi in portfolio_buckets_full:
    grp = [p for p in all_positions if lo <= p.portfolio_at_entry < hi]
    row = (label, len(grp), wr(grp), avg_roi(grp), med_roi(grp), total_pnl_f(grp)) if grp else (label, 0, 0, 0, 0, 0)
    table_b_rows.append(row)
    print(f'{row[0]:<14} {row[1]:>6} {row[2]:>7.1f} {row[3]:>9.1f} {row[4]:>9.1f} ${row[5]:>11,.2f}')

# TABLE C: Price tier
price_tiers = [
    ('2-15c', 0.02, 0.15),
    ('15-50c', 0.15, 0.50),
    ('50-82c', 0.50, 0.82),
    ('82-95c', 0.82, 0.95),
    ('95-99c', 0.95, 0.99),
]

print('\n\n=== TABLE C: Buy Price Tier vs Outcomes ===')
print(f'{"Price":<10} {"Count":>6} {"WR%":>7} {"AvgROI%":>9} {"TotalPnL":>12}')
print('-'*48)
table_c_rows = []
for label, lo, hi in price_tiers:
    grp = [p for p in all_positions if lo <= p.avg_buy_price < hi]
    row = (label, len(grp), wr(grp), avg_roi(grp), total_pnl_f(grp)) if grp else (label, 0, 0, 0, 0)
    table_c_rows.append(row)
    print(f'{row[0]:<10} {row[1]:>6} {row[2]:>7.1f} {row[3]:>9.1f} ${row[4]:>11,.2f}')

# TABLE D: Cross-tab Ratio x Portfolio size
print('\n\n=== TABLE D: Ratio x Portfolio Size (Count / AvgROI%) ===')
port_labels_d = [('< $2K', 0, 2000), ('$2K-10K', 2000, 10000), ('$10K-50K', 10000, 50000), ('$50K+', 50000, 99999999)]
ratio_labels_d = [('< 5%', 0, 0.05), ('5-15%', 0.05, 0.15), ('15-30%', 0.15, 0.30), ('30-50%', 0.30, 0.50), ('50%+', 0.50, 9999)]

header = f'{"":>12}' + ''.join(f'{lb:>16}' for lb, _, _ in port_labels_d)
print(header)
print('-'*76)
table_d_data = {}
for rl, rlo, rhi in ratio_labels_d:
    row_str = f'{rl:>12}'
    for pl, plo, phi in port_labels_d:
        grp = [p for p in all_positions if rlo <= p.ratio < rhi and plo <= p.portfolio_at_entry < phi]
        cnt = len(grp)
        ar = avg_roi(grp) if grp else 0
        cell = f'{cnt}n/{ar:+.0f}%'
        row_str += f'{cell:>16}'
        table_d_data[(rl, pl)] = (cnt, ar)
    print(row_str)

# TABLE E: Cross-tab Ratio x Price tier
print('\n\n=== TABLE E: Ratio x Price Tier (Count / AvgROI%) ===')
price_labels_e = [('2-15c', 0.02, 0.15), ('15-50c', 0.15, 0.50), ('50-82c', 0.50, 0.82), ('82-95c', 0.82, 0.95), ('95-99c', 0.95, 0.99)]

header = f'{"":>12}' + ''.join(f'{lb:>14}' for lb, _, _ in price_labels_e)
print(header)
print('-'*82)
table_e_data = {}
for rl, rlo, rhi in ratio_labels_d:
    row_str = f'{rl:>12}'
    for pl, plo, phi in price_labels_e:
        grp = [p for p in all_positions if rlo <= p.ratio < rhi and plo <= p.avg_buy_price < phi]
        cnt = len(grp)
        ar = avg_roi(grp) if grp else 0
        cell = f'{cnt}n/{ar:+.0f}%'
        row_str += f'{cell:>14}'
        table_e_data[(rl, pl)] = (cnt, ar)
    print(row_str)

# TOP/BOTTOM
print('\n\n=== TOP 15 Winners ===')
top15 = sorted(all_positions, key=lambda p: p.net_pnl, reverse=True)[:15]
for i, p in enumerate(top15):
    dt = datetime.fromtimestamp(p.first_ts, tz=timezone.utc) if p.first_ts else None
    dt_str = f'{dt:%Y-%m-%d}' if dt else '?'
    status = 'OPEN' if p.is_open else f'CLOSED({p.resolution_status})'
    print(f'  {i+1:>2}. PnL=${p.net_pnl:>+10,.2f}  ROI={p.roi:>+7.1%}  Bought=${p.total_bought_usd:>9,.2f}  '
          f'AvgPrice={p.avg_buy_price:.2f}  Ratio={p.ratio:.1%}  [{status}] {dt_str} {p.title[:50]}')

print('\n=== BOTTOM 15 Losers ===')
bottom15 = sorted(all_positions, key=lambda p: p.net_pnl)[:15]
for i, p in enumerate(bottom15):
    dt = datetime.fromtimestamp(p.first_ts, tz=timezone.utc) if p.first_ts else None
    dt_str = f'{dt:%Y-%m-%d}' if dt else '?'
    status = 'OPEN' if p.is_open else f'CLOSED({p.resolution_status})'
    print(f'  {i+1:>2}. PnL=${p.net_pnl:>+10,.2f}  ROI={p.roi:>+7.1%}  Bought=${p.total_bought_usd:>9,.2f}  '
          f'AvgPrice={p.avg_buy_price:.2f}  Ratio={p.ratio:.1%}  [{status}] {dt_str} {p.title[:50]}')

# ============ ADDITIONAL: CLOSED-ONLY ANALYSIS ============
closed_positions = [p for p in all_positions if not p.is_open]
known_resolution = [p for p in closed_positions if p.resolution_status in ('won', 'lost')]

print(f'\n\n=== CLOSED POSITIONS ONLY (with known resolution) ===')
print(f'Total: {len(known_resolution)}')
if known_resolution:
    wr_closed = wr(known_resolution)
    avg_roi_closed = avg_roi(known_resolution)
    print(f'  WR: {wr_closed:.1f}%  AvgROI: {avg_roi_closed:+.1f}%  TotalPnL: ${total_pnl_f(known_resolution):+,.2f}')

# ============ GENERATE MARKDOWN REPORT ============

lines = []
L = lines.append

L(f'# Denizz Full Backtest: Bet Sizing Ratio Analysis')
L(f'')
L(f'**Generated:** {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC')
L(f'**Player:** denizz `{DENIZZ}`')
if all_trades:
    L(f'**Data span:** {first_dt:%Y-%m-%d} to {last_dt:%Y-%m-%d} ({days_span:.0f} days)')
L(f'**Total trades fetched:** {len(all_trades)}')
L(f'**Positions reconstructed:** {len(all_positions)} (Open: {open_count}, Closed: {closed_count})')
L(f'**Resolution data:** won={res_won}, lost={res_lost}, unknown={res_unknown}')
L(f'')

L(f'## Comparison with previous analysis')
L(f'')
L(f'| Metric | Previous (90d, open only) | This (full history) |')
L(f'|--------|---------------------------|---------------------|')
L(f'| Positions analyzed | 52 (open only) | {len(all_positions)} (open + closed) |')
L(f'| Trades processed | ~1,672 | {len(all_trades)} |')
L(f'| Data window | 90 days | {days_span:.0f} days |')
L(f'| Resolution tracking | No (estimated) | Yes (CLOB API) |')
L(f'| Total PnL | +$504 (sim, $2K bankroll) | ${total_pnl:+,.2f} (actual) |')
L(f'')

L(f'## Summary')
L(f'')
L(f'| Metric | Value |')
L(f'|--------|-------|')
L(f'| Total capital bought | ${total_bought:,.2f} |')
L(f'| Total capital sold (trades) | ${total_sold:,.2f} |')
L(f'| Open position value | ${total_current:,.2f} |')
L(f'| Resolution payouts | ${total_resolution:,.2f} |')
L(f'| **Net PnL** | **${total_pnl:+,.2f}** |')
if total_bought > 0:
    L(f'| ROI on deployed | {total_pnl/total_bought*100:+.1f}% |')
L(f'| Win rate | {winners}/{len(all_positions)} = {winners/len(all_positions)*100:.1f}% |')
L(f'| Losers | {losers} |')
L(f'| Breakeven | {breakeven} |')
L(f'| Peak capital deployed | ${peak_deployed:,.2f} |')
L(f'')

# Closed-only stats
if known_resolution:
    L(f'### Closed Positions (known resolution only)')
    L(f'')
    L(f'| Metric | Value |')
    L(f'|--------|-------|')
    L(f'| Positions | {len(known_resolution)} |')
    L(f'| Won | {sum(1 for p in known_resolution if p.resolution_status=="won")} |')
    L(f'| Lost | {sum(1 for p in known_resolution if p.resolution_status=="lost")} |')
    L(f'| WR | {wr(known_resolution):.1f}% |')
    L(f'| Avg ROI | {avg_roi(known_resolution):+.1f}% |')
    L(f'| Total PnL | ${total_pnl_f(known_resolution):+,.2f} |')
    L(f'')

L(f'## TABLE A: Ratio Buckets vs Outcomes')
L(f'')
L(f'Ratio = total_bought_for_market / active_portfolio_at_first_buy')
L(f'')
L(f'| Ratio | Count | WR% | Avg ROI% | Med ROI% | Total PnL |')
L(f'|-------|-------|-----|----------|----------|-----------|')
for row in table_a_rows:
    L(f'| {row[0]} | {row[1]} | {row[2]:.1f}% | {row[3]:+.1f}% | {row[4]:+.1f}% | ${row[5]:+,.2f} |')
L(f'')

L(f'## TABLE B: Portfolio Size at Entry vs Outcomes')
L(f'')
L(f'Portfolio = total active capital across all markets at time of first buy')
L(f'')
L(f'| Portfolio | Count | WR% | Avg ROI% | Med ROI% | Total PnL |')
L(f'|-----------|-------|-----|----------|----------|-----------|')
for row in table_b_rows:
    L(f'| {row[0]} | {row[1]} | {row[2]:.1f}% | {row[3]:+.1f}% | {row[4]:+.1f}% | ${row[5]:+,.2f} |')
L(f'')

L(f'## TABLE C: Buy Price Tier vs Outcomes')
L(f'')
L(f'| Price | Count | WR% | Avg ROI% | Total PnL |')
L(f'|-------|-------|-----|----------|-----------|')
for row in table_c_rows:
    L(f'| {row[0]} | {row[1]} | {row[2]:.1f}% | {row[3]:+.1f}% | ${row[4]:+,.2f} |')
L(f'')

L(f'## TABLE D: Ratio x Portfolio Size (Count / Avg ROI%)')
L(f'')
hdr = '| Ratio |' + '|'.join(f' {lb} ' for lb, _, _ in port_labels_d) + '|'
L(hdr)
L('|' + '|'.join(['-------'] * (len(port_labels_d) + 1)) + '|')
for rl, rlo, rhi in ratio_labels_d:
    cells = [f' {table_d_data.get((rl, pl), (0,0))[0]}n / {table_d_data.get((rl, pl), (0,0))[1]:+.0f}% ' for pl, _, _ in port_labels_d]
    L(f'| {rl} |' + '|'.join(cells) + '|')
L(f'')

L(f'## TABLE E: Ratio x Price Tier (Count / Avg ROI%)')
L(f'')
hdr = '| Ratio |' + '|'.join(f' {lb} ' for lb, _, _ in price_labels_e) + '|'
L(hdr)
L('|' + '|'.join(['-------'] * (len(price_labels_e) + 1)) + '|')
for rl, rlo, rhi in ratio_labels_d:
    cells = [f' {table_e_data.get((rl, pl), (0,0))[0]}n / {table_e_data.get((rl, pl), (0,0))[1]:+.0f}% ' for pl, _, _ in price_labels_e]
    L(f'| {rl} |' + '|'.join(cells) + '|')
L(f'')

L(f'## Top 15 Winners')
L(f'')
L(f'| # | PnL | ROI | Bought | Avg Price | Ratio | Status | Date | Title |')
L(f'|---|-----|-----|--------|-----------|-------|--------|------|-------|')
for i, p in enumerate(top15):
    dt = datetime.fromtimestamp(p.first_ts, tz=timezone.utc) if p.first_ts else None
    dt_str = f'{dt:%Y-%m-%d}' if dt else '?'
    status = 'OPEN' if p.is_open else p.resolution_status.upper()
    L(f'| {i+1} | ${p.net_pnl:+,.2f} | {p.roi:+.1%} | ${p.total_bought_usd:,.2f} | {p.avg_buy_price:.2f} | {p.ratio:.0%} | {status} | {dt_str} | {p.title[:45]} |')
L(f'')

L(f'## Bottom 15 Losers')
L(f'')
L(f'| # | PnL | ROI | Bought | Avg Price | Ratio | Status | Date | Title |')
L(f'|---|-----|-----|--------|-----------|-------|--------|------|-------|')
for i, p in enumerate(bottom15):
    dt = datetime.fromtimestamp(p.first_ts, tz=timezone.utc) if p.first_ts else None
    dt_str = f'{dt:%Y-%m-%d}' if dt else '?'
    status = 'OPEN' if p.is_open else p.resolution_status.upper()
    L(f'| {i+1} | ${p.net_pnl:+,.2f} | {p.roi:+.1%} | ${p.total_bought_usd:,.2f} | {p.avg_buy_price:.2f} | {p.ratio:.0%} | {status} | {dt_str} | {p.title[:45]} |')
L(f'')

# Key insights
L(f'## Key Insights for Copy-Trading Calibration')
L(f'')

best_ratio = max(table_a_rows, key=lambda r: r[5] if r[1] >= 3 else -999999)
worst_ratio = min(table_a_rows, key=lambda r: r[5] if r[1] >= 3 else 999999)
best_price = max(table_c_rows, key=lambda r: r[4] if r[1] >= 3 else -999999)
best_port = max(table_b_rows, key=lambda r: r[5] if r[1] >= 3 else -999999)

# WR by ratio
best_wr_ratio = max(table_a_rows, key=lambda r: r[2] if r[1] >= 5 else -1)

L(f'1. **Best ratio bucket by PnL:** {best_ratio[0]} ({best_ratio[1]} positions, WR {best_ratio[2]:.0f}%, total PnL ${best_ratio[5]:+,.0f})')
L(f'2. **Worst ratio bucket by PnL:** {worst_ratio[0]} ({worst_ratio[1]} positions, WR {worst_ratio[2]:.0f}%, total PnL ${worst_ratio[5]:+,.0f})')
L(f'3. **Best price tier by PnL:** {best_price[0]} ({best_price[1]} positions, WR {best_price[2]:.0f}%, total PnL ${best_price[4]:+,.0f})')
L(f'4. **Best portfolio size by PnL:** {best_port[0]} ({best_port[1]} positions, WR {best_port[2]:.0f}%, total PnL ${best_port[5]:+,.0f})')
L(f'5. **Highest WR ratio bucket (n>=5):** {best_wr_ratio[0]} ({best_wr_ratio[1]} positions, WR {best_wr_ratio[2]:.0f}%)')
L(f'')

# Signal strength analysis
L(f'### Signal Strength Observations')
L(f'')
L(f'- **Concentration vs diversification:** Denizz puts the vast majority of bets at <5% ratio. '
  f'Larger ratio bets (>15%) are rare but tend to underperform.')
L(f'- **Price tier sweet spot:** Check which price tiers combine high WR with positive total PnL.')
L(f'- **Resolution data impact:** {res_won} positions resolved as wins, {res_lost} as losses. '
  f'{res_unknown} closed positions have unknown resolution (API may not track all).')
L(f'')
L(f'### Caveats')
L(f'')
L(f'- Trades API capped at 3,500 records. Older trades may be missing.')
L(f'- Resolution status for some markets could not be determined via CLOB API.')
L(f'- "Ratio" uses portfolio snapshot at first buy time; DCA adds complicate the true ratio.')
L(f'- Open position values use current market prices (unrealized PnL).')
L(f'')
L(f'---')
L(f'*Analysis based on {len(all_positions)} positions from {len(all_trades)} trades spanning {days_span:.0f} days.*')

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'\n\nReport saved to: {OUT_FILE}')
print('DONE')
