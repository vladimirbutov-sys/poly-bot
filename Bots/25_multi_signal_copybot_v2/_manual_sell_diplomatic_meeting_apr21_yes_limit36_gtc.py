"""Passive GTC sell: 100% of US x Iran diplomatic meeting by April 21 YES @ $0.36."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "10825770508982253966577236303666571711538785796333843502583628816512489950358"
LIMIT_PRICE = 0.36
WATCH_SECONDS = 60

data = tracker.load()
position_key = None
for k, p in (data.get("positions") or {}).items():
    if p.get("token_id") == TOKEN and p.get("status") == "open":
        position_key = k
        break
if not position_key:
    print("No open position"); sys.exit(1)

onchain = get_wallet_balance(OUR_WALLET, TOKEN)
SHARES = round(onchain - 0.01, 2)
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Position: {onchain:.4f} sh on-chain")
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Placing GTC SELL: {SHARES} sh @ ${LIMIT_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")
print(f"Watching {WATCH_SECONDS}s (no auto-cancel)...")

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    d = executor.get_order_details(oid)
    status = d.get("status", "UNKNOWN")
    matched = float(d.get("size_matched", 0) or 0)
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] matched {matched:.2f}")
        last_matched = matched
    if status == "MATCHED":
        print("  FULLY MATCHED"); break
    time.sleep(6)

d = executor.get_order_details(oid)
final_status = d.get("status", "UNKNOWN")
final_matched = float(d.get("size_matched", 0) or 0)
print(f"\nFinal: {final_status}  matched {final_matched:.2f}/{SHARES}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
    revenue = real["cost_usd"] if real and real["size"] > 0 else final_matched * LIMIT_PRICE

    data = tracker.load()
    p = data["positions"][position_key]
    cs = float(p.get("size_shares", 0))
    cc = float(p.get("cost_usd", 0))
    cost_sold = cc * (final_matched / cs) if cs > 0 else 0
    pnl = revenue - cost_sold
    p["size_shares"] = round(cs - final_matched, 4)
    p["cost_usd"] = round(cc - cost_sold, 4)
    p.setdefault("sells", []).append({
        "shares": round(final_matched, 4),
        "price": round(actual_price, 6),
        "revenue": round(revenue, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_100pct_limit36_gtc",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if p["size_shares"] < 0.5:
        p["status"] = "sold"
    tracker.save(data)
    print(f"[OK] sold {final_matched:.2f} sh @ ${actual_price:.4f}  revenue ${revenue:.2f}  PnL ${pnl:+.2f}")
    print(f"  remaining: {p['size_shares']:.2f} sh  status={p['status']}")

if final_status != "MATCHED":
    print(f"\nORDER REMAINS LIVE (GTC): {oid}")
    print(f"  {SHARES - final_matched:.2f} sh @ ${LIMIT_PRICE} waiting for buyer")
