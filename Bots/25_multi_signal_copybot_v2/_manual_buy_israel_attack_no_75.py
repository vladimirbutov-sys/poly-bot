"""Buy $75 NO on Will Israel conduct military action against Iran by April 21.

Resolution: NO wins if Israel does NOT attack by Apr 21 23:59 ET.
Market implies 94% probability Israel won't attack.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x9dd27666ad05dbe8ac5547e79d634fc306578b60b71f96ab4347f020b46e9413"
TOKEN = "22461574847104976677124723854389208007201865418102388935875021506968919487748"  # NO
TITLE = "Will Israel conduct military action against Iran by April 21, 2026?"
SLUG  = "israel-military-action-against-iran-by-167"
LIMIT_PRICE = 0.95
SIZE_USD = 75.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"NO bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT_PRICE}")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={res.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=180)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

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
        "outcome": "No", "event_slug": SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-19_israel_attack_no_apr21",
    }
    tracker.save(data)
    print(f"✓ Recorded: {matched:.2f} sh NO @ ${actual_price:.4f} = ${actual_cost:.2f}")
