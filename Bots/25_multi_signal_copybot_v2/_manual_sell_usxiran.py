"""Manual sell: 50% of US x Iran permanent peace deal by April 22 @ $0.22.

Executed 2026-04-15 at user's explicit request.
Uses executor.place_limit_sell (which goes through safe_sell for precision).
After fill, records the sell in tracker via tracker.record_sell.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

KEY = "0x76b0d903f5a13baa99c2592d8971909cd4e8e4508956e51badba792b1e601504"
LIMIT_PRICE = 0.22

# --- Load position ---
data = tracker.load()
pos = data["positions"].get(KEY)
if not pos:
    print(f"ERROR: position {KEY[:20]} not found")
    sys.exit(1)

title = pos.get("title", "?")
current_shares = float(pos.get("size_shares", 0) or 0)
token_id = pos.get("token_id", "")
sell_shares = round(current_shares * 0.5, 2)

print(f"Position      : {title}")
print(f"Current shares: {current_shares}")
print(f"Selling 50%   : {sell_shares} sh @ limit ${LIMIT_PRICE}")
print(f"Expected rev  : ${sell_shares * LIMIT_PRICE:.2f}")
print()

# --- Place sell (goes through safe_sell precision check) ---
result = executor.place_limit_sell(token_id=token_id, price=LIMIT_PRICE, shares=sell_shares)

if not result:
    print("SELL failed (place_limit_sell returned None).")
    sys.exit(2)

if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SELL skipped — on-chain balance too low: {result.get('onchain')}")
    sys.exit(3)

print(f"Order placed  : order_id={result.get('order_id')[:16]}...")
print(f"  size_shares : {result.get('size_shares')}")
print(f"  price       : {result.get('price')}")

# --- Wait for fill ---
print("Waiting for fill (up to 300s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=300)
status = fill.get("status", "UNKNOWN")
matched = float(fill.get("size_matched") or 0)
original = float(fill.get("size_original") or sell_shares)

print(f"  Status      : {status}")
print(f"  Matched     : {matched} / {original} ({fill.get('filled_pct', 0)*100:.1f}%)")

if matched < 0.5:
    print("Nothing filled. No tracker update.")
    sys.exit(4)

# --- Record partial or full sell ---
revenue = round(matched * LIMIT_PRICE, 2)
reason = "manual_50%_usxiran_april22"
if status != "MATCHED":
    reason += "_partial"

data = tracker.load()
tracker.record_sell(data, KEY, matched, LIMIT_PRICE, revenue, reason)
print()
print(f"RECORDED in tracker: sold {matched} sh @ ${LIMIT_PRICE} = ${revenue:.2f}")
avg = float(pos.get("avg_entry", 0) or 0)
pnl = revenue - (matched * avg)
print(f"PnL on this slice : ${pnl:+.2f}")

data = tracker.load()
pos_after = data["positions"][KEY]
print(f"Remaining shares  : {pos_after.get('size_shares')}")
