"""Cancel the passive GTC limit BUY on US x Iran peace deal Apr 22 YES @ $0.13."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor

TOKEN = "10355316169421062771540371697837923442956106006258739802114788264214901200573"

client = executor._get_client()
try:
    orders = client.get_orders(params=None)
except TypeError:
    orders = client.get_orders()

open_orders = [o for o in (orders or []) if str(o.get("asset_id")) == TOKEN and o.get("side", "").upper() == "BUY"]
print(f"Found {len(open_orders)} open BUY order(s) on this token:")
for o in open_orders:
    oid = o.get("id") or o.get("order_id")
    price = o.get("price")
    size = o.get("original_size") or o.get("size")
    matched = o.get("size_matched") or 0
    print(f"  {oid[:24]}... price={price} size={size} matched={matched}")

for o in open_orders:
    oid = o.get("id") or o.get("order_id")
    price = float(o.get("price") or 0)
    if abs(price - 0.13) < 0.001:
        print(f"\nCancelling {oid[:24]}... @ ${price}")
        ok = executor.cancel_order(oid)
        print(f"  result: {ok}")
