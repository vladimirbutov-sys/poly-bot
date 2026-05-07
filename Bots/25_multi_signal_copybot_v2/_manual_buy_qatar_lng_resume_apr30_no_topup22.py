"""Top-up: $22.08 NO on QatarEnergy LNG resume by April 30 @ $0.67."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "35215605700679698941732970499634840134674905805412260600160248150702604117291"
LIMIT_PRICE = 0.67
SIZE_USD = 22.08

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Top-up: ${SIZE_USD} @ ${LIMIT_PRICE}")

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

    data = tracker.load()
    for k, p in (data.get('positions') or {}).items():
        if (p.get('token_id') == TOKEN and p.get('status') == 'open'
                and p.get('signal_player') == 'manual'):
            cs = float(p.get('size_shares') or 0)
            cc = float(p.get('cost_usd') or 0)
            new_sh = cs + matched
            new_cost = cc + actual_cost
            p['size_shares'] = round(new_sh, 4)
            p['cost_usd'] = round(new_cost, 4)
            p['avg_entry'] = round(new_cost / new_sh, 6) if new_sh > 0 else 0
            p.setdefault('order_ids', []).append(oid)
            tracker.save(data)
            print(f"\u2713 Topped up: {new_sh:.2f} sh cost ${new_cost:.2f} avg ${p['avg_entry']:.4f}")
            break
