"""Cancel GTC sell order and market-sell ALL remaining NO shares on POTUS week."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "8645739410699309255723712337953202603299613672752563309810773074070571201206"  # NO
OLD_GTC = "0x43b292b7825b53da35d79e33935540cf051bda3ae8e52ccab16e5510ceb90054"

# 1. Cancel GTC order (and log any partial fills)
print("--- Step 1: cancel GTC order ---")
d = executor.get_order_details(OLD_GTC)
old_matched = float(d.get("size_matched", 0) or 0)
old_size = float(d.get("size_original", 0) or 0)
old_status = d.get("status", "?")
print(f"Old GTC: {old_status}  matched {old_matched:.2f}/{old_size}")

if old_status == "LIVE":
    ok = executor.cancel_order(OLD_GTC)
    print(f"  Cancel: {ok}")
    time.sleep(2)

# Record any partial fill from the old GTC before cancel
if old_matched > 0.5:
    real = executor.get_actual_fill(OLD_GTC)
    ap = real["vwap"] if real and real["size"] > 0 else 0.70
    rev = real["cost_usd"] if real and real["size"] > 0 else old_matched * 0.70
    data = tracker.load()
    for k, p in (data.get("positions") or {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open":
            cs = float(p.get("size_shares", 0))
            cc = float(p.get("cost_usd", 0))
            cost_sold = cc * (old_matched / cs) if cs > 0 else 0
            p["size_shares"] = round(cs - old_matched, 4)
            p["cost_usd"] = round(cc - cost_sold, 4)
            p.setdefault("sells", []).append({
                "shares": round(old_matched, 4),
                "price": round(ap, 6),
                "revenue": round(rev, 4),
                "pnl": round(rev - cost_sold, 4),
                "reason": "gtc_limit70_partial_before_market_sell",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            tracker.save(data)
            print(f"  recorded partial: {old_matched:.2f} sh @ ${ap:.4f}")
            break

# 2. Get real on-chain balance (safer than tracker)
print("\n--- Step 2: get on-chain balance ---")
onchain = get_wallet_balance(OUR_WALLET, TOKEN)
print(f"On-chain: {onchain:.4f} sh")
SHARES = round(onchain - 0.01, 2)  # small safety margin
print(f"Will sell: {SHARES} sh")

# 3. Fetch orderbook, place aggressive market sell
print("\n--- Step 3: aggressive market sell ---")
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
# Go 3c below bid to ensure we cross and walk the book
LIMIT_PRICE = round(max(bid - 0.03, 0.01), 4)
print(f"Placing market sell: {SHARES} sh @ limit ${LIMIT_PRICE}")
print(f"  (crosses the book — will match against best bids, avg price ~${bid:.3f})")

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
    print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

    # Update tracker
    data = tracker.load()
    for k, p in (data.get("positions") or {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open":
            cs = float(p.get("size_shares", 0))
            cc = float(p.get("cost_usd", 0))
            # Sell up to what's in tracker; any excess on-chain is dust
            sell_shares = min(matched, cs)
            cost_sold = cc * (sell_shares / cs) if cs > 0 else 0
            pnl = revenue - cost_sold
            p["size_shares"] = round(cs - sell_shares, 4)
            p["cost_usd"] = round(cc - cost_sold, 4)
            p.setdefault("sells", []).append({
                "shares": round(matched, 4),
                "price": round(actual_price, 6),
                "revenue": round(revenue, 4),
                "pnl": round(pnl, 4),
                "reason": "manual_all_remaining_market_sell",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if p["size_shares"] < 0.5:
                p["status"] = "sold"
            tracker.save(data)
            print(f"\n[OK] sold {matched:.2f} sh @ ${actual_price:.4f}")
            print(f"  revenue ${revenue:.2f}  PnL ${pnl:+.2f}")
            print(f"  remaining: {p['size_shares']:.2f} sh  status={p['status']}")
            break
else:
    print("Nothing filled within timeout")
