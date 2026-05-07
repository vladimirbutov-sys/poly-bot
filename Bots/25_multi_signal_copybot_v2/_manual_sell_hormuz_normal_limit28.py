"""Place a GTC sell on Hormuz-normal-April position at limit $0.28.

Sells 50% of current position (294.62 / 589.246 sh).
Do NOT auto-cancel on timeout — leave it live on the book.
Capture any partial fill within 180s and record it; remaining sits on book.
"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell
from config import OUR_WALLET

KEY_PREFIX = "0xc230fd"
LIMIT_PRICE = 0.28
SELL_PCT = 0.50
WATCH_SECONDS = 180

data = tracker.load()
full_key = None
pos = None
for k, p in data["positions"].items():
    if k.startswith(KEY_PREFIX):
        full_key = k; pos = p
        break
if not pos or pos.get("status") != "open":
    print("Position not open — abort")
    sys.exit(1)

token = pos.get("token_id", "")
tracker_shares = float(pos.get("size_shares", 0) or 0)
onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
available = min(tracker_shares, onchain or 0)

# 50% of the smaller of tracker/onchain, rounded down to 2 decimals (CLOB precision)
import math
shares = math.floor(available * SELL_PCT * 100) / 100

print(f"Tracker shares : {tracker_shares}")
print(f"On-chain       : {onchain}")
print(f"Selling 50%    : {shares} sh @ limit ${LIMIT_PRICE}  (GTC, will stay on book)")
print(f"Entry          : ${pos.get('entry_price')} — expected PnL slice if fully filled: ${(LIMIT_PRICE - float(pos.get('avg_entry') or 0)) * shares:+.2f}")
print()

result = executor.place_limit_sell(token_id=token, price=LIMIT_PRICE, shares=shares)
if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SKIP: insufficient onchain {result.get('onchain')}")
    sys.exit(2)
if not result or not result.get("order_id"):
    print("Order placement failed")
    sys.exit(3)

order_id = result["order_id"]
requested_size = float(result.get("size_shares") or shares)
print(f"ORDER LIVE: order_id={order_id[:20]}...  size={requested_size}")
print(f"Watching for {WATCH_SECONDS}s (no auto-cancel)...")
print()

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    details = executor.get_order_details(order_id)
    status = details.get("status", "UNKNOWN")
    matched = float(details.get("size_matched", 0) or 0)
    if matched > last_matched + 0.01:
        delta = matched - last_matched
        print(f"  [+{int(time.time()-start):>3}s] status={status} matched={matched:.2f} (+{delta:.2f})")
        last_matched = matched
    if status == "MATCHED":
        print("  → FULLY MATCHED")
        break
    time.sleep(8)

details = executor.get_order_details(order_id)
final_status = details.get("status", "UNKNOWN")
final_matched = float(details.get("size_matched", 0) or 0)
print()
print(f"Final poll: status={final_status}  matched={final_matched:.2f} / {requested_size}")

if final_matched > 0.5:
    revenue = round(final_matched * LIMIT_PRICE, 2)
    data = tracker.load()
    tracker.record_sell(data, full_key, final_matched, LIMIT_PRICE, revenue,
                        "manual_50%_hormuz_normal_limit28")
    avg = float(pos.get("avg_entry", 0) or 0)
    pnl = revenue - (final_matched * avg)
    print(f"RECORDED: {final_matched:.2f} sh @ ${LIMIT_PRICE} = ${revenue:.2f}  PnL slice: ${pnl:+.2f}")
else:
    print("Nothing filled yet. Order is still LIVE on the book.")

if final_status != "MATCHED":
    print()
    print(f"ORDER REMAINS LIVE: order_id {order_id}")
    print(f"  Remaining ~{requested_size - final_matched:.2f} sh @ ${LIMIT_PRICE} GTC")
    print(f"  Bot's sync (onchain_sync_down) will catch any later fill and update tracker.")
