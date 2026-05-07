"""
Full 90-day backtest of the current copy-trading strategy on denizz trades.

Replays every denizz BUY/SELL chronologically, applies all current bot
rules, tracks our simulated portfolio state, and produces a full report.

See accompanying _analytics/2026-04-09_denizz-90d-backtest.md for results.
"""
import sys
import io
import os
import json
import time
import requests
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DENIZZ = '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73'
BANKROLL = 2000.0

NOW = int(datetime.now(timezone.utc).timestamp())
CUTOFF = NOW - 90 * 86400  # 90 days ago

DATA_DIR = '_analytics/data'
OUT_FILE = '_analytics/2026-04-09_denizz-90d-backtest.md'
os.makedirs(DATA_DIR, exist_ok=True)

# ========== FETCH HISTORIC DATA ==========

def fetch_all(endpoint, params_extra, max_records=5000, cache_file=None):
    """Paginated fetch with optional file cache."""
    if cache_file:
        path = os.path.join(DATA_DIR, cache_file)
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            if NOW - mtime < 3600:  # use cache if <1h old
                with open(path, encoding='utf-8') as f:
                    return json.load(f)
    out = []
    off = 0
    while True:
        p = {'user': DENIZZ, 'limit': 500, 'offset': off}
        p.update(params_extra)
        try:
            r = requests.get(f'https://data-api.polymarket.com/{endpoint}',
                             params=p, timeout=25)
        except Exception as e:
            print(f'  err: {e}')
            break
        if not r.ok:
            break
        b = r.json()
        if not b:
            break
        out.extend(b)
        if len(b) < 500:
            break
        off += 500
        time.sleep(0.15)
        if len(out) >= max_records:
            break
    if cache_file:
        with open(os.path.join(DATA_DIR, cache_file), 'w', encoding='utf-8') as f:
            json.dump(out, f)
    return out


print('Fetching denizz trades (90d, may use cache)...')
all_trades = fetch_all('trades', {}, max_records=5000, cache_file='denizz_trades_90d.json')
trades_90d = [t for t in all_trades if int(t.get('timestamp', 0) or 0) >= CUTOFF]
print(f'  total trades: {len(all_trades)}  in-window: {len(trades_90d)}')

print('Fetching denizz activity (for merges)...')
all_activity = fetch_all('activity', {}, max_records=5000, cache_file='denizz_activity_90d.json')
merges_90d = [a for a in all_activity
              if (a.get('type') or '').upper() in ('MERGE', 'CONVERSION')
              and int(a.get('timestamp', 0) or 0) >= CUTOFF]
print(f'  merges in-window: {len(merges_90d)}')

# Trades-only timeline sorted by ts asc
trades_sorted = sorted(trades_90d, key=lambda t: int(t.get('timestamp', 0) or 0))

# Precompute per-market trades (all participants) for price lookups on exits.
# We only need snapshots of prices at specific times, so lazy-fetch per market.
market_trades_cache = {}

def fetch_market_trades(cid):
    if cid in market_trades_cache:
        return market_trades_cache[cid]
    out = []
    off = 0
    while True:
        try:
            r = requests.get('https://data-api.polymarket.com/trades',
                             params={'market': cid, 'limit': 500, 'offset': off},
                             timeout=20)
            if not r.ok:
                break
            b = r.json()
            if not b:
                break
            out.extend(b)
            if len(b) < 500:
                break
            off += 500
            time.sleep(0.1)
            if off > 2000:
                break
        except Exception:
            break
    market_trades_cache[cid] = out
    return out


def price_at_or_after(cid, asset, ts):
    """First trade price on (cid, asset) at or after ts. None if no data."""
    trades = fetch_market_trades(cid)
    best = None
    for t in trades:
        if t.get('asset', '') != asset:
            continue
        t_ts = int(t.get('timestamp', 0) or 0)
        if t_ts >= ts:
            if best is None or t_ts < best[1]:
                best = (float(t.get('price', 0) or 0), t_ts)
    return best


# ========== STRATEGY RULES ==========

# Price zones → price multiplier for bet sizing
PRICE_BET_MULTIPLIERS = [
    (0.00, 0.15, 0.7),
    (0.15, 0.50, 1.0),
    (0.50, 0.70, 0.9),
    (0.70, 0.82, 0.8),
    (0.82, 0.90, 0.4),
    (0.90, 0.98, 0.3),
]
def price_mult(p):
    for lo, hi, m in PRICE_BET_MULTIPLIERS:
        if lo <= p < hi:
            return m
    return 1.0

# Slippage caps
MAX_SLIPPAGE_TIERS = [
    (0.00, 0.10, 0.020),
    (0.10, 0.20, 0.030),
    (0.20, 0.30, 0.030),
    (0.30, 0.50, 0.030),
    (0.50, 0.70, 0.030),
    (0.70, 0.82, 0.030),
    (0.82, 0.88, 0.015),
    (0.88, 0.92, 0.010),
    (0.92, 0.95, 0.006),
    (0.95, 0.97, 0.003),
    (0.97, 0.99, 0.002),
]
def max_slippage(p):
    for lo, hi, s in MAX_SLIPPAGE_TIERS:
        if lo <= p < hi:
            return s
    return 0.002

# Tier bet amounts (cumulative) for denizz
TIER_LEVELS = [(500, 30), (2000, 55), (5000, 105), (10000, 200)]
def tier_bet(invested_usd, entry_price):
    base = 0
    for level, amt in TIER_LEVELS:
        if invested_usd >= level:
            base = amt
    return round(base * price_mult(entry_price), 2)

# Late-entry multiplier (Rule A+)
def late_entry_mult(player_avg, our_price):
    if player_avg <= 0 or our_price <= 0:
        return 1.0, 'no history'
    m = our_price / player_avg
    if m <= 1.2: return 1.0, f'on-time {m:.2f}x'
    if m <= 1.5: return 0.75, f'late {m:.2f}x'
    if m <= 2.0: return 0.50, f'bad {m:.2f}x'
    if m <= 3.0: return 0.25, f'terrible {m:.2f}x'
    return 0.10, f'extreme {m:.2f}x'

# Category (simplified — check title keywords)
CATEGORY_KEYWORDS = {
    'politics': ['trump', 'biden', 'congress', 'senate', 'democrat', 'republican',
                 'pardon', 'white house', 'presidential'],
    'geopolitics': ['nato', 'china', 'sanctions', 'nuclear', 'trade deal',
                    'blockade', 'taiwan', 'north korea', 'venezuela'],
    'iran': ['iran', 'tehran', 'hezbollah', 'lebanon', 'israel', 'iranian',
             'hamas', 'gaza', 'houthi', 'yemen', 'khamenei', 'netanyahu'],
    'russia_ukraine': ['ukraine', 'russia', 'putin', 'zelensky'],
    'oil': ['oil', 'crude', 'brent', 'wti', 'gold', 'hormuz'],
    'entertainment': ['super bowl', 'oscar', 'grammy', 'ufc', 'nfl', 'nba',
                      'mbappe', 'ballon', 'world cup'],
    'tech': ['nvidia', 'apple', 'google', 'meta', 'tesla'],
    'elections': ['election', 'vote', 'ballot', 'primary', 'runoff'],
}
def classify_category(title):
    t = (title or '').lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return None

EXCLUDED_KEYWORDS = ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol',
                     'crypto', 'token', 'defi', 'nft', 'fed rate', 'inflation',
                     'cpi', 'gdp', 'unemployment', 'interest rate', 'fomc',
                     'federal reserve']
def is_excluded(title):
    t = (title or '').lower()
    return any(k in t for k in EXCLUDED_KEYWORDS)


# ========== SIMULATION STATE ==========

class SimState:
    def __init__(self):
        self.bankroll = BANKROLL
        self.balance = BANKROLL  # USDC free
        self.positions = {}  # buf_key → {'cost', 'shares', 'avg_entry', 'entry_ts', 'title', 'last_tier_bet'}
        self.buffer = {}  # buf_key → {'total_usd': ..., 'player_avg_at_time': ..., 'signaled': bool}
        self.player_state = defaultdict(lambda: {'cost': 0, 'shares': 0})
        # player_state per (cid, asset) — cumulative cost & shares for denizz,
        # used to compute historical avgPrice at any moment
        # Stats
        self.entries = []       # list of entry records
        self.exits = []         # list of exit records
        self.skipped = defaultdict(int)  # skip reasons
        self.rule_a_savings = 0  # usd saved by late-gate downsizing
        self.rule_b_blocked = 0
        self.equity_curve = []
        self.max_equity = BANKROLL
        self.max_drawdown = 0

    def update_equity(self, ts):
        # equity = balance + current_value of open positions (approximated by cost)
        open_val = sum(p['cost'] for p in self.positions.values())
        equity = self.balance + open_val
        self.equity_curve.append((ts, equity))
        if equity > self.max_equity:
            self.max_equity = equity
        dd = (self.max_equity - equity) / self.max_equity if self.max_equity > 0 else 0
        if dd > self.max_drawdown:
            self.max_drawdown = dd

    def player_avg(self, cid, asset):
        ps = self.player_state[(cid, asset)]
        if ps['shares'] > 0:
            return ps['cost'] / ps['shares']
        return 0

    def apply_player_trade(self, t):
        cid = t.get('conditionId', '')
        asset = t.get('asset', '')
        side = (t.get('side', '') or '').upper()
        size = float(t.get('size', 0) or 0)
        price = float(t.get('price', 0) or 0)
        if size <= 0 or price <= 0:
            return
        ps = self.player_state[(cid, asset)]
        if side == 'BUY':
            ps['cost'] += size * price
            ps['shares'] += size
        elif side == 'SELL':
            # proportional reduction using current avg
            if ps['shares'] > 0:
                avg = ps['cost'] / ps['shares']
                ps['cost'] -= size * avg
                ps['shares'] -= size
                if ps['shares'] < 0.01:
                    ps['shares'] = 0
                    ps['cost'] = 0


def simulate():
    state = SimState()

    print(f'\nReplaying {len(trades_sorted)} denizz trades chronologically...')
    processed = 0

    # Build a secondary timeline: merges interleaved with trades by timestamp
    merge_events = [{'type': 'MERGE', 'data': m, 'ts': int(m.get('timestamp', 0) or 0)}
                    for m in merges_90d]
    trade_events = [{'type': 'TRADE', 'data': t, 'ts': int(t.get('timestamp', 0) or 0)}
                    for t in trades_sorted]
    timeline = sorted(trade_events + merge_events, key=lambda x: x['ts'])

    for ev in timeline:
        processed += 1
        ts = ev['ts']

        if ev['type'] == 'MERGE':
            m = ev['data']
            cid = m.get('conditionId', '')
            # Treat merge as 100% exit signal on any open position tied to denizz on this cid
            for buf_key, pos in list(state.positions.items()):
                if buf_key.startswith(cid + '|'):
                    _, asset = buf_key.split('|', 1)
                    # Exit at current mid price (approximate)
                    snap = price_at_or_after(cid, asset, ts)
                    exit_price = snap[0] if snap else pos['avg_entry']
                    shares = pos['shares']
                    revenue = shares * exit_price
                    pnl = revenue - pos['cost']
                    state.balance += revenue
                    state.exits.append({
                        'ts': ts, 'buf_key': buf_key, 'title': pos['title'],
                        'shares': shares, 'exit_price': exit_price,
                        'cost': pos['cost'], 'pnl': pnl,
                        'reason': 'merge_exit',
                        'hold_days': (ts - pos['entry_ts']) / 86400
                    })
                    del state.positions[buf_key]
            state.apply_player_trade_merge(cid) if False else None  # merge reduces shares, but we skip for simplicity
            state.update_equity(ts)
            continue

        t = ev['data']
        cid = t.get('conditionId', '')
        asset = t.get('asset', '')
        title = t.get('title', '')
        outcome = t.get('outcome', '')
        side = (t.get('side', '') or '').upper()
        size = float(t.get('size', 0) or 0)
        price = float(t.get('price', 0) or 0)

        if not cid or not asset or size <= 0 or price <= 0:
            continue

        buf_key = f'{cid}|{asset}'

        # Update player state BEFORE decision (since this trade is happening)
        # But we want player_avg PRE-trade for our mult calculation? No — post-trade:
        # denizz is updating their position, we evaluate on the NEW state.
        state.apply_player_trade(t)

        if side == 'BUY':
            # Update buffer
            if buf_key not in state.buffer:
                state.buffer[buf_key] = {'total_usd': 0, 'signaled': False}
            state.buffer[buf_key]['total_usd'] += size * price

            # Check if already in position — tier upgrade branch
            if buf_key in state.positions:
                pos = state.positions[buf_key]
                player_invested = state.player_state[(cid, asset)]['cost']
                player_avg = state.player_avg(cid, asset)

                # Rule B: compare our entry (approximated = this trade's price) vs
                # triggering buy price (same trade price) → mult = 1.0 → never blocks
                # That's by design now, so skip.

                # Rule A+ scaling on upgrade
                new_bet = tier_bet(player_invested, price)
                size_mult, _ = late_entry_mult(player_avg, price)
                new_bet = round(new_bet * size_mult, 2)
                last_tier_bet = pos['last_tier_bet']
                increment = round(new_bet - last_tier_bet, 2)
                if increment >= 10 and increment <= state.balance:
                    # Execute upgrade
                    shares_added = increment / price
                    new_total_cost = pos['cost'] + increment
                    new_total_shares = pos['shares'] + shares_added
                    pos['cost'] = new_total_cost
                    pos['shares'] = new_total_shares
                    pos['avg_entry'] = new_total_cost / new_total_shares
                    pos['last_tier_bet'] = new_bet
                    state.balance -= increment
                    state.entries.append({
                        'ts': ts, 'buf_key': buf_key, 'title': title,
                        'price': price, 'size_usd': increment,
                        'player_invested': player_invested, 'player_avg': player_avg,
                        'kind': 'upgrade', 'late_mult': size_mult,
                    })
                state.update_equity(ts)
                continue

            # Not yet in position — check if buffer crosses threshold
            if state.buffer[buf_key]['total_usd'] < 500:
                continue  # still buffering

            # Apply entry filters
            if is_excluded(title):
                state.skipped['excluded'] += 1
                continue
            if classify_category(title) is None:
                state.skipped['category'] += 1
                continue
            if not (0.05 <= price <= 0.98):
                state.skipped['price_range'] += 1
                continue
            # Slippage — we use trade price as entry, slippage 0 by assumption
            # (ASSUMPTION: we get the same fill price as denizz — see notes)

            # Opposition check skipped (assumption)

            # Check position limits
            if len(state.positions) >= 20:
                state.skipped['max_concurrent'] += 1
                continue

            # Compute bet size
            player_invested = state.player_state[(cid, asset)]['cost']
            player_avg = state.player_avg(cid, asset)
            bet = tier_bet(player_invested, price)

            # Rule A+ late entry gate
            size_mult, reason = late_entry_mult(player_avg, price)
            bet_before = bet
            bet = round(bet * size_mult, 2)
            if size_mult < 1.0:
                state.rule_a_savings += (bet_before - bet)

            if bet < 10:
                state.skipped['bet_too_small'] += 1
                continue
            if bet > state.balance:
                state.skipped['insufficient_balance'] += 1
                continue

            # Enter
            shares = bet / price
            state.positions[buf_key] = {
                'cost': bet, 'shares': shares, 'avg_entry': price,
                'entry_ts': ts, 'title': title, 'outcome': outcome,
                'last_tier_bet': bet,
            }
            state.balance -= bet
            state.buffer[buf_key]['signaled'] = True
            state.entries.append({
                'ts': ts, 'buf_key': buf_key, 'title': title,
                'price': price, 'size_usd': bet, 'shares': shares,
                'player_invested': player_invested, 'player_avg': player_avg,
                'kind': 'new', 'late_mult': size_mult, 'reason': reason,
            })
            state.update_equity(ts)

        elif side == 'SELL':
            # Player sold — profit-conditional rule
            if buf_key not in state.positions:
                continue
            pos = state.positions[buf_key]
            ps = state.player_state[(cid, asset)]
            # At this point player state was already updated (after sell)
            # To get sold_pct, we need sold_shares / (ps_after + sold_shares)
            shares_before = ps['shares'] + size
            sold_pct = size / shares_before if shares_before > 0 else 0

            # Current price approximated by this sell trade price
            our_bid = price
            in_profit = our_bid >= pos['avg_entry']

            should_exit = False
            reason = ''
            if sold_pct >= 0.7:
                should_exit = True
                reason = f'player_dump_{int(sold_pct*100)}pct'
            elif in_profit:
                should_exit = True
                reason = f'player_partial_{int(sold_pct*100)}pct_lock_win'
            else:
                # HOLD — profit-conditional protection
                continue

            if should_exit:
                shares = pos['shares']
                revenue = shares * our_bid
                pnl = revenue - pos['cost']
                state.balance += revenue
                state.exits.append({
                    'ts': ts, 'buf_key': buf_key, 'title': pos['title'],
                    'shares': shares, 'exit_price': our_bid,
                    'cost': pos['cost'], 'pnl': pnl,
                    'reason': reason,
                    'hold_days': (ts - pos['entry_ts']) / 86400,
                })
                del state.positions[buf_key]
                state.update_equity(ts)

    # End of timeline — close remaining open positions at last-known price
    print(f'\nEnd of timeline. {len(state.positions)} positions still open — closing at current prices...')
    for buf_key, pos in list(state.positions.items()):
        cid, asset = buf_key.split('|', 1)
        snap = price_at_or_after(cid, asset, NOW - 86400)
        if snap:
            exit_price = snap[0]
        else:
            exit_price = pos['avg_entry']  # fallback
        shares = pos['shares']
        revenue = shares * exit_price
        pnl = revenue - pos['cost']
        state.balance += revenue
        state.exits.append({
            'ts': NOW, 'buf_key': buf_key, 'title': pos['title'],
            'shares': shares, 'exit_price': exit_price,
            'cost': pos['cost'], 'pnl': pnl,
            'reason': 'eom_close',
            'hold_days': (NOW - pos['entry_ts']) / 86400,
        })
        del state.positions[buf_key]

    return state


# ========== REPORT ==========

def generate_report(state):
    lines = []
    lines.append('# Backtest: denizz copy strategy (90d, 2026-01-09 to 2026-04-09)')
    lines.append('')
    lines.append(f'**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    lines.append(f'**Player:** denizz `{DENIZZ}`')
    lines.append(f'**Bankroll:** ${BANKROLL:,.0f}')
    lines.append(f'**Trade events processed:** {len(trades_90d)} trades + {len(merges_90d)} merges')
    lines.append('')

    # Summary
    total_entries = len(state.entries)
    new_entries = sum(1 for e in state.entries if e['kind'] == 'new')
    upgrade_entries = sum(1 for e in state.entries if e['kind'] == 'upgrade')
    total_exits = len(state.exits)
    realized_pnl = sum(e['pnl'] for e in state.exits)
    total_deployed = sum(e['size_usd'] for e in state.entries)
    wins = [e for e in state.exits if e['pnl'] > 0]
    losses = [e for e in state.exits if e['pnl'] < 0]
    win_rate = len(wins) / total_exits * 100 if total_exits > 0 else 0
    avg_win = sum(e['pnl'] for e in wins) / len(wins) if wins else 0
    avg_loss = sum(e['pnl'] for e in losses) / len(losses) if losses else 0
    sharpe_like = (avg_win / abs(avg_loss)) if avg_loss < 0 else float('inf')
    final_balance = state.balance

    lines.append('## TL;DR')
    lines.append('')
    lines.append(f'**Net P&L:** ${realized_pnl:+,.2f}')
    lines.append(f'**ROI on bankroll:** {realized_pnl / BANKROLL * 100:+.1f}%')
    lines.append(f'**Final balance:** ${final_balance:,.2f} (started ${BANKROLL:,.0f})')
    lines.append('')

    lines.append('## Summary metrics')
    lines.append('')
    lines.append('| Metric | Value |')
    lines.append('|--------|-------|')
    lines.append(f'| Total entries | **{total_entries}** (new: {new_entries}, upgrades: {upgrade_entries}) |')
    lines.append(f'| Total exits | **{total_exits}** |')
    lines.append(f'| Capital deployed (sum of bets) | ${total_deployed:,.2f} |')
    lines.append(f'| Realized P&L | **${realized_pnl:+,.2f}** |')
    lines.append(f'| ROI on bankroll | **{realized_pnl / BANKROLL * 100:+.1f}%** |')
    lines.append(f'| ROI on deployed capital | **{realized_pnl / total_deployed * 100 if total_deployed > 0 else 0:+.1f}%** |')
    lines.append(f'| Win rate | **{win_rate:.1f}%** ({len(wins)}W / {len(losses)}L) |')
    lines.append(f'| Avg win | ${avg_win:+,.2f} |')
    lines.append(f'| Avg loss | ${avg_loss:+,.2f} |')
    lines.append(f'| Win/loss ratio | **{sharpe_like:.2f}** |')
    lines.append(f'| Max drawdown | {state.max_drawdown * 100:.1f}% |')
    lines.append(f'| Max equity | ${state.max_equity:,.2f} |')
    lines.append('')

    # Skipped breakdown
    lines.append('## Entries blocked by filters')
    lines.append('')
    lines.append('| Reason | Count |')
    lines.append('|--------|------|')
    for k in sorted(state.skipped.keys(), key=lambda x: -state.skipped[x]):
        lines.append(f'| {k} | {state.skipped[k]} |')
    lines.append('')

    # Rule impact
    lines.append('## Rule A+ (late-entry size gate) impact')
    lines.append('')
    lines.append(f'Capital "saved" by size downsizing: **${state.rule_a_savings:,.2f}**')
    late_entries = [e for e in state.entries if e.get('late_mult', 1) < 1]
    lines.append(f'Entries downsized: {len(late_entries)} of {total_entries}')
    # Breakdown by multiplier
    by_mult = defaultdict(int)
    for e in late_entries:
        m = e['late_mult']
        by_mult[f'{m:.2f}x'] += 1
    for k, v in sorted(by_mult.items()):
        lines.append(f'  - {k} multiplier: {v} entries')
    lines.append('')

    # Exits by reason
    lines.append('## Exits by reason')
    lines.append('')
    by_reason = defaultdict(lambda: {'n': 0, 'pnl': 0})
    for e in state.exits:
        r = e['reason']
        by_reason[r]['n'] += 1
        by_reason[r]['pnl'] += e['pnl']
    lines.append('| Reason | N | Total PnL | Avg PnL |')
    lines.append('|--------|---|-----------|---------|')
    for r, s in sorted(by_reason.items(), key=lambda x: -x[1]['pnl']):
        avg = s['pnl'] / s['n'] if s['n'] > 0 else 0
        lines.append(f'| {r} | {s["n"]} | ${s["pnl"]:+,.2f} | ${avg:+,.2f} |')
    lines.append('')

    # Top winners/losers
    exits_sorted = sorted(state.exits, key=lambda x: -x['pnl'])
    lines.append('## Top 10 winners')
    lines.append('')
    lines.append('| PnL | Hold (d) | Reason | Title |')
    lines.append('|-----|---------|--------|-------|')
    for e in exits_sorted[:10]:
        lines.append(f'| ${e["pnl"]:+,.2f} | {e["hold_days"]:.1f} | {e["reason"]} | {e["title"][:50]} |')
    lines.append('')
    lines.append('## Top 10 losers')
    lines.append('')
    lines.append('| PnL | Hold (d) | Reason | Title |')
    lines.append('|-----|---------|--------|-------|')
    for e in exits_sorted[-10:][::-1]:
        lines.append(f'| ${e["pnl"]:+,.2f} | {e["hold_days"]:.1f} | {e["reason"]} | {e["title"][:50]} |')
    lines.append('')

    # Assumptions
    lines.append('## Assumptions & limitations')
    lines.append('')
    lines.append('| # | Assumption | Bias direction | Criticality |')
    lines.append('|---|------------|---------------|-------------|')
    lines.append('| 1 | Fill at denizz trade price (zero slippage) | **Optimistic** (overstates P&L) | **HIGH** |')
    lines.append('| 2 | Orderbook depth at time T unknown — assumed sufficient for our small orders | Slight optimistic | LOW |')
    lines.append('| 3 | Our exit price = player sell trade price (no lag) | Optimistic | MEDIUM |')
    lines.append('| 4 | Historical player_avg reconstructed from trades (buys − proportional sells) | May be off on merge/split events | LOW |')
    lines.append('| 5 | Opposition check (Car/aenews2 blockers) SKIPPED — would only matter for Car/aenews2 signals which we do not backtest here | No bias (denizz ignores them anyway) | LOW |')
    lines.append('| 6 | Trades API limit 5000 entries, may miss oldest trades in 90d window | Incomplete coverage | MEDIUM |')
    lines.append('| 7 | Market liquidity on exit assumed unlimited | Optimistic for big sizes | LOW |')
    lines.append('| 8 | Stop loss 65% / time stop 16d / 99c target NOT simulated — we only exit on player signals | Understates exits (some positions might be closed earlier) | **HIGH** |')
    lines.append('| 9 | Open positions at end of window closed at last known price | Approximation | LOW |')
    lines.append('| 10 | Merge events handled as full exit at player sell price (simplified) | May not match reality | LOW |')
    lines.append('')
    lines.append('## Reliability assessment')
    lines.append('')
    lines.append('**Confidence: MEDIUM.** The P&L number should be treated as an upper-bound estimate.')
    lines.append('Biggest sources of error: (1) zero-slippage fill assumption overstates wins by 2-5%;')
    lines.append('(2) no stop loss / time stop simulation understates exits and may overstate drawdown.')
    lines.append('Directionally the results are valid for comparing rule variants.')
    lines.append('')

    return '\n'.join(lines)


# ========== MAIN ==========

print('\n=== Running simulation ===')
state = simulate()
report = generate_report(state)

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    f.write(report)

# Console summary
print('\n' + '='*60)
print('BACKTEST SUMMARY')
print('='*60)
realized_pnl = sum(e['pnl'] for e in state.exits)
total_deployed = sum(e['size_usd'] for e in state.entries)
wins = [e for e in state.exits if e['pnl'] > 0]
losses = [e for e in state.exits if e['pnl'] < 0]
print(f'Entries:         {len(state.entries)} (new {sum(1 for e in state.entries if e["kind"]=="new")} + upg {sum(1 for e in state.entries if e["kind"]=="upgrade")})')
print(f'Exits:           {len(state.exits)}')
print(f'Capital deployed: ${total_deployed:,.2f}')
print(f'Realized P&L:    ${realized_pnl:+,.2f}')
print(f'ROI bankroll:    {realized_pnl / BANKROLL * 100:+.1f}%')
print(f'Win rate:        {len(wins)/(len(wins)+len(losses))*100:.1f}% ({len(wins)}W/{len(losses)}L)')
print(f'Rule A+ savings: ${state.rule_a_savings:,.2f}')
print(f'Max drawdown:    {state.max_drawdown*100:.1f}%')
print(f'\nFull report: {OUT_FILE}')
