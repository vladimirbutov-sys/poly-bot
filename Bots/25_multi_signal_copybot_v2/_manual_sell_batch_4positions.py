"""Batch sell: 4 partial-exit orders at current best bid.

User's request 2026-04-18:
  1. Hormuz traffic returns to normal April YES — sell 40%
  2. Trump agree to Iranian enrichment April YES — sell 50%
  3. US x Iran permanent peace deal Apr 22 YES — sell 50% (booking loss)
  4. Trump announces end of military operations Apr 21 YES — sell 30% (booking loss)

Each fires sequentially via place_limit_sell at best bid. Bid usually fills
instantly because limit at bid = aggressive sell that lifts the bid.
"""
import sys, io, time, math, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

PLAN = [
    {'substr': 'strait of hormuz traffic returns to normal by end of april', 'pct': 0.40,
     'reason_tag': 'manual_40pct_hormuz_2026-04-18'},
    {'substr': 'will trump agree to iranian enrichment of uranium in april', 'pct': 0.50,
     'reason_tag': 'manual_50pct_trump_enrichment_2026-04-18'},
    {'substr': 'us x iran permanent peace deal by april 22', 'pct': 0.50,
     'reason_tag': 'manual_50pct_peace_apr22_2026-04-18'},
    {'substr': 'trump announces end of military operations against iran by april 21st', 'pct': 0.30,
     'reason_tag': 'manual_30pct_endmil_apr21_2026-04-18'},
]

WATCH_PER_ORDER = 60   # seconds to wait per order (limit at bid usually fills instantly)

results = []

for spec in PLAN:
    print('=' * 80)
    data = tracker.load()
    matched_key = None
    matched_pos = None
    for k, p in data['positions'].items():
        if p.get('status') != 'open':
            continue
        if spec['substr'] in (p.get('title') or '').lower().strip():
            matched_key = k
            matched_pos = p
            break

    if not matched_pos:
        print(f"NOT FOUND: {spec['substr']}")
        results.append({'spec': spec, 'status': 'not_found'})
        continue

    title = matched_pos.get('title', '?')
    token = matched_pos.get('token_id')
    avg = float(matched_pos.get('avg_entry') or 0)
    onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
    available = min(float(matched_pos.get('size_shares', 0)), onchain or 0)
    sell_sh = math.floor(available * spec['pct'] * 100) / 100

    bid, ask = filters.get_orderbook_prices(token)
    print(f"{title[:55]}")
    print(f"  shares avail : {available}")
    print(f"  selling {spec['pct']*100:.0f}% : {sell_sh}")
    print(f"  bid/ask      : ${bid:.3f} / ${ask:.3f}")
    print(f"  limit price  : ${bid:.3f}")
    print(f"  expected rev : ${sell_sh * bid:.2f}")
    print(f"  PnL slice    : ${(bid - avg) * sell_sh:+.2f}")

    if sell_sh < 0.5:
        print("  TOO SMALL — skipping")
        results.append({'spec': spec, 'status': 'too_small'})
        continue

    res = executor.place_limit_sell(token_id=token, price=bid, shares=sell_sh)
    if isinstance(res, dict) and res.get('error') == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
        print(f"  SKIP onchain insufficient: {res.get('onchain')}")
        results.append({'spec': spec, 'status': 'insufficient'})
        continue
    if not res or not res.get('order_id'):
        print(f"  ORDER PLACEMENT FAILED")
        results.append({'spec': spec, 'status': 'place_failed'})
        continue

    oid = res['order_id']
    requested = float(res.get('size_shares') or sell_sh)
    print(f"  ORDER LIVE: {oid[:24]}... size={requested}")

    # Watch briefly
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
    print(f"  FINAL: {final_status}  matched={final_matched:.2f}/{requested}")

    if final_matched > 0.5:
        revenue = round(final_matched * bid, 2)
        data2 = tracker.load()
        tracker.record_sell(data2, matched_key, final_matched, bid, revenue, spec['reason_tag'])
        pnl = revenue - (final_matched * avg)
        print(f"  RECORDED: {final_matched:.2f} sh @ ${bid:.3f} = ${revenue:.2f}  PnL: ${pnl:+.2f}")
        results.append({'spec': spec, 'status': 'sold', 'shares': final_matched,
                        'price': bid, 'revenue': revenue, 'pnl': pnl})
    else:
        print(f"  NOTHING FILLED — order remains live (will be GTC)")
        results.append({'spec': spec, 'status': 'not_filled', 'order_id': oid})

print()
print('=' * 80)
print('BATCH SUMMARY:')
print('=' * 80)
total_rev = 0
total_pnl = 0
for r in results:
    if r.get('status') == 'sold':
        total_rev += r['revenue']
        total_pnl += r['pnl']
        print(f"  ✓ SOLD  {r['shares']:>7.2f} sh @ ${r['price']:.3f} = ${r['revenue']:>7.2f}  PnL ${r['pnl']:+.2f}  | {r['spec']['substr'][:45]}")
    elif r.get('status') == 'not_filled':
        print(f"  ⚠ LIVE  ({r['order_id'][:24]}...)  | {r['spec']['substr'][:45]}")
    else:
        print(f"  ✗ {r.get('status'):<12}                                      | {r['spec']['substr'][:45]}")
print('-' * 80)
print(f'  TOTAL revenue: ${total_rev:.2f}')
print(f'  TOTAL PnL    : ${total_pnl:+.2f}')
