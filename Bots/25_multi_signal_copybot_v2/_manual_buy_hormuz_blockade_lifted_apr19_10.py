"""Buy $10 YES on Trump announces Hormuz blockade lifted by April 19 — lottery ticket."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x3a9ef67522be6f0e4dcb97ac56e064efe6b14e54713ee2050418d311883c31ba"
TOKEN = "91598771792773760116390366584153669276526784848469387505098726980059231998980"
TITLE = "Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by April 19, 2026?"
SLUG  = "trump-announces-us-blockade-of-hormuz-lifted-by"
LIMIT_PRICE = 0.11   # = ask + 0.1c rounded
SIZE_USD = 10.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT_PRICE}")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={res.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": "Yes", "event_slug": SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-19_hormuz_blockade_lifted_apr19_lottery",
    }
    tracker.save(data)
    print(f"✓ Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
