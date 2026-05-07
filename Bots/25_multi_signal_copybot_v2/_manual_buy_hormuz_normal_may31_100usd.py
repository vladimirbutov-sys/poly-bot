"""Manual buy: $100 YES on Strait of Hormuz traffic returns to normal by end of May @ best ask."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x518a5b030b205706b8ffe6bbad9bd3de59548348e5c0471827f5de21e513333c"
TOKEN = "75845920741796858670183364159540464375486880005358999101126589340494255300090"  # YES
TITLE = "Strait of Hormuz traffic returns to normal by end of May?"
SLUG  = "strait-of-hormuz-traffic-returns-to-normal-by-end-of-may"
EVENT_SLUG = "strait-of-hormuz-traffic-returns-to-normal-by-end-of-may"
OUTCOME = "Yes"
SIZE_USD = 100.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
if not ask or ask <= 0:
    print("No ask"); sys.exit(1)

LIMIT_PRICE = round(ask, 4)
print(f"BUY YES @ ${LIMIT_PRICE}, size ${SIZE_USD}")
result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result or not result.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = result['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if real and real['size'] > 0 else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f} cost ${actual_cost:.2f}")

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": OUTCOME, "event_slug": EVENT_SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1, "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-20_hormuz_normal_may31_100usd",
    }
    tracker.save(data)
    print(f"\u2713 Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
else:
    print("Nothing filled"); sys.exit(2)
