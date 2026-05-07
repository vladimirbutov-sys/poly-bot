"""Batch buy: Trump end military operations vs Iran
  - $50 YES by April 30 @ $0.29
  - $125 YES by May 31 @ $0.69
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

PLAN = [
    {
        'CID': '0xfa59099fbda1e0f0058ed3cbd57e939fe90ab6d9b57d53bd488bcadf75c191d4',
        'TOKEN': '112434828665041337854033745240098052999773438249964130665844574663228374653496',
        'TITLE': 'Trump announces end of military operations against Iran by April 30th?',
        'SLUG':  'trump-announces-end-of-military-operations-against-iran-by',
        'LIMIT': 0.29,
        'SIZE':  50.0,
        'REASON': 'manual_buy_2026-04-19_trump_end_military_apr30',
    },
    {
        'CID': '0x57c1e8de9d359a76055fe1be95e46a1e72d0537811dcc2ccf070cdfa73d8ba33',
        'TOKEN': '88235774871095952577870395590885258537861888267109065817501809685441370257453',
        'TITLE': 'Trump announces end of military operations against Iran by May 31st?',
        'SLUG':  'trump-announces-end-of-military-operations-against-iran-by',
        'LIMIT': 0.69,
        'SIZE':  125.0,
        'REASON': 'manual_buy_2026-04-19_trump_end_military_may31',
    },
]

results = []
for spec in PLAN:
    print('=' * 80)
    print(spec['TITLE'][:70])
    bid, ask = filters.get_orderbook_prices(spec['TOKEN'])
    print(f"  Live bid/ask: ${bid:.3f}/${ask:.3f}  limit ${spec['LIMIT']}  size ${spec['SIZE']}")

    result = executor.place_limit_buy(token_id=spec['TOKEN'], price=spec['LIMIT'], size_usd=spec['SIZE'])
    if not result or not result.get('order_id'):
        print('  PLACE FAILED'); results.append({'spec':spec,'status':'failed'}); continue

    oid = result['order_id']
    req = float(result.get('size_shares') or 0)
    print(f"  ORDER LIVE: {oid[:24]}... size={req}")

    fill = executor.wait_for_fill_with_details(oid, timeout=120)
    status = fill.get('status','UNKNOWN')
    matched = float(fill.get('size_matched',0) or 0)
    print(f"  {status}  matched {matched:.2f}/{req}")

    if matched > 0.5:
        real = executor.get_actual_fill(oid)
        if real and real['size'] > 0:
            actual_price = real['vwap']
        else:
            actual_price = spec['LIMIT']
        actual_cost = round(matched * actual_price, 2)
        print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

        data = tracker.load()
        new_key = "0xmanual_" + hashlib.md5(f"{spec['CID']}_{spec['TOKEN']}_{time.time()}".encode()).hexdigest()[:32]
        data.setdefault('positions', {})[new_key] = {
            "condition_id": spec['CID'], "token_id": spec['TOKEN'],
            "title": spec['TITLE'], "outcome": "Yes", "event_slug": spec['SLUG'],
            "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
            "size_shares": round(matched, 2), "cost_usd": actual_cost,
            "tier": "manual", "strategy": "manual", "signal_player": "manual",
            "parts_filled": 1, "parts_planned": 1,
            "order_ids": [oid],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "open", "sells": [], "final_pnl": 0,
            "_adopted_from": spec['REASON'],
        }
        tracker.save(data)
        results.append({'spec':spec,'status':'bought','shares':matched,'price':actual_price,'cost':actual_cost})
    else:
        results.append({'spec':spec,'status':'not_filled','oid':oid})

print()
print('=' * 80)
print('BATCH SUMMARY')
for r in results:
    if r['status'] == 'bought':
        print(f"  ✓ {r['shares']:>6.2f} sh @ ${r['price']:.4f} = ${r['cost']:>7.2f}  | {r['spec']['TITLE'][:55]}")
    else:
        print(f"  ✗ {r['status']}  | {r['spec']['TITLE'][:55]}")
