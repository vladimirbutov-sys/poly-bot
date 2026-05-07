"""Just keep trying to place BUY @ $0.13 until CLOB comes back (up to 60 min)."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "10065719129703851524738159766241582795004980250212999796913119632612444350346"
LIMIT_PRICE = 0.13
SIZE_USD = 32.0
MAX_RETRIES = 720   # 720 × 5s = 60 min

for attempt in range(MAX_RETRIES):
    try:
        res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
        if res and res.get('order_id'):
            oid = res['order_id']
            print(f"[{attempt}] ORDER LIVE: {oid[:24]} size={res.get('size_shares')}")
            fill = executor.wait_for_fill_with_details(oid, timeout=90)
            print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")
            matched = float(fill.get('size_matched', 0) or 0)
            if matched > 0.5:
                real = executor.get_actual_fill(oid)
                ap = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
                cost = round(matched * ap, 2)
                print(f"  VWAP ${ap:.4f} cost ${cost:.2f}")
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
                        print(f"✓ Topped up: {nsh:.2f} sh @ avg ${navg:.4f}")
                        break
            sys.exit(0)
    except Exception as e:
        if '425' in str(e):
            if attempt % 12 == 0:  # log every minute
                print(f"[{attempt}] still 425, waiting…")
        else:
            print(f"[{attempt}] ERR: {e}")
    time.sleep(5)

print("FAIL: 60 min timeout")
