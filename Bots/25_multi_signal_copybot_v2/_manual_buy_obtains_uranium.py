"""Place a GTC limit BUY — $30 of US obtains Iranian enriched uranium by May 31? NO @ $0.79.
Do NOT wait/cancel. Order sits on the book.
Poll briefly to catch instant fill; if any matched, record in tracker.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID    = "0xbcacd5a055f5a9ced6f69f122216c073dd6987d08253fc07bbcc168fa5b81d55"
TOKEN  = "5345441419419147559625888104788940459264045849260872706421285679583531763371"
TITLE  = "US obtains Iranian enriched uranium by May 31?"
SLUG   = "us-obtains-iranian-enriched-uranium-by-may-31"
OUTCOME = "No"
LIMIT  = 0.79
SIZE   = 30.0
POLL_SECONDS = 30

print(f"BUY LIMIT GTC: {TITLE}")
print(f"  {OUTCOME} @ ${LIMIT}, size ${SIZE}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT, size_usd=SIZE)
if not result:
    print("place_limit_buy returned None"); sys.exit(1)

order_id = result.get("order_id")
req_size = float(result.get("size_shares") or 0)
print(f"Order live  : order_id {order_id}")
print(f"  requested : {req_size} sh")
print(f"  (if ask crosses below $0.79, fills immediately; else waits)")
print()
print(f"Polling briefly ({POLL_SECONDS}s) in case of instant fill...")

# Poll without cancelling
start = time.time()
last_matched = 0.0
while time.time() - start < POLL_SECONDS:
    details = executor.get_order_details(order_id)
    matched = float(details.get("size_matched", 0) or 0)
    status = details.get("status", "UNKNOWN")
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>3}s] matched={matched:.2f}  status={status}")
        last_matched = matched
    if status == "MATCHED":
        break
    time.sleep(5)

# Final poll, no cancel
details = executor.get_order_details(order_id)
final_matched = float(details.get("size_matched", 0) or 0)
final_status = details.get("status", "UNKNOWN")
print(f"\nFinal: status={final_status}  matched={final_matched:.2f} / {req_size}")

# Record whatever filled
if final_matched > 0.5:
    real = executor.get_actual_fill(order_id)
    if real and real["size"] > 0:
        actual_price = real["vwap"]
        actual_cost = real["cost_usd"]
        print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}  (limit was ${LIMIT})")
    else:
        actual_price = LIMIT
        actual_cost = final_matched * LIMIT
        print(f"  [WARN] no trade rows — falling back to limit ${actual_price}")
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data = tracker.load()
    data.setdefault("positions", {})[new_key] = {
        "condition_id": CID,
        "token_id": TOKEN,
        "title": TITLE,
        "outcome": OUTCOME,
        "event_slug": SLUG,
        "entry_price": round(actual_price, 6),
        "avg_entry": round(actual_price, 6),
        "size_shares": round(final_matched, 2),
        "cost_usd": round(actual_cost, 2),
        "tier": "manual",
        "strategy": "manual",
        "signal_player": "manual",
        "parts_filled": 1,
        "parts_planned": 1,
        "order_ids": [order_id],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open",
        "sells": [],
        "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-15",
    }
    tracker.save(data)
    print(f"✓ Recorded: {new_key[:28]}... {final_matched:.2f} sh @ ${LIMIT} = ${actual_cost:.2f}")
else:
    print("No fill yet. Order REMAINS LIVE on the book.")
    print(f"  order_id: {order_id}")
    print(f"  When it fills, bot's onchain_sync will NOT auto-adopt (we have closed rows for this market).")
    print(f"  To track it in positions.json after fill — run this script again or add manual tracker entry.")
