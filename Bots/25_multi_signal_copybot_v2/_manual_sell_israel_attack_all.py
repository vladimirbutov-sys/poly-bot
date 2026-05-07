"""Sell ALL remaining Israel conduct military action against Iran by Apr 21 YES @ bid."""
import sys, io, time, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

KEY_PREFIX = "0xhedge_8aeb7cdb6fc5db066e9a9e"

data = tracker.load()
full_key = None; pos = None
for k, p in data['positions'].items():
    if k.startswith(KEY_PREFIX):
        full_key = k; pos = p; break
if not pos or pos.get('status') != 'open':
    print("Position not open"); sys.exit(1)

token = pos.get('token_id')
tracker_sh = float(pos.get('size_shares', 0))
onchain = safe_sell.get_wallet_balance(OUR_WALLET, token)
available = min(tracker_sh, onchain or 0)
shares = math.floor(available * 100) / 100
bid, ask = filters.get_orderbook_prices(token)
avg = float(pos.get('avg_entry', 0))

print(f"Tracker: {tracker_sh} sh  on-chain: {onchain}  selling: {shares}")
print(f"bid/ask: ${bid:.3f}/${ask:.3f}")
print(f"avg entry: ${avg:.4f}")
print(f"Expected revenue at bid: ${shares * bid:.2f}  PnL ${(bid - avg) * shares:+.2f}")

res = executor.place_limit_sell(token_id=token, price=bid, shares=shares)
if isinstance(res, dict) and res.get('error') == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SKIP insufficient: {res.get('onchain')}"); sys.exit(2)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(3)

oid = res['order_id']
print(f"ORDER LIVE: {oid[:24]}...")

last = 0.0
start = time.time()
while time.time() - start < 120:
    d = executor.get_order_details(oid)
    s = d.get('status', 'UNKNOWN')
    m = float(d.get('size_matched', 0) or 0)
    if m > last + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] status={s} matched={m:.2f}")
        last = m
    if s == 'MATCHED':
        print('  → FULLY MATCHED'); break
    time.sleep(5)

d = executor.get_order_details(oid)
final_status = d.get('status', 'UNKNOWN')
final_matched = float(d.get('size_matched', 0) or 0)
print(f"Final: {final_status}  matched {final_matched:.2f}/{shares}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else bid
    revenue = round(final_matched * actual_price, 2)
    data2 = tracker.load()
    tracker.record_sell(data2, full_key, final_matched, actual_price, revenue,
                        'manual_sell_all_israel_attack_apr21_2026-04-19')
    pnl = revenue - final_matched * avg
    print(f"RECORDED: {final_matched:.2f} sh @ ${actual_price:.4f} = ${revenue}  PnL ${pnl:+.2f}")

if final_status != 'MATCHED':
    print(f"\nPARTIAL / LIVE — {shares - final_matched:.2f} sh remain on book at ${bid}")
