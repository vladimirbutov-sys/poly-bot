"""Rotation: SELL all Apr 15 conflict-ends YES, BUY $400 of Apr 30 same series.

User's request 2026-04-19. Apr 15 deadline already past (likely YES resolution
soon); price jumped to $0.83 today — exit at profit. Apr 30 still has time.
"""
import sys, io, time, hashlib, math
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, safe_sell, filters
from config import OUR_WALLET

# ====== STEP 1: SELL ALL Apr 15 ======
print('=' * 80)
print('STEP 1: SELL ALL Iran x Israel/US conflict ends Apr 15 YES')
print('=' * 80)

data = tracker.load()
apr15_positions = []
for k,p in data['positions'].items():
    t = (p.get('title') or '').lower()
    if 'iran x israel/us conflict ends by april 15' in t and p.get('status')=='open' and p.get('outcome')=='Yes':
        apr15_positions.append((k, p))

if not apr15_positions:
    print('No Apr 15 position found, aborting.')
    sys.exit(1)

# All positions share same token, take from first
key, pos = apr15_positions[0]
TOKEN_15 = pos.get('token_id')
total_tracker = sum(float(p.get('size_shares',0)) for _,p in apr15_positions)
onchain_15 = safe_sell.get_wallet_balance(OUR_WALLET, TOKEN_15)
shares_to_sell = min(total_tracker, onchain_15 or 0)
shares_to_sell = math.floor(shares_to_sell * 100) / 100

bid_15, ask_15 = filters.get_orderbook_prices(TOKEN_15)
print(f'Apr 15 bid: ${bid_15:.3f}, ask: ${ask_15:.3f}')
print(f'Tracker total: {total_tracker:.2f} sh  on-chain: {onchain_15}  selling: {shares_to_sell}')

# Sell at bid (aggressive, instant fill)
res_sell = executor.place_limit_sell(token_id=TOKEN_15, price=bid_15, shares=shares_to_sell)
if isinstance(res_sell, dict) and res_sell.get('error') == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f'SKIP onchain insufficient: {res_sell.get("onchain")}')
    sys.exit(2)
if not res_sell or not res_sell.get('order_id'):
    print('SELL ORDER FAILED')
    sys.exit(3)

oid_sell = res_sell['order_id']
print(f'SELL ORDER LIVE: {oid_sell[:24]}...')

# Watch up to 90s
last_m = 0.0
start = time.time()
while time.time() - start < 90:
    d = executor.get_order_details(oid_sell)
    s = d.get('status', 'UNKNOWN')
    m = float(d.get('size_matched', 0) or 0)
    if m > last_m + 0.01:
        print(f'  [+{int(time.time()-start):>2}s] status={s} matched={m:.2f}')
        last_m = m
    if s == 'MATCHED':
        print('  → FULLY MATCHED'); break
    time.sleep(5)

d_final = executor.get_order_details(oid_sell)
sell_status = d_final.get('status', 'UNKNOWN')
sell_matched = float(d_final.get('size_matched', 0) or 0)
print(f'SELL final: {sell_status}  matched: {sell_matched:.2f}')

if sell_matched > 0.5:
    real = executor.get_actual_fill(oid_sell)
    if real and real['size'] > 0:
        actual_sell_price = real['vwap']
        actual_revenue = real['cost_usd']
        print(f'  real VWAP: ${actual_sell_price:.4f}  revenue ${actual_revenue:.2f}')
    else:
        actual_sell_price = bid_15
        actual_revenue = sell_matched * bid_15
    # Distribute the sell across multiple positions (proportionally)
    data2 = tracker.load()
    remaining_to_record = sell_matched
    for k_p, p_p in apr15_positions:
        pos_sh = float(data2['positions'][k_p].get('size_shares', 0))
        if pos_sh < 0.5: continue
        share = min(pos_sh, remaining_to_record)
        if share < 0.5: continue
        rev_share = round(share * actual_sell_price, 2)
        tracker.record_sell(data2, k_p, share, actual_sell_price, rev_share,
                            'manual_sell_all_apr15_rotate_2026-04-19')
        remaining_to_record -= share
        if remaining_to_record < 0.5: break
    sell_pnl = actual_revenue - sum(float(p.get('cost_usd',0)) for _,p in apr15_positions
                                     if float(p.get('size_shares',0)) > 0.5) * (sell_matched / total_tracker)
    print(f'  RECORDED across {len(apr15_positions)} positions, revenue ${actual_revenue:.2f}')
else:
    print('SELL did not fill — not proceeding to BUY (need cash)')
    sys.exit(4)

# ====== STEP 2: BUY $400 Apr 30 ======
print()
print('=' * 80)
print('STEP 2: BUY $400 Iran x Israel/US conflict ends Apr 30 YES')
print('=' * 80)

CID_30   = "0xa6ddb7146f48a12dbf73456d654211b01d7493829932c31b7fe85d82120d338f"
TOKEN_30 = "103971336418419351548990142781195320713490282483637854831265186666012554199721"
TITLE_30 = "Iran x Israel/US conflict ends by April 30?"
SLUG_30  = "iran-x-israelus-conflict-ends-by"
SIZE_USD = 400.0

bid_30, ask_30 = filters.get_orderbook_prices(TOKEN_30)
LIMIT_30 = round(math.ceil((ask_30 + 0.005) * 100) / 100, 2)
print(f'Apr 30 bid/ask: ${bid_30:.3f}/${ask_30:.3f}  limit: ${LIMIT_30}')

res_buy = executor.place_limit_buy(token_id=TOKEN_30, price=LIMIT_30, size_usd=SIZE_USD)
if not res_buy or not res_buy.get('order_id'):
    print('BUY ORDER FAILED')
    sys.exit(5)

oid_buy = res_buy['order_id']
req_buy = float(res_buy.get('size_shares') or 0)
print(f'BUY ORDER LIVE: {oid_buy[:24]}... size={req_buy}')

# Watch
last_m = 0.0
start = time.time()
while time.time() - start < 180:
    d = executor.get_order_details(oid_buy)
    s = d.get('status', 'UNKNOWN')
    m = float(d.get('size_matched', 0) or 0)
    if m > last_m + 0.01:
        print(f'  [+{int(time.time()-start):>2}s] status={s} matched={m:.2f}')
        last_m = m
    if s == 'MATCHED':
        print('  → FULLY MATCHED'); break
    time.sleep(5)

d_final = executor.get_order_details(oid_buy)
buy_status = d_final.get('status', 'UNKNOWN')
buy_matched = float(d_final.get('size_matched', 0) or 0)
print(f'BUY final: {buy_status}  matched: {buy_matched:.2f}/{req_buy}')

if buy_matched > 0.5:
    real_b = executor.get_actual_fill(oid_buy)
    if real_b and real_b['size'] > 0:
        actual_buy_price = real_b['vwap']
        actual_buy_cost = real_b['cost_usd']
        print(f'  real VWAP: ${actual_buy_price:.4f}  cost ${actual_buy_cost:.2f}')
    else:
        actual_buy_price = LIMIT_30
        actual_buy_cost = buy_matched * LIMIT_30
        print(f'  [WARN] no trade rows — fallback to limit')

    data3 = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID_30}_{TOKEN_30}_{time.time()}".encode()).hexdigest()[:32]
    data3.setdefault('positions', {})[new_key] = {
        "condition_id": CID_30, "token_id": TOKEN_30, "title": TITLE_30,
        "outcome": "Yes", "event_slug": SLUG_30,
        "entry_price": round(actual_buy_price, 6), "avg_entry": round(actual_buy_price, 6),
        "size_shares": round(buy_matched, 2), "cost_usd": round(actual_buy_cost, 2),
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid_buy],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-19_iran_conflict_apr30_rotate",
    }
    tracker.save(data3)
    print(f'  RECORDED: {buy_matched:.2f} sh @ ${actual_buy_price:.4f} = ${actual_buy_cost:.2f}')

print()
print('=' * 80)
print('ROTATION COMPLETE')
print('=' * 80)
PYEOF
