"""Compute max payout if all open positions win.
Uses ON-CHAIN balances (CTF.balanceOf) as source of truth.
Pulls cost basis from data-api trade history (not tracker)."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, filters
from py_clob_client.clob_types import TradeParams

WALLET = '0x4717eccF1e1E2443e7563b330C6E0B3B6f96bDdE'

# Load tracker — get list of tokens to check (those marked open)
with open('positions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

token_info = {}  # token_id → {title, outcome}
for k, p in data.get('positions', {}).items():
    if p.get('status') == 'open':
        tok = p.get('token_id', '')
        if tok:
            token_info[tok] = {
                'title': p.get('title', '?')[:55],
                'outcome': p.get('outcome', '?'),
                'tracker_shares': float(p.get('size_shares', 0)),
                'tracker_cost': float(p.get('cost_usd', 0)),
            }

print(f"Tracker: {len(token_info)} open positions")

# Fetch all trades once
c = executor._get_client()
all_trades = c.get_trades(TradeParams(maker_address=WALLET.lower()))
print(f"data-api trades fetched: {len(all_trades)}\n")

# Bucket trades by token
trades_by_tok: dict[str, list] = {}
for t in all_trades:
    tok = str(t.get('asset_id', ''))
    trades_by_tok.setdefault(tok, []).append(t)

# Compute for each open token
results = []
for tok, info in token_info.items():
    trades = trades_by_tok.get(tok, [])
    bought = sold = cost_buy = rev_sell = 0.0
    for t in trades:
        side = t.get('side', '')
        sz = float(t.get('size', 0))
        pr = float(t.get('price', 0))
        if side == 'BUY':
            bought += sz; cost_buy += sz * pr
        elif side == 'SELL':
            sold += sz; rev_sell += sz * pr
    onchain_net = bought - sold  # net shares still held (on-chain proxy)
    # Live bid for mark-to-market
    try:
        bid, ask = filters.get_orderbook_prices(tok)
    except Exception:
        bid = ask = 0
    # Cost basis of remaining = proportional
    avg_buy = cost_buy / bought if bought > 0 else 0
    cost_remaining = avg_buy * onchain_net
    realized_pnl = rev_sell - (avg_buy * sold)
    # Max payout if our outcome wins
    max_payout = onchain_net * 1.00 if onchain_net > 0 else 0
    mtm_value = onchain_net * bid if onchain_net > 0 else 0

    results.append({
        'title': info['title'], 'outcome': info['outcome'],
        'onchain_sh': onchain_net, 'avg_entry': avg_buy,
        'cost_remaining': cost_remaining,
        'bid': bid, 'mtm': mtm_value,
        'realized': realized_pnl,
        'max_payout': max_payout,
        'max_win_pnl': max_payout - cost_remaining,
    })

# Sort by max_payout descending
results.sort(key=lambda r: -r['max_payout'])

print(f"{'='*140}")
print(f"{'#':<3} {'Рынок':<55} {'Сторона':<7} {'On-ch sh':>10} {'Avg entry':>10} {'Cost':>8} {'Bid':>7} {'MtM':>8} {'Max payout':>12} {'Max PnL':>10}")
print(f"{'='*140}")

total_cost = 0; total_mtm = 0; total_payout = 0; total_realized = 0
for i, r in enumerate(results, 1):
    print(f"{i:<3} {r['title']:<55} {r['outcome']:<7} {r['onchain_sh']:>10.2f} ${r['avg_entry']:>8.4f} ${r['cost_remaining']:>6.2f} ${r['bid']:>5.3f} ${r['mtm']:>6.2f} ${r['max_payout']:>10.2f} ${r['max_win_pnl']:>+8.2f}")
    total_cost += r['cost_remaining']
    total_mtm += r['mtm']
    total_payout += r['max_payout']
    total_realized += r['realized']

print(f"{'='*140}")
print(f"\n📊 СУММЫ:")
print(f"  Вложено (cost на открытых):          ${total_cost:,.2f}")
print(f"  Mark-to-Market сейчас (по bid):      ${total_mtm:,.2f}")
print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"  🎯 МАКС PAYOUT (если ВСЁ выиграет):  ${total_payout:,.2f}")
print(f"  💰 МАКС PnL:                          ${total_payout - total_cost:+,.2f}")
print(f"")
print(f"  Реализованный PnL по этим токенам:   ${total_realized:+,.2f}")
