"""Reprice: cancel SELL @ 0.98 and place SELL @ 0.978 on Iran legalize gay marriage."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor

TOKEN = "107171737619314142212827016886886005382319261850070382453179959313987657965300"
NEW_PRICE = 0.978
SHARES = 102.24
OLD_OID = "0xb1df51e49312b346d8578e478b4fdb1c13a07ad49da7dc5b8a87691c24eab9e8"

# Step 1: cancel old
print(f"Cancelling old order {OLD_OID[:24]}... @ 0.98")
ok = executor.cancel_order(OLD_OID)
print(f"  cancel result: {ok}")

import time
time.sleep(2)

# Step 2: place new
print(f"Placing new SELL {SHARES} sh @ ${NEW_PRICE}")
res = executor.place_limit_sell(token_id=TOKEN, price=NEW_PRICE, shares=SHARES)
if not res or not res.get("order_id"):
    print("PLACE FAILED:", res)
    sys.exit(1)
oid = res["order_id"]
print(f"OK new order: {oid}")
print(f"   size:  {res.get('size_shares')}")
