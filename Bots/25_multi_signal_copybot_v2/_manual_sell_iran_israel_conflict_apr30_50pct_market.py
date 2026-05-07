"""Manual sell: 50% YES on Iran x Israel/US conflict ends by April 30 @ best market bid."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "103971336418419351548990142781195320713490282483637854831265186666012554199721"  # YES
PCT = 0.50

data = tracker.load()
position_key = None
total_shares = 0.0
for k, p in (data.get("positions") or {}).items():
    if p.get("token_id") == TOKEN and p.get("status") == "open":
        position_key = k
        total_shares = float(p.get("size_shares") or 0)
        break
if not position_key:
    print("No open position"); sys.exit(1)

onchain = get_wallet_balance(OUR_WALLET, TOKEN)
bid, ask = filters.get_orderbook_prices(TOKEN)
shares_to_sell = round(total_shares * PCT, 2)
LIMIT_PRICE = round(max(bid - 0.005, 0.01), 4)

print(f"Position: {total_shares} sh  on-chain {onchain:.4f}")
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Selling 50% = {shares_to_sell} sh @ aggressive limit ${LIMIT_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares_to_sell)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched", 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
    revenue = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE

    data = tracker.load()
    p = data["positions"][position_key]
    cs = float(p.get("size_shares", 0))
    cc = float(p.get("cost_usd", 0))
    cost_sold = cc * (matched / cs) if cs > 0 else 0
    pnl = revenue - cost_sold
    p["size_shares"] = round(cs - matched, 4)
    p["cost_usd"] = round(cc - cost_sold, 4)
    p.setdefault("sells", []).append({
        "shares": round(matched, 4),
        "price": round(actual_price, 6),
        "revenue": round(revenue, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_50pct_market_aggressive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if p["size_shares"] < 0.5:
        p["status"] = "sold"
    tracker.save(data)
    print(f"\n[OK] sold {matched:.2f} sh @ ${actual_price:.4f}")
    print(f"  revenue ${revenue:.2f}  PnL ${pnl:+.2f}")
    print(f"  remaining: {p['size_shares']:.2f} sh  status={p['status']}")
else:
    print("Nothing filled")
