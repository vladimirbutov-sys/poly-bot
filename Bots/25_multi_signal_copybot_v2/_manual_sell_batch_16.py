"""Market sell batch of 16 positions — cross-bid for guaranteed fill."""
import sys, io, json, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

# Map: partial event_slug keywords → must match open position
TARGETS = [
    ("us-forces-seize-another-oil-tanker-by-april-30", "Yes"),
    ("iran-agrees-to-end-enrichment-of-uranium-by-june-30", "Yes"),
    ("trump-announces-end-of-military-operations-against-iran-by-may-31", "Yes"),
    ("us-iran-nuclear-deal-by-april-30", None),  # any outcome
    ("us-iran-nuclear-deal-by-june-30", None),
    ("strait-of-hormuz-traffic-returns-to-normal-by-end-of-may", "Yes"),
    ("will-donald-trump-announce-that-the-united-states-blockade-of-the-strait-of-hormuz-has-been-lifted-by-may-31", "Yes"),
    ("will-trumps-approval-rating-hit-35-in-2026", "Yes"),
    ("qatarenergy-announcesresumes-lng-production-in-qatar-by-april-30", None),
    ("will-russia-capture-all-of-huliaipole-by-april-30", "Yes"),
    ("will-russia-enter-rai-oleksandrivka-by-april-30", "Yes"),
    ("will-150-or-more-ships-transit-the-strait-of-hormuz-between-april-20-april-26", "Yes"),
    ("russia-x-ukraine-ceasefire-by-june-30-2026", "Yes"),
    ("will-russia-capture-all-of-hryshyne-by-april-30", "Yes"),
    ("internet-access-restored-in-iran-by-april-30", "Yes"),
    ("will-trump-agree-to-iranian-transit-fees-in-the-strait-of-hormuz", None),
]

def find_position(slug_key, outcome, data):
    """Find an open position matching slug_key and optional outcome."""
    for k, p in data.get('positions', {}).items():
        if p.get('status') != 'open':
            continue
        es = (p.get('event_slug', '') or '').lower()
        title = (p.get('title', '') or '').lower()
        slug_l = slug_key.lower()
        # match by event_slug first, fallback to title
        if slug_l in es or slug_l in title:
            if outcome is None or p.get('outcome') == outcome:
                return k, p
    return None, None


def market_sell(token_id, shares, limit_price):
    result = executor.place_limit_sell(token_id=token_id, price=limit_price, shares=shares)
    if not result or not result.get('order_id'):
        return None, 0, 0
    oid = result['order_id']
    fill = executor.wait_for_fill_with_details(oid, timeout=60)
    matched = float(fill.get('size_matched', 0) or 0)
    real = executor.get_actual_fill(oid)
    ap = real['vwap'] if (real and real['size'] > 0) else limit_price
    rev = real['cost_usd'] if (real and real['size'] > 0) else matched * limit_price
    return oid, matched, rev, ap


def main():
    data = tracker.load()
    print(f"Batch sell of {len(TARGETS)} markets\n" + "=" * 70)
    total_rev = 0
    total_cost = 0
    total_pnl = 0
    results = []
    for i, (slug, outcome) in enumerate(TARGETS, 1):
        k, p = find_position(slug, outcome, data)
        if not p:
            print(f"\n[{i}/{len(TARGETS)}] {slug[:50]:50s} — NOT FOUND (skip)")
            results.append((slug, 'NOT_FOUND', 0, 0, 0))
            continue
        token = p.get('token_id')
        shares = float(p.get('size_shares', 0))
        if shares < 0.5:
            print(f"\n[{i}/{len(TARGETS)}] {p.get('title','?')[:50]:50s} — empty (skip)")
            continue
        bid, ask = filters.get_orderbook_prices(token)
        # Cross bid with 2-cent buffer (3-decimal markets)
        limit_px = max(0.01, round(bid - 0.015, 2))
        print(f"\n[{i}/{len(TARGETS)}] {p.get('outcome')} – {p.get('title','?')[:45]:45s}")
        print(f"    shares={shares:.2f}  bid/ask=${bid:.4f}/${ask:.4f}  limit=${limit_px}")
        try:
            oid, matched, rev, ap = market_sell(token, shares, limit_px)
        except Exception as e:
            print(f"    SELL ERROR: {e}")
            results.append((slug, 'ERROR', 0, 0, 0))
            continue
        if not oid or matched < 0.5:
            print(f"    FAIL — no fill (bid may be empty)")
            results.append((slug, 'NO_FILL', 0, 0, 0))
            continue
        # Update tracker
        cur = float(p.get('size_shares', 0)); cost = float(p.get('cost_usd', 0))
        cost_sold = cost * (matched / cur) if cur > 0 else 0
        pnl = rev - cost_sold
        new_sh = cur - matched
        p['size_shares'] = round(new_sh, 4)
        p['cost_usd'] = round(cost - cost_sold, 4)
        p.setdefault('sells', []).append({
            'shares': round(matched, 4), 'price': round(ap, 6),
            'revenue': round(rev, 4), 'pnl': round(pnl, 4),
            'reason': 'batch_market_exit',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
        if new_sh < 0.5:
            p['status'] = 'sold'
            p['final_pnl'] = round(pnl, 4)
        print(f"    ✓ Sold {matched:.2f} @ ${ap:.4f} = ${rev:.2f}  PnL ${pnl:+.2f}")
        total_rev += rev
        total_cost += cost_sold
        total_pnl += pnl
        results.append((slug, 'SOLD', matched, ap, pnl))
        # Save tracker incrementally
        tracker.save(data)
        time.sleep(0.5)

    print("\n" + "=" * 70)
    print(f"TOTAL revenue: ${total_rev:.2f}")
    print(f"TOTAL cost sold: ${total_cost:.2f}")
    print(f"TOTAL PnL:     ${total_pnl:+.2f}")


if __name__ == '__main__':
    main()
