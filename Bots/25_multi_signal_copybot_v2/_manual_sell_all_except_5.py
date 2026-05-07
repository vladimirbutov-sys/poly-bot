"""Sell-all except 5 specified markets, using best-bid sweep for each."""
import sys, io, time, json, os
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
import requests
from dotenv import load_dotenv
load_dotenv('.env')
WALLET = os.getenv('POLYMARKET_WALLET','')

# Markets to KEEP (do not sell). Match by title substring (case-insensitive).
KEEP_TITLE_SUBSTRINGS = [
    "Will Trump agree to Iranian enrichment of uranium in April",
    "Iran agrees to surrender enriched uranium stockpile by April 30, 2026",
    "Iran agrees to end enrichment of uranium by April 30",
    "US x Iran ceasefire extended by April 22, 2026",
    "Israel x Hezbollah Ceasefire extended by April 26, 2026",
]

def is_kept(title: str) -> bool:
    t = (title or "").lower()
    return any(s.lower() in t for s in KEEP_TITLE_SUBSTRINGS)


def get_onchain_size(token_id: str) -> float:
    try:
        r = requests.get('https://data-api.polymarket.com/positions',
                         params={'user': WALLET, 'limit': 200}, timeout=15).json()
        for p in r:
            if str(p.get('asset','')) == token_id:
                return float(p.get('size', 0) or 0)
    except Exception as e:
        print(f"  WARN: on-chain fetch failed: {e}")
    return 0.0


def aggressive_limit(token_id: str, shares_needed: float) -> tuple[float, float]:
    """Return (limit_price, expected_vwap) for a sell that sweeps enough bid liquidity."""
    r = requests.get(f'https://clob.polymarket.com/book?token_id={token_id}', timeout=10).json()
    bids = sorted([(float(b['price']), float(b['size'])) for b in r.get('bids', [])], key=lambda x: -x[0])
    cum_sh = 0.0
    cum_usd = 0.0
    last_p = bids[0][0] if bids else 0.0
    for bp, bs in bids:
        take = min(bs, shares_needed - cum_sh)
        cum_sh += take
        cum_usd += take * bp
        last_p = bp
        if cum_sh >= shares_needed:
            break
    vwap = (cum_usd / cum_sh) if cum_sh > 0 else 0.0
    # Limit goes 1 tick below the deepest level we need (or 5c lower for safety)
    limit_price = max(0.001, round(last_p - 0.005, 4))
    return limit_price, vwap


# Step 1: cancel ALL our open sell orders (we'll replace with sweeping limits)
print("=" * 80)
print("STEP 1: Cancel any live sell orders on positions we plan to sell")
print("=" * 80)
data = tracker.load()
opens = [(k, p) for k, p in data.get('positions', {}).items() if p.get('status') == 'open']

c = executor._get_client()
all_my_orders = c.get_orders()
sell_pending = {str(o.get('asset_id','')): o for o in all_my_orders if o.get('side') == 'SELL'}

cancelled = 0
for k, p in opens:
    if is_kept(p.get('title', '')):
        continue
    tok = p.get('token_id', '')
    if tok in sell_pending:
        oid = sell_pending[tok].get('id', '')
        print(f"  Cancelling {oid[:24]}... (token {tok[:16]}...)")
        try:
            executor.cancel_order(oid)
            cancelled += 1
        except Exception as e:
            print(f"    err: {e}")

print(f"Cancelled {cancelled} orders. Sleeping 3s...")
time.sleep(3)

# Step 2: sell each non-kept position
print()
print("=" * 80)
print("STEP 2: Place sweeping market sells for remaining positions")
print("=" * 80)

results = []
total_revenue = 0.0
total_cost = 0.0
total_pnl = 0.0
sold_count = 0
skipped_count = 0

# Reload tracker before each sell to keep state fresh
for k, p in opens:
    title = p.get('title', '')
    if is_kept(title):
        print(f"\n[KEEP] {title[:65]}")
        skipped_count += 1
        continue

    tok = p.get('token_id', '')
    cid = p.get('condition_id', '')
    out = p.get('outcome', '')
    sh_t = float(p.get('size_shares', 0) or 0)
    cost = float(p.get('cost_usd', 0) or 0)
    sh_o = get_onchain_size(tok)
    sh = min(sh_t, sh_o) if sh_o > 0 else sh_t
    if sh < 0.5:
        print(f"\n[SKIP-DUST] {title[:65]} on-chain={sh_o:.4f}")
        continue

    print(f"\n--- {out} {sh:.2f} sh | {title[:60]} ---")
    bid, ask = filters.get_orderbook_prices(tok)
    print(f"  bid/ask: ${bid:.4f}/${ask:.4f} (cost basis ${cost:.2f})")

    limit, exp_vwap = aggressive_limit(tok, sh)
    print(f"  Placing SELL {sh:.2f} sh @ limit ${limit:.4f} (exp VWAP ${exp_vwap:.4f})")

    res = executor.place_limit_sell(token_id=tok, price=limit, shares=sh)
    if not res or not res.get('order_id'):
        print(f"  PLACE FAILED: {res}")
        results.append({'title': title, 'status': 'place_failed'})
        continue
    oid = res['order_id']
    print(f"  order: {oid[:24]}...")

    fill = executor.wait_for_fill_with_details(oid, timeout=120)
    matched = float(fill.get('size_matched') or 0)
    print(f"  status={fill.get('status')}  matched={matched:.2f}/{fill.get('size_original'):.2f}")

    if matched < 0.5:
        print(f"  Nothing filled — order rests on book")
        results.append({'title': title, 'status': 'no_fill', 'order_id': oid})
        continue

    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else limit
    revenue = real['cost_usd'] if (real and real['size'] > 0) else matched * limit
    print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

    # Update tracker
    data = tracker.load()
    pp = data.get('positions', {}).get(k)
    if pp is not None:
        cur_sh = float(pp.get('size_shares', 0) or 0)
        cur_cost = float(pp.get('cost_usd', 0) or 0)
        cost_sold = cur_cost * (matched / cur_sh) if cur_sh > 0 else 0
        pnl = revenue - cost_sold
        new_sh = cur_sh - matched
        pp['size_shares'] = round(new_sh, 4)
        pp['cost_usd'] = round(cur_cost - cost_sold, 4)
        pp.setdefault('sells', []).append({
            'shares': round(matched, 4),
            'price': round(actual_price, 6),
            'revenue': round(revenue, 4),
            'pnl': round(pnl, 4),
            'reason': 'manual_sell_all_2026-04-27',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
        if new_sh < 0.5:
            pp['status'] = 'sold'
            pp['final_pnl'] = round(pnl, 4)
        tracker.save(data)
        print(f"  tracker updated: PnL ${pnl:+.2f}  status={pp['status']}")
    else:
        cost_sold = cost
        pnl = revenue - cost_sold

    sold_count += 1
    total_revenue += revenue
    total_cost += cost_sold
    total_pnl += pnl
    results.append({
        'title': title, 'status': 'sold',
        'shares': matched, 'vwap': actual_price,
        'revenue': revenue, 'cost_sold': cost_sold, 'pnl': pnl,
    })
    time.sleep(1)

print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"  Sold:     {sold_count} positions")
print(f"  Kept:     {skipped_count} positions")
print(f"  Total cost basis sold: ${total_cost:.2f}")
print(f"  Total revenue:         ${total_revenue:.2f}")
print(f"  Total realized PnL:    ${total_pnl:+.2f}")

with open('_sell_all_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)
print("\nResults saved to _sell_all_results.json")
