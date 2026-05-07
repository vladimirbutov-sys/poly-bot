"""Top-up: buy remaining $59 YES on Hormuz blockade lifted May 31 @ $0.81."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "926377706175971731068420551849041218012736398250875962020506643091812084572"
LIMIT_PRICE = 0.81
SIZE_USD = 59.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Top-up BUY: ${SIZE_USD} @ limit ${LIMIT_PRICE}")

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
    print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

    # Find the existing manual position for this token and top it up
    data = tracker.load()
    merged = False
    for k, p in (data.get('positions') or {}).items():
        if (p.get('token_id') == TOKEN and p.get('status') == 'open'
                and p.get('signal_player') == 'manual'):
            cur_sh = float(p.get('size_shares') or 0)
            cur_cost = float(p.get('cost_usd') or 0)
            new_sh = cur_sh + matched
            new_cost = cur_cost + actual_cost
            p['size_shares'] = round(new_sh, 4)
            p['cost_usd'] = round(new_cost, 4)
            p['avg_entry'] = round(new_cost / new_sh, 6) if new_sh > 0 else 0
            p.setdefault('order_ids', []).append(oid)
            p['_last_topup'] = datetime.now(timezone.utc).isoformat()
            tracker.save(data)
            print(f"\u2713 Topped up {k[:24]}... to {new_sh:.2f} sh, cost ${new_cost:.2f}, avg ${p['avg_entry']:.4f}")
            merged = True
            break
    if not merged:
        print("No existing position found — created standalone is not safe, please inspect")
