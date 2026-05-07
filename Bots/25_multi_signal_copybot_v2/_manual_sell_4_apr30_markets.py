"""Sell 4 specified open positions at best market price (sweep best bid)."""
import sys, io, time, os
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
import requests

TARGETS = [
    'us-iran nuclear deal by april 30',
    'us x iran permanent peace deal by april 30',
    'trump announces end of military operations against iran by april 30',
    'will trump agree to iranian oil sanction relief in april',
]

def aggressive_limit(token_id: str, shares_needed: float) -> float:
    r = requests.get(f'https://clob.polymarket.com/book?token_id={token_id}', timeout=10).json()
    bids = sorted([(float(b['price']), float(b['size'])) for b in r.get('bids', [])], key=lambda x: -x[0])
    if not bids:
        return 0.0
    cum = 0.0; last_p = bids[0][0]
    for bp, bs in bids:
        cum += bs; last_p = bp
        if cum >= shares_needed:
            break
    return max(0.001, round(last_p - 0.005, 4))


# Cancel any existing sells on target tokens first
data = tracker.load()
opens = [(k, p) for k, p in data.get('positions', {}).items() if p.get('status') == 'open']
matched = []
for k, p in opens:
    title_lower = (p.get('title', '') or '').lower()
    for t in TARGETS:
        if t in title_lower:
            matched.append((k, p))
            break

c = executor._get_client()
all_orders = c.get_orders()
target_tokens = {p.get('token_id', '') for k, p in matched}
cancelled = 0
for o in all_orders:
    if str(o.get('asset_id', '')) in target_tokens and o.get('side') == 'SELL':
        oid = o.get('id', '')
        print(f"Cancelling existing SELL {oid[:24]}...")
        try:
            executor.cancel_order(oid)
            cancelled += 1
        except Exception as e:
            print(f"  err: {e}")
if cancelled:
    time.sleep(3)

# Place sells
total_revenue = 0.0
total_cost = 0.0
total_pnl = 0.0
for k, p in matched:
    tok = p.get('token_id', '')
    sh = float(p.get('size_shares', 0) or 0)
    cost = float(p.get('cost_usd', 0) or 0)
    title = p.get('title', '')[:60]
    print(f"\n--- {p.get('outcome')} {sh:.2f} sh | {title} ---")

    bid, ask = filters.get_orderbook_prices(tok)
    print(f"  bid/ask: ${bid:.4f}/${ask:.4f}, cost ${cost:.2f}")

    limit = aggressive_limit(tok, sh)
    if limit <= 0:
        print(f"  no bids, skipping")
        continue
    print(f"  Placing SELL {sh:.2f} @ ${limit:.4f}")

    res = executor.place_limit_sell(token_id=tok, price=limit, shares=sh)
    if not res or not res.get('order_id'):
        print(f"  PLACE FAILED: {res}")
        continue
    oid = res['order_id']
    print(f"  order: {oid[:24]}...")

    fill = executor.wait_for_fill_with_details(oid, timeout=120)
    matched_sh = float(fill.get('size_matched') or 0)
    print(f"  status={fill.get('status')}  matched={matched_sh:.2f}/{fill.get('size_original'):.2f}")
    if matched_sh < 0.5:
        print(f"  Nothing filled")
        continue

    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else limit
    revenue = real['cost_usd'] if (real and real['size'] > 0) else matched_sh * limit
    print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

    data = tracker.load()
    pp = data['positions'][k]
    cur_sh = float(pp['size_shares'])
    cur_cost = float(pp['cost_usd'])
    cost_sold = cur_cost * (matched_sh / cur_sh) if cur_sh > 0 else 0
    pnl = revenue - cost_sold
    new_sh = cur_sh - matched_sh
    pp['size_shares'] = round(new_sh, 4)
    pp['cost_usd'] = round(cur_cost - cost_sold, 4)
    pp.setdefault('sells', []).append({
        'shares': round(matched_sh, 4),
        'price': round(actual_price, 6),
        'revenue': round(revenue, 4),
        'pnl': round(pnl, 4),
        'reason': 'manual_sell_4_apr30_markets',
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
    if new_sh < 0.5:
        pp['status'] = 'sold'
        pp['final_pnl'] = round(pnl, 4)
    tracker.save(data)
    print(f"  OK PnL ${pnl:+.2f}  status={pp['status']}")

    total_revenue += revenue
    total_cost += cost_sold
    total_pnl += pnl
    time.sleep(1)

print("\n" + "=" * 60)
print(f"SUMMARY")
print(f"  cost ${total_cost:.2f}  revenue ${total_revenue:.2f}  PnL ${total_pnl:+.2f}")
