"""GTC limit-sell 40% of Trump end military ops Apr30 NO @ limit $0.97.

Position: 523.79 sh, avg $0.9456, cost $495.29 (denizz-driven).
40% = 209.52 sh. Limit $0.97 above current ask $0.96 → GTC, sits on book.
Watch 90s for any cross-fill, do NOT cancel; remainder stays live.
"""
import sys, io, time, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

KEY = "0x4cfdb3e056107ccee3ea680ea2211dfd8b75349d9bf661394f76e77c784582c6"
TOKEN = "43306201559293677467902878784200227711843675662189772539825649733291552996303"
LIMIT_PRICE = 0.97
PCT = 0.40
WATCH = 90
REASON_TAG = "manual_40pct_trump_end_ops_apr30_no_2026-04-26_gtc097"

data = tracker.load()
pos = data['positions'].get(KEY)
if not pos or pos.get('status') != 'open':
    print(f"POSITION NOT OPEN  status={pos and pos.get('status')}")
    sys.exit(1)

title = pos.get('title', '?')
avg = float(pos.get('avg_entry') or 0)
tracker_sh = float(pos.get('size_shares', 0) or 0)
onchain = safe_sell.get_wallet_balance(OUR_WALLET, TOKEN)
available = min(tracker_sh, onchain or 0)
sell_sh = math.floor(available * PCT * 100) / 100

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"{title}")
print(f"  available  : {available} sh")
print(f"  selling 40%: {sell_sh} sh")
print(f"  bid/ask    : ${bid:.4f} / ${ask:.4f}")
print(f"  limit      : ${LIMIT_PRICE:.4f}  (above ask → GTC)")
print(f"  potential rev (full fill): ${sell_sh * LIMIT_PRICE:.2f}")
print(f"  potential PnL slice      : ${(LIMIT_PRICE - avg) * sell_sh:+.2f}")

if sell_sh < 0.5:
    print("TOO SMALL"); sys.exit(2)

res = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=sell_sh)
if isinstance(res, dict) and res.get('error') == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SKIP onchain insufficient: {res.get('onchain')}"); sys.exit(3)
if not res or not res.get('order_id'):
    print("ORDER PLACEMENT FAILED"); sys.exit(4)

oid = res['order_id']
requested = float(res.get('size_shares') or sell_sh)
print(f"  ORDER LIVE : {oid[:24]}... size={requested}")
print(f"  Watching {WATCH}s (NO auto-cancel)...")

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH:
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
print(f"  FINAL      : {final_status}  matched={final_matched:.2f}/{requested}")

if final_matched > 0.5:
    revenue = round(final_matched * LIMIT_PRICE, 2)
    data2 = tracker.load()
    tracker.record_sell(data2, KEY, final_matched, LIMIT_PRICE, revenue, REASON_TAG)
    pnl = revenue - (final_matched * avg)
    rem = requested - final_matched
    print(f"  RECORDED   : {final_matched:.2f} sh @ ${LIMIT_PRICE} = ${revenue:.2f}  PnL ${pnl:+.2f}")
    if rem > 0.5:
        print(f"  REMAINDER LIVE: {rem:.2f} sh on book (order {oid[:24]}...)")
else:
    print(f"  NOTHING FILLED — order LIVE on book at ${LIMIT_PRICE} GTC ({requested:.2f} sh)")
