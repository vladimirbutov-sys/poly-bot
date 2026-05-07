"""Manual sell: 139 sh YES Peace Apr 30 cleanup (stuck after TIMEOUT incident).
Bot's follow-sell at $0.22 timed out 22.04 01:19, retry at $0.216 also timed
out. Bid collapsed to $0.14. This is what the adaptive retry fix would have
handled — for now close manually.
"""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "64575112906857627673396031002364315784778510108272214779568803819416675082435"  # YES Peace Apr 30

data = tracker.load()
position_key = None
for k, p in (data.get("positions") or {}).items():
    if p.get("token_id") == TOKEN and p.get("status") == "open":
        position_key = k
        break
if not position_key:
    print("No open position"); sys.exit(1)

onchain = get_wallet_balance(OUR_WALLET, TOKEN)
bid, ask = filters.get_orderbook_prices(TOKEN)
SHARES = round(onchain - 0.01, 2)
LIMIT_PRICE = round(max(bid - 0.01, 0.01), 4)

print(f"On-chain: {onchain:.4f} sh")
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Selling {SHARES} sh @ aggressive ${LIMIT_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES)
if not result or not result.get("order_id"):
    print("FAILED"); sys.exit(1)
oid = result["order_id"]
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched", 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    ap = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
    rev = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE

    data = tracker.load()
    p = data["positions"][position_key]
    cs = float(p.get("size_shares", 0))
    cc = float(p.get("cost_usd", 0))
    cost_sold = cc * (matched / cs) if cs > 0 else 0
    pnl = rev - cost_sold
    p["size_shares"] = round(cs - matched, 4)
    p["cost_usd"] = round(max(cc - cost_sold, 0), 4)
    p.setdefault("sells", []).append({
        "shares": round(matched, 4),
        "price": round(ap, 6),
        "revenue": round(rev, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_cleanup_timeout_retry_bugfix_20260422",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if p["size_shares"] < 0.5:
        p["status"] = "sold"
    tracker.save(data)
    print(f"\n[OK] sold {matched:.2f} sh @ ${ap:.4f}")
    print(f"  revenue ${rev:.2f}  PnL ${pnl:+.2f}")
    print(f"  remaining: {p['size_shares']:.2f} sh  status={p['status']}")
else:
    print("Nothing filled")
