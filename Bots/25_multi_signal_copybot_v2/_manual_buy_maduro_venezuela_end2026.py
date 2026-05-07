"""One-shot manual buy: Maduro Venezuela end-of-2026 Yes for $46 at market.

Executed 2026-04-17 at user's explicit request.
Bot's HORIZON_TIERS filter blocks this market (258d > 120d) so bot never
entered on its own. User overrides manually. Position will be tracked
with signal_player="manual" so follow-sell works if denizz sells.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x67f3f8d0a0ecdfc008c99650284a4674388a8c3029b0eb7ca0abd65dde8d996f"
TOKEN = "37090128566507509913630589460372620352013766554886380785463533062224343545231"
TITLE = "Will Nicolás Maduro be the leader of Venezuela end of 2026?"
SLUG  = "will-nicols-maduro-be-the-leader-of-venezuela-end-of-2026"
OUTCOME = "Yes"
SIZE_USD = 46.0

# Fetch live best ask, set limit = ask + 1c buffer (rounded to tick).
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")

LIMIT_PRICE = round(ask + 0.01, 2)
print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE} (ask+1c buffer), size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)

if not result:
    print("BUY order failed. Aborting — no tracker write.")
    sys.exit(1)

print(f"BUY placed: order_id={result.get('order_id')[:16]}...")
print(f"  shares: {result.get('size_shares')}, cost_usd: {result.get('cost_usd'):.2f}")

print("Waiting for fill (up to 300s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=300)
print(f"  fill status: {fill.get('status')} | matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

if fill.get("status") not in ("MATCHED", "PARTIAL"):
    print(f"Order did not fill (status={fill.get('status')}). Not recording.")
    sys.exit(2)

matched = float(fill.get("size_matched") or 0)
# Polymarket's get_order returns the LIMIT price, not VWAP. Pull real fills.
real = executor.get_actual_fill(result["order_id"])
if real and real["size"] > 0:
    actual_price = real["vwap"]
    actual_cost = real["cost_usd"]
    print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}  (limit was ${LIMIT_PRICE})")
else:
    actual_price = float(fill.get("price") or LIMIT_PRICE)
    actual_cost = matched * actual_price
    print(f"  [WARN] no trade rows — falling back to limit price ${actual_price}")

data = tracker.load()
new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]

data.setdefault("positions", {})[new_key] = {
    "condition_id": CID,
    "token_id": TOKEN,
    "title": TITLE,
    "outcome": OUTCOME,
    "event_slug": SLUG,
    "entry_price": actual_price,
    "avg_entry": actual_price,
    "size_shares": round(matched, 2),
    "cost_usd": round(actual_cost, 2),
    "tier": "manual",
    "strategy": "manual",
    "signal_player": "manual",
    "parts_filled": 1,
    "parts_planned": 1,
    "order_ids": [result.get("order_id", "")],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "open",
    "sells": [],
    "final_pnl": 0,
    "_adopted_from": "manual_buy_2026-04-17",
}
tracker.save(data)
print(f"\n✓ Recorded in tracker as {new_key[:20]}...")
print(f"  shares: {matched:.2f}, cost: ${actual_cost:.2f}, entry: ${actual_price}")
