"""Sell 100% of both NO positions on US x Iran diplomatic meeting markets.

Apr 27 NO  — 78.95 sh,  avg $0.948,  cost $74.84
Apr 28 NO  — 81.53 sh,  avg $0.92,   cost $75.01

Strategy: limit at current best bid → instant cross. No auto-cancel: any
unfilled remainder stays GTC and tracker.sync_with_onchain will catch later fills.
"""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

PLAN = [
    {
        'tag': 'Apr 27 NO',
        'key': '0xmanual_51827dc08225712e02b26985c75b8fe8',
        'token': '92079910675159907375467354284229768948316964233795313847482829094812147958054',
        'reason_tag': 'manual_100pct_diplomatic_apr27_no_2026-04-26',
    },
    {
        'tag': 'Apr 28 NO',
        'key': '0xmanual_3e6ffd7acacd4823e59cd47d55b7fe9d',
        'token': '42277247300059455315872150222700537525647929202778246138550488342397262489345',
        'reason_tag': 'manual_100pct_diplomatic_apr28_no_2026-04-26',
    },
]

WATCH_PER_ORDER = 60

results = []

for spec in PLAN:
    print('=' * 80)
    print(f"{spec['tag']}")
    data = tracker.load()
    pos = data.get('positions', {}).get(spec['key'])
    if pos is None or pos.get('status') != 'open':
        print(f"  POSITION NOT OPEN  status={pos and pos.get('status')}")
        results.append({'spec': spec, 'status': 'not_open'})
        continue

    title = pos.get('title', '?')
    token = pos.get('token_id')
    avg = float(pos.get('avg_entry') or 0)
    tracker_sh = float(pos.get('size_shares', 0) or 0)
    onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
    available = min(tracker_sh, onchain or 0)

    bid, ask = filters.get_orderbook_prices(token)
    print(f"  title       : {title}")
    print(f"  tracker sh  : {tracker_sh}")
    print(f"  on-chain sh : {onchain}")
    print(f"  selling     : {available} (100%)")
    print(f"  bid/ask     : ${bid:.4f} / ${ask:.4f}")
    print(f"  limit price : ${bid:.4f}  (crosses bid → instant fill)")
    print(f"  expected rev: ${available * bid:.2f}")
    print(f"  PnL slice   : ${(bid - avg) * available:+.2f}")

    if available < 0.5:
        print("  TOO SMALL — skipping")
        results.append({'spec': spec, 'status': 'too_small'})
        continue

    res = executor.place_limit_sell(token_id=token, price=bid, shares=available)
    if isinstance(res, dict) and res.get('error') == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
        print(f"  SKIP onchain insufficient: {res.get('onchain')}")
        results.append({'spec': spec, 'status': 'insufficient'})
        continue
    if not res or not res.get('order_id'):
        print(f"  ORDER PLACEMENT FAILED")
        results.append({'spec': spec, 'status': 'place_failed'})
        continue

    oid = res['order_id']
    requested = float(res.get('size_shares') or available)
    print(f"  ORDER LIVE  : {oid[:24]}... size={requested}")

    last_matched = 0.0
    start = time.time()
    while time.time() - start < WATCH_PER_ORDER:
        details = executor.get_order_details(oid)
        status = details.get('status', 'UNKNOWN')
        matched = float(details.get('size_matched', 0) or 0)
        if matched > last_matched + 0.01:
            print(f"    [+{int(time.time()-start):>2}s] status={status} matched={matched:.2f}")
            last_matched = matched
        if status == 'MATCHED':
            print('    → FULLY MATCHED')
            break
        time.sleep(5)

    final = executor.get_order_details(oid)
    final_status = final.get('status', 'UNKNOWN')
    final_matched = float(final.get('size_matched', 0) or 0)
    print(f"  FINAL       : {final_status}  matched={final_matched:.2f}/{requested}")

    if final_matched > 0.5:
        real = executor.get_actual_fill(oid)
        if real and real.get('size', 0) > 0:
            actual_price = real['vwap']
            revenue = real['cost_usd']
        else:
            actual_price = bid
            revenue = round(final_matched * bid, 2)

        data2 = tracker.load()
        tracker.record_sell(data2, spec['key'], final_matched, actual_price, revenue, spec['reason_tag'])
        pnl = revenue - (final_matched * avg)
        print(f"  RECORDED    : {final_matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}  PnL ${pnl:+.2f}")
        results.append({'spec': spec, 'status': 'sold', 'shares': final_matched,
                        'price': actual_price, 'revenue': revenue, 'pnl': pnl,
                        'remaining': requested - final_matched, 'order_id': oid})
    else:
        print(f"  NOTHING FILLED — order remains live (GTC)")
        results.append({'spec': spec, 'status': 'live', 'order_id': oid})

print()
print('=' * 80)
print('BATCH SUMMARY')
print('=' * 80)
total_rev = 0.0
total_pnl = 0.0
for r in results:
    s = r.get('status')
    tag = r['spec']['tag']
    if s == 'sold':
        total_rev += r['revenue']
        total_pnl += r['pnl']
        rem = r.get('remaining', 0)
        rem_str = f" (live remainder {rem:.2f} sh)" if rem > 0.5 else ""
        print(f"  ✓ SOLD  {tag}  {r['shares']:.2f} sh @ ${r['price']:.4f} = ${r['revenue']:.2f}  PnL ${r['pnl']:+.2f}{rem_str}")
    elif s == 'live':
        print(f"  ⚠ LIVE  {tag}  order {r['order_id'][:24]}...")
    else:
        print(f"  ✗ {s:<14} {tag}")
print('-' * 80)
print(f'  TOTAL revenue : ${total_rev:.2f}')
print(f'  TOTAL PnL     : ${total_pnl:+.2f}')
