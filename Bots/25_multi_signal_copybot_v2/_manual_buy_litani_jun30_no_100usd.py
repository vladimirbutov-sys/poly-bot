"""Manual buy: $100 NO on Israeli forces cross the Litani River by June 30 @ limit $0.58."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0x9049d96597900ba0f3013604dc7adc3dd6e7e4764c5a0c16318605c40ac1ee96"
TOKEN = "61105898512331423456932766287679410148969111620575334880263459667275737814007"  # NO
TITLE = "Israeli forces cross the Litani River by June 30?"
SLUG  = "israeli-forces-cross-the-litani-river-by-june-30"
EVENT_SLUG = "israeli-forces-cross-the-litani-river-by-june-30"
OUTCOME = "No"
SIZE_USD = 100.0
LIMIT_PRICE = 0.58  # sweep best 2 levels (0.57 + 0.58)

print(f"BUY {OUTCOME} @ ${LIMIT_PRICE}, size ${SIZE_USD}")
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
        "_adopted_from": "manual_buy_2026-04-26_litani_jun30_no_100usd",
    }
    tracker.save(data)
    print(f"OK Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
else:
    print("Nothing filled"); sys.exit(2)
