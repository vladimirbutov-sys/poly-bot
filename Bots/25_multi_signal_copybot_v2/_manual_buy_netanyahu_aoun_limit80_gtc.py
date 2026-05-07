"""GTC limit BUY: Netanyahu-Aoun NO @ $0.80 for $75.

Sits on the book (new best bid) since current ask is $0.92 — won't fill
instantly. Watches 180s for any partial fill, records what filled at REAL
VWAP, leaves remainder live on the book.

Any subsequent fills after watch window → bot's tracker.sync_with_onchain
forward-scan will catch the on-chain balance increase and add via
onchain_sync_up. If that sync uses estimated cost rather than real VWAP,
avg_entry may drift slightly. Run this script's recording logic again later
if you want to refresh from real trades.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x6fa05bcbb53efaf95bf5053388f0eb040b1c4ebab2ece4c37cd74bbe3167e625"
TOKEN = "23330623927523224976798170032966383651796457473765550056022078478545665896004"
TITLE = "Will Netanyahu talk to Joseph Aoun by April 30?"
SLUG  = "will-netanyahu-talk-to-joseph-aoun-by"
OUTCOME = "No"
LIMIT_PRICE = 0.80
SIZE_USD = 75.0
WATCH_SECONDS = 180

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")
print(f"Placing GTC BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE} (size ${SIZE_USD})")
if LIMIT_PRICE >= ask:
    print(f"  → at/above ask — will fill instantly")
else:
    print(f"  → below ask — sits on book as best bid until taker comes")
print()

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed.")
    sys.exit(1)

order_id = result["order_id"]
req_size = float(result.get("size_shares") or 0)
print(f"ORDER LIVE: order_id={order_id[:20]}...  size={req_size}")
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

# Final poll — DO NOT cancel
details = executor.get_order_details(order_id)
final_status = details.get("status", "UNKNOWN")
final_matched = float(details.get("size_matched", 0) or 0)
print()
print(f"Final poll: status={final_status}  matched={final_matched:.2f} / {req_size}")

# Record any fills via REAL VWAP
if final_matched > 0.5:
    real = executor.get_actual_fill(order_id)
    if real and real["size"] > 0:
        actual_price = real["vwap"]
        actual_cost = real["cost_usd"]
        print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}  (limit was ${LIMIT_PRICE})")
    else:
        actual_price = LIMIT_PRICE
        actual_cost = final_matched * LIMIT_PRICE
        print(f"  [WARN] no trade rows — falling back to limit ${actual_price}")

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
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
        "_adopted_from": "manual_buy_2026-04-17_gtc_limit80",
    }
    tracker.save(data)
    print(f"\n✓ Recorded as {new_key[:24]}... | {final_matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
    print("  consolidate_duplicates will merge with existing 0xmanual_c6038565... NO position next cycle")
else:
    print("Nothing filled in watch window. Order is LIVE on the book.")

if final_status != "MATCHED":
    print()
    print(f"ORDER REMAINS LIVE: order_id {order_id}")
    print(f"  Remaining ~{req_size - final_matched:.2f} sh @ ${LIMIT_PRICE} GTC")
    print(f"  Bot's tracker.sync_with_onchain (forward scan) will catch any later fill")
    print(f"  and add to the existing manual NO position via onchain_sync_up.")
