"""Top-up Trump POTUS NO: $95 at limit $0.66 (crosses asks $0.651/$0.653)."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xc6c25c2150b2e2c7758ee0ad8640324f60086367fc689f0bca618621c890a2c6"
TOKEN = "8645739410699309255723712337953202603299613672752563309810773074070571201206"
TITLE = 'Will Trump post "POTUS" this week on Truth Social?'
SLUG  = "will-trump-post-potus-this-week-on-truth-social"
LIMIT_PRICE = 0.66
SIZE_USD = 95.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"NO bid/ask: ${bid:.3f}/${ask:.3f}  limit ${LIMIT_PRICE}")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={res.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

    # Find existing NO position and top it up
    data = tracker.load()
    found_key = None
    for k, p in data.get("positions", {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open" and p.get("outcome") == "No":
            found_key = k; break
    if found_key:
        p = data["positions"][found_key]
        old_sh = float(p.get("size_shares", 0))
        old_cost = float(p.get("cost_usd", 0))
        new_sh = old_sh + matched
        new_cost = round(old_cost + actual_cost, 4)
        new_avg = new_cost / new_sh if new_sh > 0 else 0
        p["size_shares"] = round(new_sh, 4)
        p["cost_usd"] = new_cost
        p["avg_entry"] = round(new_avg, 6)
        p["parts_filled"] = p.get("parts_filled", 0) + 1
        p.setdefault("order_ids", []).append(oid)
        tracker.save(data)
        print(f"✓ Topped up position {found_key}")
        print(f"  total: {new_sh:.2f} sh, cost ${new_cost:.2f}, avg ${new_avg:.4f}")
    else:
        print(f"WARN: existing NO position not found, creating new")
        new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
        data.setdefault('positions', {})[new_key] = {
            "condition_id": CID, "token_id": TOKEN, "title": TITLE,
            "outcome": "No", "event_slug": SLUG,
            "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
            "size_shares": round(matched, 2), "cost_usd": actual_cost,
            "tier": "manual", "strategy": "manual", "signal_player": "manual",
            "parts_filled": 1, "parts_planned": 1,
            "order_ids": [oid],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "open", "sells": [], "final_pnl": 0,
        }
        tracker.save(data)
