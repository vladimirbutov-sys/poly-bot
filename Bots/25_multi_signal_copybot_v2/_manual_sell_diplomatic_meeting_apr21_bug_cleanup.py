"""Bug cleanup: sell remaining 12 sh NO on US x Iran diplomatic meeting by April 21.

Position was left open by the 2026-04-21 cumul>100% follow-sell bug (see
_analytics/2026-04-21_follow_sell_cumulative_bug.md). Fix applied, but
this specific position needs manual cleanup.
"""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "17672950353917556724323355261458951468235130062273241703548640979565238082018"  # NO

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

print(f"Position: {onchain:.4f} sh on-chain")
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Selling {SHARES} sh @ aggressive limit ${LIMIT_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=90)
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
    # cost_usd in tracker is STALE (see bug analysis doc §6). Use proportional
    # method but cap at matched*avg_entry if that is lower, so PnL isn't wildly off.
    proportional_cost = cc * (matched / cs) if cs > 0 else 0
    avg = float(p.get("avg_entry", 0) or 0)
    price_based_cost = matched * avg if avg > 0 else proportional_cost
    # Use the smaller (more conservative) of the two for PnL calc
    cost_sold = min(proportional_cost, price_based_cost) if avg > 0 else proportional_cost
    pnl = revenue - cost_sold
    p["size_shares"] = round(cs - matched, 4)
    p["cost_usd"] = round(max(cc - cost_sold, 0), 4)
    p.setdefault("sells", []).append({
        "shares": round(matched, 4),
        "price": round(actual_price, 6),
        "revenue": round(revenue, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_bug_cleanup_cumul_saturation_fix",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if p["size_shares"] < 0.5:
        p["status"] = "sold"
    tracker.save(data)
    print(f"\n[OK] sold {matched:.2f} sh @ ${actual_price:.4f}")
    print(f"  revenue ${revenue:.2f}  PnL ~${pnl:+.2f} (tracker cost_usd drift noted)")
    print(f"  remaining: {p['size_shares']:.2f} sh  status={p['status']}")
else:
    print("Nothing filled")
