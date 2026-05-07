"""Top-up: $200 NO on Trump announces end of military operations against Iran by April 30 @ limit $0.94."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0xfa59099fbda1e0f0058ed3cbd57e939fe90ab6d9b57d53bd488bcadf75c191d4"
TOKEN = "43306201559293677467902878784200227711843675662189772539825649733291552996303"  # NO
TITLE = "Trump announces end of military operations against Iran by April 30th?"
EVENT_SLUG = ""
OUTCOME = "No"
SIZE_USD = 200.0
LIMIT_PRICE = 0.94  # best ask, deep liquidity

print(f"BUY {OUTCOME} @ ${LIMIT_PRICE}, size ${SIZE_USD}")
result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result or not result.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = result['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if real and real['size'] > 0 else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f} cost ${actual_cost:.2f}")

    data = tracker.load()
    existing_key = None
    for k, p in data.get('positions', {}).items():
        if p.get('condition_id') == CID and p.get('token_id') == TOKEN and p.get('status') == 'open':
            existing_key = k
            break

    if existing_key:
        p = data['positions'][existing_key]
        old_sh = float(p.get('size_shares', 0) or 0)
        old_cost = float(p.get('cost_usd', 0) or 0)
        new_sh = old_sh + matched
        new_cost = round(old_cost + actual_cost, 2)
        new_avg = round(new_cost / new_sh, 6) if new_sh > 0 else actual_price
        p['size_shares'] = round(new_sh, 2)
        p['cost_usd'] = new_cost
        p['avg_entry'] = new_avg
        p.setdefault('order_ids', []).append(oid)
        p['parts_filled'] = (p.get('parts_filled', 1) or 1) + 1
        p['parts_planned'] = (p.get('parts_planned', 1) or 1) + 1
        tracker.save(data)
        print(f"OK Merged into {existing_key[:24]}: {old_sh:.2f}+{matched:.2f}={new_sh:.2f} sh, avg ${new_avg:.4f}, total cost ${new_cost:.2f}")
    else:
        new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
        data.setdefault('positions', {})[new_key] = {
            "condition_id": CID, "token_id": TOKEN, "title": TITLE,
            "outcome": OUTCOME, "event_slug": EVENT_SLUG,
            "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
            "size_shares": round(matched, 2), "cost_usd": actual_cost,
            "tier": "manual", "strategy": "manual", "signal_player": "manual",
            "parts_filled": 1, "parts_planned": 1, "order_ids": [oid],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "open", "sells": [], "final_pnl": 0,
            "_adopted_from": "manual_buy_2026-04-25_trump_end_ops_apr30_no_topup200",
        }
        tracker.save(data)
        print(f"OK Recorded new: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
else:
    print("Nothing filled"); sys.exit(2)
