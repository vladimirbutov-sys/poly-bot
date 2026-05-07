"""Check: what liquidity/spread do stuck low-volume markets have?"""
import sys, io, json
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find stuck markets (resolved >72h after end_date) with volume <1000
stuck = []
all_low_vol = []

for m in data['markets'].values():
    vol = m.get('volume', 0) or 0
    if vol >= 1000:
        continue

    liq = m.get('liquidity', 0) or 0
    spread = m.get('spread', None)
    snapshots = m.get('snapshots', [])

    # Get last snapshot liquidity and spread
    last_liq = None
    last_spread = None
    last_bid = None
    if snapshots:
        last = snapshots[-1]
        last_liq = last.get('liquidity', None)
        last_spread = last.get('spread', None)
        last_bid = last.get('best_bid', None)

    info = {
        'question': m.get('question', '')[:65],
        'volume': vol,
        'category': m.get('category', 'unknown'),
        'liquidity': liq,
        'last_liq': last_liq,
        'last_spread': last_spread,
        'last_bid': last_bid,
        'num_snapshots': len(snapshots),
    }

    if not m.get('resolved') or not m.get('resolution'):
        continue

    res = m['resolution']
    closed_str = res.get('closed_time', '')
    end_str = m.get('end_date', '')
    if not closed_str or not end_str:
        continue
    try:
        closed = datetime.strptime(closed_str[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        if 'T' in end_str:
            end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        else:
            end = datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        delay_hours = (closed - end).total_seconds() / 3600
        info['delay_hours'] = delay_hours
        info['delay_days'] = delay_hours / 24
    except:
        continue

    all_low_vol.append(info)
    if delay_hours > 72:
        stuck.append(info)

print(f"Low-volume markets (<$1k, resolved): {len(all_low_vol)}")
print(f"Stuck >72h among them: {len(stuck)}")
print()

# ============================================================
# What liquidity do stuck low-vol markets have?
# ============================================================
print("=" * 80)
print("STUCK MARKETS (<$1k volume, >72h delay) — LIQUIDITY & SPREAD")
print("=" * 80)

print(f"\n{'Delay':>7} | {'Vol':>8} | {'Liq':>8} | {'Spread':>7} | {'Bid':>6} | {'Cat':<15} | Question")
print("-" * 110)
for r in sorted(stuck, key=lambda x: -x['delay_hours']):
    liq_str = f"${r['last_liq']:,.0f}" if r['last_liq'] is not None else "N/A"
    spr_str = f"{r['last_spread']:.3f}" if r['last_spread'] is not None else "N/A"
    bid_str = f"{r['last_bid']:.3f}" if r['last_bid'] is not None else "N/A"
    print(f"{r['delay_days']:>6.1f}d | ${r['volume']:>6,.0f} | {liq_str:>8} | {spr_str:>7} | {bid_str:>6} | {r['category']:<15} | {r['question']}")

# ============================================================
# Overall liquidity stats for low-vol markets
# ============================================================
print("\n" + "=" * 80)
print("LIQUIDITY DISTRIBUTION FOR ALL LOW-VOL MARKETS (<$1k)")
print("=" * 80)

liqs = [r['last_liq'] for r in all_low_vol if r['last_liq'] is not None]
bids = [r['last_bid'] for r in all_low_vol if r['last_bid'] is not None]
spreads = [r['last_spread'] for r in all_low_vol if r['last_spread'] is not None]

if liqs:
    liqs.sort()
    print(f"\nLiquidity (last snapshot):")
    print(f"  Median: ${liqs[len(liqs)//2]:,.0f}")
    print(f"  Avg: ${sum(liqs)/len(liqs):,.0f}")
    print(f"  Min: ${min(liqs):,.0f}")
    print(f"  P10: ${liqs[int(len(liqs)*0.1)]:,.0f}")
    print(f"  P25: ${liqs[int(len(liqs)*0.25)]:,.0f}")

if spreads:
    spreads.sort()
    print(f"\nSpread (last snapshot):")
    print(f"  Median: {spreads[len(spreads)//2]:.3f}")
    print(f"  Avg: {sum(spreads)/len(spreads):.3f}")
    print(f"  P75: {spreads[int(len(spreads)*0.75)]:.3f}")
    print(f"  P90: {spreads[int(len(spreads)*0.9)]:.3f}")

if bids:
    bids.sort()
    print(f"\nBest bid (last snapshot):")
    print(f"  Median: {bids[len(bids)//2]:.3f}")
    print(f"  P10: {bids[int(len(bids)*0.1)]:.3f}")
    print(f"  P25: {bids[int(len(bids)*0.25)]:.3f}")

# ============================================================
# Simulate: if we sold stuck markets, what would we lose?
# ============================================================
print("\n" + "=" * 80)
print("SIMULATION: IF WE SOLD STUCK MARKETS AT best_bid")
print("=" * 80)

# We buy at ~0.98. If best_bid is 0.95, we lose 3 cents per share.
# With 5 shares, that's 15 cents loss.
buy_price = 0.98
shares = 5

print(f"\nAssumption: bought at {buy_price}, {shares} shares (${shares*buy_price:.2f} cost)")
print()

sold_ok = 0
sold_loss = 0
cant_sell = 0
total_loss = 0

for r in stuck:
    bid = r['last_bid']
    if bid is None or bid <= 0:
        cant_sell += 1
        print(f"  CANT SELL | {r['question']}")
    elif bid >= buy_price:
        sold_ok += 1
    else:
        loss = (buy_price - bid) * shares
        total_loss += loss
        sold_loss += 1
        print(f"  LOSS ${loss:.2f} (bid={bid:.3f}) | {r['question']}")

print(f"\n  Could sell at profit/even: {sold_ok}")
print(f"  Could sell at loss: {sold_loss} (total loss: ${total_loss:.2f})")
print(f"  Can't sell (no bid): {cant_sell}")

# ============================================================
# How many LOW-VOL markets would our bot have bought? (with all other filters)
# ============================================================
print("\n" + "=" * 80)
print("HOW MANY LOW-VOL MARKETS PASS OUR OTHER FILTERS?")
print("=" * 80)

# Check how many low-vol markets would still pass liquidity filter ($500)
liq_pass = sum(1 for r in all_low_vol if r['liquidity'] >= 500)
liq_fail = len(all_low_vol) - liq_pass
print(f"\n  Low-vol (<$1k) markets total: {len(all_low_vol)}")
print(f"  Pass liquidity >= $500: {liq_pass}")
print(f"  Fail liquidity < $500: {liq_fail}")

stuck_pass_liq = sum(1 for r in stuck if r['liquidity'] >= 500)
print(f"\n  Stuck markets that pass liquidity >= $500: {stuck_pass_liq} out of {len(stuck)}")
