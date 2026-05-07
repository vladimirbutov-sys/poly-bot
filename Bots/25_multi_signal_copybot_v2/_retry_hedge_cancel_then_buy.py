"""Retry loop: cancel old $0.12 BUY, then place new $0.13 BUY on <25 ships YES."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "10065719129703851524738159766241582795004980250212999796913119632612444350346"
LIMIT_PRICE = 0.13
SIZE_USD = 32.0
MAX_RETRIES = 120   # 120 × 5s = 10 min max

# PHASE 1: cancel old $0.12 order — retry until success
c = executor._get_client()
cancelled = False
for attempt in range(MAX_RETRIES):
    try:
        orders = [o for o in c.get_orders() if str(o.get('asset_id','')) == TOKEN]
        buy_orders = [o for o in orders if o.get('side') == 'BUY']
        if not buy_orders:
            print(f"[{attempt}] No BUY orders to cancel — proceeding")
            cancelled = True
            break
        for o in buy_orders:
            oid_f = o.get('id','')
            try:
                executor.cancel_order(oid_f)
                print(f"[{attempt}] Cancelled {oid_f[:24]} @ ${o.get('price')}")
            except Exception as e:
                if '425' in str(e):
                    print(f"[{attempt}] Cancel 425 — retry in 5s")
                    break
                else:
                    raise
        # Recheck
        time.sleep(2)
        orders2 = [o for o in c.get_orders() if str(o.get('asset_id','')) == TOKEN and o.get('side') == 'BUY']
        if not orders2:
            cancelled = True
            print(f"[{attempt}] All BUY orders cancelled ✓")
            break
    except Exception as e:
        print(f"[{attempt}] Cancel error: {e}")
    time.sleep(5)

if not cancelled:
    print("FAIL: could not cancel old order after max retries"); sys.exit(1)

# PHASE 2: place new buy @ $0.13 — retry until success
time.sleep(3)
for attempt in range(MAX_RETRIES):
    try:
        bid, ask = filters.get_orderbook_prices(TOKEN)
        print(f"[buy {attempt}] bid/ask ${bid:.4f}/${ask:.4f}")
        res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
        if res and res.get('order_id'):
            oid = res['order_id']
            print(f"ORDER LIVE: {oid[:24]}... size={res.get('size_shares')}")
            fill = executor.wait_for_fill_with_details(oid, timeout=90)
            print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")
            matched = float(fill.get('size_matched', 0) or 0)
            if matched > 0.5:
                real = executor.get_actual_fill(oid)
                ap = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
                cost = round(matched * ap, 2)
                print(f"  VWAP ${ap:.4f}  cost ${cost:.2f}")
                data = tracker.load()
                for k, p in data.get('positions', {}).items():
                    if p.get('token_id') == TOKEN and p.get('status') == 'open' and p.get('outcome') == 'Yes':
                        osh = float(p.get('size_shares', 0))
                        oc = float(p.get('cost_usd', 0))
                        nsh = osh + matched
                        nc = round(oc + cost, 4)
                        navg = nc / nsh if nsh > 0 else 0
                        p['size_shares'] = round(nsh, 4)
                        p['cost_usd'] = nc
                        p['avg_entry'] = round(navg, 6)
                        p['parts_filled'] = p.get('parts_filled', 0) + 1
                        p.setdefault('order_ids', []).append(oid)
                        tracker.save(data)
                        print(f"✓ Topped up: {nsh:.2f} sh @ avg ${navg:.4f}, cost ${nc:.2f}")
                        break
            sys.exit(0)
    except Exception as e:
        if '425' in str(e):
            print(f"[buy {attempt}] BUY 425 — retry in 5s")
        else:
            print(f"[buy {attempt}] ERR: {e}")
    time.sleep(5)

print("FAIL: could not place buy after max retries")
