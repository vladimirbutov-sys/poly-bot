"""Cancel $0.68 limit, place new limit SELL 100% Trump POTUS NO @ $0.66."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "8645739410699309255723712337953202603299613672752563309810773074070571201206"
KEY   = "0xmanual_4afbba32986b1a7d8acfca3b51061eb5"
LIMIT_PRICE = 0.66

c = executor._get_client()
orders = [o for o in c.get_orders() if str(o.get('asset_id','')) == TOKEN]
for o in orders:
    if o.get('side') == 'SELL':
        oid_full = o.get('id', '')
        print(f"Cancelling {oid_full[:24]}... @ ${o.get('price')} size={o.get('original_size')}")
        executor.cancel_order(oid_full)
        time.sleep(2)

data = tracker.load()
p = data.get("positions", {}).get(KEY)
shares = float(p.get("size_shares", 0))
print(f"Position: {shares:.2f} sh (cost ${p.get('cost_usd')}  avg ${p.get('avg_entry')})")

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"NO bid/ask: ${bid:.4f}/${ask:.4f}  new limit ${LIMIT_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"Order placed: {oid[:24]}... size={result.get('size_shares')}")
print(f"At full fill: revenue ~${shares * LIMIT_PRICE:.2f}  vs cost $104.08 → PnL ~${shares * LIMIT_PRICE - 104.08:+.2f}")
