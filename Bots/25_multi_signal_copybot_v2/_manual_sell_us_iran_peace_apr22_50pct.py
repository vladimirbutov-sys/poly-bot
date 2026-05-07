"""Sell 50% of US x Iran peace deal Apr 22 YES @ limit $0.43.

User's request 2026-04-17. Position 566 sh @ avg $0.196, cost $111.
Selling half (~283 sh) at $0.43 — bid is exactly there, fills immediately.
Expected PnL slice: ~+$66.
"""
import sys, io, time, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell
from config import OUR_WALLET

KEY_PREFIX = "0x6437009bb5cf689c37c8a58da3f605812110d645f79de8c19991b09aed190955"
LIMIT_PRICE = 0.43
SELL_PCT = 0.50
WATCH_SECONDS = 120

data = tracker.load()
full_key = None
pos = None
for k, p in data["positions"].items():
    if k.startswith(KEY_PREFIX):
        full_key = k; pos = p; break
if not pos or pos.get("status") != "open":
    print("Position not open — abort"); sys.exit(1)

token = pos.get("token_id", "")
tracker_shares = float(pos.get("size_shares", 0) or 0)
onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
available = min(tracker_shares, onchain or 0)
shares = math.floor(available * SELL_PCT * 100) / 100

print(f"Tracker shares : {tracker_shares}")
print(f"On-chain       : {onchain}")
print(f"Selling 50%    : {shares} sh @ limit ${LIMIT_PRICE}")
avg = float(pos.get("avg_entry", 0) or 0)
print(f"Entry avg      : ${avg:.4f}")
print(f"Expected gross : ${shares * LIMIT_PRICE:.2f}")
print(f"Expected PnL   : ${(LIMIT_PRICE - avg) * shares:+.2f}")
print()

result = executor.place_limit_sell(token_id=token, price=LIMIT_PRICE, shares=shares)
if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SKIP: insufficient onchain {result.get('onchain')}"); sys.exit(2)
if not result or not result.get("order_id"):
    print("Order placement failed"); sys.exit(3)

order_id = result["order_id"]
requested = float(result.get("size_shares") or shares)
print(f"ORDER LIVE: {order_id[:24]}... size={requested}")
print(f"Watching {WATCH_SECONDS}s...")
print()

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    details = executor.get_order_details(order_id)
    status = details.get("status", "UNKNOWN")
    matched = float(details.get("size_matched", 0) or 0)
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>3}s] status={status} matched={matched:.2f}")
        last_matched = matched
    if status == "MATCHED":
        print("  → FULLY MATCHED"); break
    time.sleep(6)

details = executor.get_order_details(order_id)
final_status = details.get("status", "UNKNOWN")
final_matched = float(details.get("size_matched", 0) or 0)
print()
print(f"Final: status={final_status}  matched={final_matched:.2f}/{requested}")

if final_matched > 0.5:
    revenue = round(final_matched * LIMIT_PRICE, 2)
    data = tracker.load()
    tracker.record_sell(data, full_key, final_matched, LIMIT_PRICE, revenue,
                        "manual_50%_us_iran_peace_apr22_limit43")
    pnl = revenue - (final_matched * avg)
    print(f"RECORDED: {final_matched:.2f} sh @ ${LIMIT_PRICE} = ${revenue:.2f}  PnL: ${pnl:+.2f}")

if final_status != "MATCHED":
    print()
    print(f"ORDER REMAINS LIVE: {order_id}")
    print(f"  Remaining ~{requested - final_matched:.2f} sh on book GTC")
