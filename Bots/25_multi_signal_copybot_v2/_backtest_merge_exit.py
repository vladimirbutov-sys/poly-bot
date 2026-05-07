"""
Backtest merge-triggered exit.

Rules under test:
  R1. When signal_player does MERGE on a condition_id where we have an open
      position with signal_player == that player, EXIT all shares at current
      best bid.
  R2. Merge is always treated as 100% sold (sold_pct_player = 1.0), so the
      profit-conditional rule short-circuits and always EXITs (even at loss).

What we measure:
  For each historical merge by Car/denizz, determine the player's dominant
  directional side (the side they were accumulating before merge), then:
  - Exit price = first trade price on that side after merge time
  - Hold+24h price / Hold+7d price = price snapshot later
  - PnL delta = exit_price - hold_price (positive = merge exit was correct)

Then aggregate:
  - avg PnL improvement per unit
  - % of merges where exit was correct (exit_price > hold_price)
  - worst case avoided / best case missed
"""
import sys
import io
import time
import requests
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PLAYERS = {
    'Car':    '0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b',
    'denizz': '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73',
}

HORIZON_24H = 24 * 3600
HORIZON_7D = 7 * 24 * 3600


def fetch_all(user, endpoint, max_records=2500):
    out = []
    offset = 0
    while True:
        try:
            r = requests.get(
                f'https://data-api.polymarket.com/{endpoint}',
                params={'user': user, 'limit': 500, 'offset': offset},
                timeout=20,
            )
        except Exception:
            break
        if not r.ok:
            break
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
        time.sleep(0.15)
        if len(out) >= max_records:
            break
    return out


def fetch_market_trades(cid, limit=500):
    """Get all trades on a market (any user) — used to find price snapshots."""
    try:
        r = requests.get(
            'https://data-api.polymarket.com/trades',
            params={'market': cid, 'limit': limit},
            timeout=20,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return []


def price_at_or_after(trades, target_ts, asset):
    """First trade on given asset at or after target_ts. Returns price or None."""
    for t in sorted(trades, key=lambda x: int(x.get('timestamp', 0) or 0)):
        if t.get('asset', '') != asset:
            continue
        ts = int(t.get('timestamp', 0) or 0)
        if ts >= target_ts:
            return float(t.get('price', 0) or 0), ts
    return None, None


def price_at_or_before(trades, target_ts, asset):
    """Last trade on given asset at or before target_ts."""
    best = None
    for t in trades:
        if t.get('asset', '') != asset:
            continue
        ts = int(t.get('timestamp', 0) or 0)
        if ts <= target_ts:
            if best is None or ts > best[1]:
                best = (float(t.get('price', 0) or 0), ts)
    if best:
        return best[0], best[1]
    return None, None


def determine_dominant_side(player_trades, cid, merge_ts):
    """Look at player's trades on this cid BEFORE merge_ts. Which side had
    more BUYs by size (USD)? That's the "directional" side — the one where
    we would have copied the player."""
    side_usd = defaultdict(float)
    side_asset = {}
    for t in player_trades:
        if t.get('conditionId', '') != cid:
            continue
        if int(t.get('timestamp', 0) or 0) >= merge_ts:
            continue
        side = (t.get('side', '') or '').upper()
        if side != 'BUY':
            continue
        outcome = (t.get('outcome', '') or '').strip().capitalize()
        sz = float(t.get('size', 0) or 0)
        pr = float(t.get('price', 0) or 0)
        side_usd[outcome] += sz * pr
        side_asset[outcome] = t.get('asset', '')
    if not side_usd:
        return None, None
    # Pick the outcome with LARGEST accumulated USD (the "main" bet the player
    # would have given us a signal on). The other side is the hedge.
    dominant = max(side_usd.items(), key=lambda x: x[1])[0]
    return dominant, side_asset.get(dominant)


def backtest_player(name, wallet):
    print(f'\n=== {name} ===')
    trades = fetch_all(wallet, 'trades')
    activity = fetch_all(wallet, 'activity')
    merges = [a for a in activity if (a.get('type') or '').upper() in ('MERGE', 'CONVERSION')]
    print(f'  trades: {len(trades)}, merges: {len(merges)}')

    if not merges:
        return None

    results = []
    for m in merges:
        cid = m.get('conditionId', '')
        merge_ts = int(m.get('timestamp', 0) or 0)
        if not cid or not merge_ts:
            continue

        # Determine dominant side
        dominant, dom_asset = determine_dominant_side(trades, cid, merge_ts)
        if not dominant or not dom_asset:
            continue

        # Get market-wide trades to fetch price snapshots
        mtrades = fetch_market_trades(cid, limit=500)
        if not mtrades:
            continue

        # Exit price: best bid at merge time → use last trade before merge on dominant side
        exit_price, exit_ts = price_at_or_before(mtrades, merge_ts, dom_asset)
        if exit_price is None:
            exit_price, exit_ts = price_at_or_after(mtrades, merge_ts, dom_asset)
        if exit_price is None:
            continue

        # Hold prices at +24h and +7d
        hold_24h, _ = price_at_or_after(mtrades, merge_ts + HORIZON_24H, dom_asset)
        hold_7d, _ = price_at_or_after(mtrades, merge_ts + HORIZON_7D, dom_asset)

        results.append({
            'title': m.get('title', '')[:45],
            'dominant': dominant,
            'merge_dt': datetime.fromtimestamp(merge_ts, tz=timezone.utc).strftime('%m-%d %H:%M'),
            'exit_price': exit_price,
            'hold_24h': hold_24h,
            'hold_7d': hold_7d,
        })
        time.sleep(0.1)

    if not results:
        print('  no results')
        return None

    # Summary
    print(f'\n  {"Merge":<16} {"Side":<4} {"Exit":>6} {"+24h":>6} {"+7d":>6} {"Δ24h":>7} {"Δ7d":>7}  Title')
    print('  ' + '-'*110)
    sum_delta_24h = 0
    n_24h = 0
    wins_24h = 0
    sum_delta_7d = 0
    n_7d = 0
    wins_7d = 0

    for r in results:
        d24 = (r['exit_price'] - r['hold_24h']) if r['hold_24h'] is not None else None
        d7 = (r['exit_price'] - r['hold_7d']) if r['hold_7d'] is not None else None
        d24_s = f'{d24:+.3f}' if d24 is not None else '—'
        d7_s = f'{d7:+.3f}' if d7 is not None else '—'
        h24_s = f'{r["hold_24h"]:.3f}' if r['hold_24h'] is not None else '—'
        h7_s = f'{r["hold_7d"]:.3f}' if r['hold_7d'] is not None else '—'
        print(f'  {r["merge_dt"]:<16} {r["dominant"]:<4} {r["exit_price"]:>6.3f} {h24_s:>6} {h7_s:>6} {d24_s:>7} {d7_s:>7}  {r["title"]}')

        if d24 is not None:
            sum_delta_24h += d24
            n_24h += 1
            if d24 > 0: wins_24h += 1
        if d7 is not None:
            sum_delta_7d += d7
            n_7d += 1
            if d7 > 0: wins_7d += 1

    print()
    if n_24h > 0:
        avg_24 = sum_delta_24h / n_24h
        print(f'  24h horizon: n={n_24h}, avg Δ={avg_24:+.4f}/share, wins={wins_24h}/{n_24h} ({wins_24h/n_24h*100:.0f}%)')
    if n_7d > 0:
        avg_7 = sum_delta_7d / n_7d
        print(f'  7d  horizon: n={n_7d}, avg Δ={avg_7:+.4f}/share, wins={wins_7d}/{n_7d} ({wins_7d/n_7d*100:.0f}%)')

    return {
        'n_24h': n_24h, 'wins_24h': wins_24h, 'sum_24h': sum_delta_24h,
        'n_7d': n_7d, 'wins_7d': wins_7d, 'sum_7d': sum_delta_7d,
    }


def main():
    print('Backtest: merge-triggered exit')
    print('Hypothesis: when player merges, exiting our same-side position')
    print('            gets better price than holding (positive Δ = correct)')

    totals = {'n_24h': 0, 'wins_24h': 0, 'sum_24h': 0, 'n_7d': 0, 'wins_7d': 0, 'sum_7d': 0}
    for name, w in PLAYERS.items():
        r = backtest_player(name, w)
        if r:
            for k in totals:
                totals[k] += r[k]

    print('\n\n=== TOTALS ===')
    if totals['n_24h'] > 0:
        avg = totals['sum_24h'] / totals['n_24h']
        wr = totals['wins_24h'] / totals['n_24h'] * 100
        print(f'  24h: n={totals["n_24h"]}, avg Δ={avg:+.4f}/sh, win rate={wr:.1f}%')
    if totals['n_7d'] > 0:
        avg = totals['sum_7d'] / totals['n_7d']
        wr = totals['wins_7d'] / totals['n_7d'] * 100
        print(f'  7d:  n={totals["n_7d"]}, avg Δ={avg:+.4f}/sh, win rate={wr:.1f}%')

    print('\nInterpretation:')
    print('  Δ>0  = following the merge gave us a better exit than holding')
    print('  Δ<0  = merge exit was premature — holding would have been better')
    print('  win rate > 50% + positive avg Δ = rule is worth keeping')


if __name__ == '__main__':
    main()
