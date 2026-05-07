"""GTC limit-sell 100% on two NO positions.

Kurds independence NO  — 309.27 sh @ limit $0.97  (above current bid $0.965)
Iran gay marriage NO   — 102.25 sh @ limit $0.98  (above current bid $0.977)

Both above bid → GTC, will sit on book. Watch 90s for partial fills, do NOT
cancel; remainder stays live and tracker.sync_with_onchain catches later fills.
"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

PLAN = [
    {
        'tag': 'Kurds independence NO',
        'key': '0xmanual_f4a7675c84c37044162b46b',  # prefix match
        'cid': '0x15fcf94587789dcd26efd4a31a1dbc8ff80c3c0bbfed1ca7eb90a054fda6efbf',
        'token': '70121850046492348784549902420135388646858612857008496798342833461244578139670',
        'limit': 0.97,
        'reason_tag': 'manual_100pct_kurds_independence_no_2026-04-26_gtc097',
    },
    {
        'tag': 'Iran gay marriage NO',
        'key': '0xmanual_5f7528b95f9ebfe0c0e40df',  # prefix match
        'cid': '0xb0a9e9c70cd5bff7feb2b7038ff7e37412b07a8bcfc2e4aff1568aff77641cc4',
        'token': '107171737619314142212827016886886005382319261850070382453179959313987657965300',
        'limit': 0.98,
        'reason_tag': 'manual_100pct_gay_marriage_no_2026-04-26_gtc098',
    },
]

WATCH_PER_ORDER = 90
results = []

for spec in PLAN:
    print('=' * 80)
    print(f"{spec['tag']}")
    data = tracker.load()
    matched_key = None
    matched_pos = None
    for k, p in data['positions'].items():
        if k.startswith(spec['key']) and p.get('status') == 'open' \
                and p.get('condition_id') == spec['cid'] and p.get('token_id') == spec['token']:
            matched_key = k
            matched_pos = p
            break

    if not matched_pos:
        print(f"  POSITION NOT FOUND  (prefix {spec['key']})")
        results.append({'spec': spec, 'status': 'not_found'})
        continue

    title = matched_pos.get('title', '?')
    token = matched_pos.get('token_id')
    avg = float(matched_pos.get('avg_entry') or 0)
    tracker_sh = float(matched_pos.get('size_shares', 0) or 0)
    onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
    available = min(tracker_sh, onchain or 0)

    bid, ask = filters.get_orderbook_prices(token)
    print(f"  title       : {title}")
    print(f"  available   : {available} sh (100%)")
    print(f"  bid/ask     : ${bid:.4f} / ${ask:.4f}")
    print(f"  limit       : ${spec['limit']:.4f}  (GTC, sits on book)")
    print(f"  potential rev (full fill): ${available * spec['limit']:.2f}")
    print(f"  potential PnL (full fill): ${(spec['limit'] - avg) * available:+.2f}")

    if available < 0.5:
        print("  TOO SMALL — skipping")
        results.append({'spec': spec, 'status': 'too_small'})
        continue

    res = executor.place_limit_sell(token_id=token, price=spec['limit'], shares=available)
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
    print(f"  Watching {WATCH_PER_ORDER}s (NO auto-cancel)...")

    last_matched = 0.0
    start = time.time()
    while time.time() - start < WATCH_PER_ORDER:
        details = executor.get_order_details(oid)
        status = details.get('status', 'UNKNOWN')
        matched = float(details.get('size_matched', 0) or 0)
        if matched > last_matched + 0.01:
            print(f"    [+{int(time.time()-start):>2}s] status={status} matched={matched:.2f} (+{matched-last_matched:.2f})")
            last_matched = matched
        if status == 'MATCHED':
            print('    → FULLY MATCHED')
            break
        time.sleep(8)

    final = executor.get_order_details(oid)
    final_status = final.get('status', 'UNKNOWN')
    final_matched = float(final.get('size_matched', 0) or 0)
    print(f"  FINAL       : {final_status}  matched={final_matched:.2f}/{requested}")

    if final_matched > 0.5:
        # Conservative: record at limit. Actual VWAP ≥ limit (taker pays ≥ our ask).
        revenue = round(final_matched * spec['limit'], 2)
        data2 = tracker.load()
        tracker.record_sell(data2, matched_key, final_matched, spec['limit'], revenue, spec['reason_tag'])
        pnl = revenue - (final_matched * avg)
        rem = requested - final_matched
        print(f"  RECORDED    : {final_matched:.2f} sh @ ${spec['limit']:.4f} = ${revenue:.2f}  PnL ${pnl:+.2f}")
        if rem > 0.5:
            print(f"  REMAINDER LIVE: {rem:.2f} sh on book (order {oid[:24]}...)")
        results.append({'spec': spec, 'status': 'partial' if rem > 0.5 else 'sold',
                        'shares': final_matched, 'price': spec['limit'],
                        'revenue': revenue, 'pnl': pnl, 'remaining': rem, 'order_id': oid})
    else:
        print(f"  NOTHING FILLED — order LIVE on book at ${spec['limit']:.4f} GTC")
        results.append({'spec': spec, 'status': 'live', 'order_id': oid, 'remaining': requested})

print()
print('=' * 80)
print('BATCH SUMMARY')
print('=' * 80)
total_rev = 0.0
total_pnl = 0.0
total_live = 0.0
for r in results:
    s = r.get('status')
    tag = r['spec']['tag']
    if s in ('sold', 'partial'):
        total_rev += r['revenue']
        total_pnl += r['pnl']
        rem = r.get('remaining', 0)
        if rem > 0.5:
            total_live += rem
            print(f"  ◐ PARTIAL  {tag:<25}  {r['shares']:.2f} filled @ ${r['price']:.3f} = ${r['revenue']:.2f}  PnL ${r['pnl']:+.2f}  | remainder {rem:.2f} sh LIVE")
        else:
            print(f"  ✓ SOLD     {tag:<25}  {r['shares']:.2f} sh @ ${r['price']:.3f} = ${r['revenue']:.2f}  PnL ${r['pnl']:+.2f}")
    elif s == 'live':
        total_live += r['remaining']
        print(f"  ⚠ LIVE     {tag:<25}  {r['remaining']:.2f} sh on book @ {r['spec']['limit']}  (order {r['order_id'][:20]}...)")
    else:
        print(f"  ✗ {s:<10} {tag}")
print('-' * 80)
print(f'  Filled revenue: ${total_rev:.2f}')
print(f'  Filled PnL    : ${total_pnl:+.2f}')
print(f'  Live on book  : {total_live:.2f} sh (waiting for buyers)')
