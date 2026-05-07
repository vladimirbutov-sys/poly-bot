"""Cancel stale $0.70 limit, place new limit SELL 100% Trump POTUS NO @ $0.68."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "8645739410699309255723712337953202603299613672752563309810773074070571201206"
KEY   = "0xmanual_4afbba32986b1a7d8acfca3b51061eb5"
LIMIT_PRICE = 0.68

# Step 1: cancel existing sell order(s)
c = executor._get_client()
orders = [o for o in c.get_orders() if str(o.get('asset_id','')) == TOKEN]
cancelled = 0
for o in orders:
    if o.get('side') == 'SELL':
        oid_full = o.get('id', '')
        print(f"Cancelling {oid_full[:24]}... @ ${o.get('price')}  orig={o.get('original_size')}  matched={o.get('size_matched')}")
        executor.cancel_order(oid_full)
        cancelled += 1

if cancelled:
    time.sleep(3)  # let cancellation propagate

# Step 2: reload tracker for current open size
data = tracker.load()
p = data.get("positions", {}).get(KEY)
if p is None:
    print(f"WARN: position {KEY} not found"); sys.exit(1)

shares_remaining = float(p.get("size_shares", 0))
print(f"\nPosition remaining: {shares_remaining:.2f} sh (avg ${p.get('avg_entry')})")

if shares_remaining < 0.5:
    print("Nothing to sell."); sys.exit(0)

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"NO bid/ask: ${bid:.4f}/${ask:.4f}  new limit ${LIMIT_PRICE}")

# Step 3: place new limit sell
result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares_remaining)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"Order placed: {oid[:24]}... size={result.get('size_shares')}")
print(f"Sitting @ ${LIMIT_PRICE} GTC — fills when buyers bid up")
print(f"At full fill: revenue ~${shares_remaining * LIMIT_PRICE:.2f}")
