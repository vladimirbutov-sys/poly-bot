"""Passive limit BUY: <25 ships Hormuz YES @ $0.10 for $50 (hedge)."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xaa980c83777851bf22a3bd4eeee864d11ce7783096a22ce4af56ff9bf2e1d2cd"
TOKEN = "10065719129703851524738159766241582795004980250212999796913119632612444350346"
TITLE = "Will fewer than 25 ships transit the Strait of Hormuz between April 20-April 26?"
SLUG  = "will-fewer-than-25-ships-transit-the-strait-of-hormuz-between-april-20-april-26"
LIMIT_PRICE = 0.10
SIZE_USD = 50.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT_PRICE} (passive, between)")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
req_sh = float(res.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}... size={req_sh}")
print(f"Sitting @ ${LIMIT_PRICE} GTC — fills when sellers drop to this price")
print(f"At full fill: payoff if YES ${req_sh:.2f} → PnL +${req_sh - SIZE_USD:+.2f}")

# Wait up to 60 seconds for any immediate fill (wouldn't happen if truly passive)
fill = executor.wait_for_fill_with_details(oid, timeout=60)
print(f"\nAfter 60s: {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")
    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": "Yes", "event_slug": SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual_hedge", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-20_hormuz_under25_hedge",
    }
    tracker.save(data)
    print(f"✓ Recorded: {matched:.2f} sh @ ${actual_price:.4f}")
else:
    print(f"\nНе исполнено — лимитка висит на книге @ ${LIMIT_PRICE}, ждёт продавцов")
    print(f"Order ID: {oid}")
