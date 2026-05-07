"""List ALL open orders on the wallet."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor

client = executor._get_client()
try:
    orders = client.get_orders(params=None)
except TypeError:
    orders = client.get_orders()

print(f"Total open orders: {len(orders or [])}")
for o in (orders or []):
    oid = o.get("id") or o.get("order_id") or "?"
    side = o.get("side")
    price = o.get("price")
    size = o.get("original_size") or o.get("size")
    matched = o.get("size_matched") or 0
    asset = str(o.get("asset_id") or "")[:20]
    print(f"  {oid[:24]}... side={side} price={price} size={size} matched={matched} token={asset}...")
