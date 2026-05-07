"""Batch sell at best BID (aggressive, instant fill):
  1. US-Iran nuclear deal before 2027 NO — 50%
  2. Israel military action against Iran Apr 21 YES — 30%
"""
import sys, io, time, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

PLAN = [
    {'substr': 'us-iran nuclear deal before 2027', 'pct': 0.50,
     'reason_tag': 'manual_50pct_nuclear_2027_2026-04-18'},
    {'substr': 'israel conduct military action against iran by april 21', 'pct': 0.30,
     'reason_tag': 'manual_30pct_israel_attack_apr21_2026-04-18'},
]
WATCH_PER_ORDER = 90  # generous watch — small orders, should be quick

results = []
for spec in PLAN:
    print('=' * 80)
    data = tracker.load()
    matched_key = None; matched_pos = None
    for k, p in data['positions'].items():
        if p.get('status') != 'open': continue
        if spec['substr'] in (p.get('title') or '').lower():
            matched_key = k; matched_pos = p; break
    if not matched_pos:
        print(f"NOT FOUND: {spec['substr']}"); results.append({'spec': spec, 'status':'not_found'}); continue

    title = matched_pos.get('title', '?')
    token = matched_pos.get('token_id')
    avg = float(matched_pos.get('avg_entry') or 0)
    onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
    available = min(float(matched_pos.get('size_shares', 0)), onchain or 0)
    sell_sh = math.floor(available * spec['pct'] * 100) / 100
    bid, ask = filters.get_orderbook_prices(token)

    print(f"{title[:55]}")
    print(f"  available: {available}  selling {spec['pct']*100:.0f}%: {sell_sh}")
    print(f"  bid/ask: ${bid:.3f}/${ask:.3f}  → limit @ BID ${bid:.3f} (aggressive)")
    print(f"  expected revenue: ${sell_sh * bid:.2f}  PnL: ${(bid - avg) * sell_sh:+.2f}")

    if sell_sh < 0.5:
        print("  TOO SMALL"); results.append({'spec': spec, 'status':'too_small'}); continue

    res = executor.place_limit_sell(token_id=token, price=bid, shares=sell_sh)
    if isinstance(res, dict) and res.get('error') == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
        print(f"  SKIP onchain insufficient: {res.get('onchain')}")
        results.append({'spec': spec, 'status':'insufficient'}); continue
    if not res or not res.get('order_id'):
        print(f"  ORDER PLACEMENT FAILED")
        results.append({'spec': spec, 'status':'place_failed'}); continue

    oid = res['order_id']
    requested = float(res.get('size_shares') or sell_sh)
    print(f"  ORDER LIVE: {oid[:24]}... size={requested}")

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
            print('    → FULLY MATCHED'); break
        time.sleep(4)

    final = executor.get_order_details(oid)
    final_status = final.get('status','UNKNOWN')
    final_matched = float(final.get('size_matched',0) or 0)
    print(f"  FINAL: {final_status} matched={final_matched:.2f}/{requested}")

    if final_matched > 0.5:
        revenue = round(final_matched * bid, 2)
        data2 = tracker.load()
        tracker.record_sell(data2, matched_key, final_matched, bid, revenue, spec['reason_tag'])
        pnl = revenue - (final_matched * avg)
        print(f"  RECORDED: {final_matched:.2f} sh @ ${bid:.3f} = ${revenue:.2f}  PnL: ${pnl:+.2f}")
        results.append({'spec': spec, 'status':'sold', 'shares':final_matched,
                        'price':bid, 'revenue':revenue, 'pnl':pnl, 'requested':requested})
    else:
        print(f"  NOTHING FILLED — order LIVE")
        results.append({'spec': spec, 'status':'not_filled', 'order_id':oid})

print('\n' + '='*80)
print('BATCH SUMMARY')
print('='*80)
total_rev = 0; total_pnl = 0
for r in results:
    if r.get('status') == 'sold':
        total_rev += r['revenue']; total_pnl += r['pnl']
        partial = '' if abs(r['shares'] - r.get('requested',0)) < 0.5 else ' [PARTIAL]'
        print(f"  ✓ {r['shares']:>7.2f} sh @ ${r['price']:.3f} = ${r['revenue']:>6.2f}  PnL ${r['pnl']:+.2f}{partial}  | {r['spec']['substr'][:45]}")
    elif r.get('status') == 'not_filled':
        print(f"  ⚠ LIVE on book: {r['order_id'][:24]}...  | {r['spec']['substr'][:45]}")
    else:
        print(f"  ✗ {r.get('status'):<14}  | {r['spec']['substr'][:45]}")
print('-'*80)
print(f"  TOTAL revenue: ${total_rev:.2f}")
print(f"  TOTAL PnL:     ${total_pnl:+.2f}")
