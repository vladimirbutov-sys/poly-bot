"""Match Trump Iran tweets to Polymarket price movements, compute spike/revert stats,
run a naive 'fade' backtest, and print honest results."""
import json, sys, io, statistics, csv, bisect
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_DIR = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data'
tweets_j = json.load(open(fr'{DATA_DIR}\trump_iran_tweets.json', encoding='utf-8'))
tweets = tweets_j['strict_iran_in_content']  # already filtered: content mentions iran
prices_j = json.load(open(fr'{DATA_DIR}\iran_prices_60d.json', encoding='utf-8'))

print(f'tweets strict-iran: {len(tweets)}')
print(f'markets: {len(prices_j)}')


def price_at(series_ts, series_px, t):
    """Nearest price <= t (within 10 min). series sorted ascending."""
    idx = bisect.bisect_right(series_ts, t) - 1
    if idx < 0:
        return None
    if t - series_ts[idx] > 600:  # >10 min gap
        return None
    return series_px[idx]


def window_stats(series_ts, series_px, t_tweet, pre_w=15*60, post_ws=(5, 15, 30, 60, 120, 360, 1440)):
    """Return dict with pre-tweet price, post-window max/min moves, and revert times."""
    pre_price = price_at(series_ts, series_px, t_tweet - 60)  # 1 min before
    if pre_price is None:
        return None
    out = {'pre_price': pre_price}
    # Find max abs move in next 30 min
    idx_start = bisect.bisect_left(series_ts, t_tweet)
    idx_end_30 = bisect.bisect_right(series_ts, t_tweet + 30*60)
    window_prices = series_px[idx_start:idx_end_30]
    if not window_prices:
        return None
    max_up = max(window_prices) - pre_price
    max_dn = pre_price - min(window_prices)
    spike_signed = max_up if max_up >= max_dn else -max_dn
    out['spike_signed'] = spike_signed
    out['spike_abs'] = max(max_up, max_dn)
    out['spike_max_up'] = max_up
    out['spike_max_dn'] = max_dn
    # Time of peak
    if max_up >= max_dn:
        peak_idx_rel = window_prices.index(max(window_prices))
        peak_px = pre_price + max_up
    else:
        peak_idx_rel = window_prices.index(min(window_prices))
        peak_px = pre_price - max_dn
    peak_ts = series_ts[idx_start + peak_idx_rel]
    out['peak_ts'] = peak_ts
    out['peak_px'] = peak_px
    out['time_to_peak_min'] = (peak_ts - t_tweet) / 60.0
    # Revert: did price return to within ±2c of pre_price in windows?
    for w in post_ws:
        i_start = bisect.bisect_right(series_ts, peak_ts)
        i_end = bisect.bisect_right(series_ts, peak_ts + w*60)
        sub = series_px[i_start:i_end]
        if not sub:
            out[f'revert_{w}m'] = None
            continue
        # Did any price in sub come within 2c of pre_price?
        # For UP spike: pre < peak, revert means price <= pre + 0.02
        if spike_signed > 0:
            reverted = any(p <= pre_price + 0.02 for p in sub)
        else:
            reverted = any(p >= pre_price - 0.02 for p in sub)
        out[f'revert_{w}m'] = bool(reverted)
    # Post-price at 30 min and 6h
    p30 = price_at(series_ts, series_px, t_tweet + 30*60)
    p6h = price_at(series_ts, series_px, t_tweet + 6*3600)
    p24h = price_at(series_ts, series_px, t_tweet + 24*3600)
    out['p_30m'] = p30
    out['p_6h'] = p6h
    out['p_24h'] = p24h
    return out


# Build per-market reactions table
rows = []
for slug, md in prices_j.items():
    series = md['series']
    if not series:
        continue
    series_ts = [s[0] for s in series]
    series_px = [s[1] for s in series]
    for tw in tweets:
        t = tw['ts_unix']
        ws = window_stats(series_ts, series_px, t)
        if ws is None:
            continue
        row = {
            'tweet_id': tw['id'],
            'tweet_ts_utc': tw['ts_utc'],
            'content': tw['content'][:200],
            'market': slug,
            **ws,
        }
        rows.append(row)

print(f'\ntotal (market, tweet) reactions: {len(rows)}')

# Summary stats — only on meaningful spikes (>=3c)
big = [r for r in rows if r['spike_abs'] >= 0.03]
print(f'with spike >=3c: {len(big)}')
huge = [r for r in rows if r['spike_abs'] >= 0.05]
print(f'with spike >=5c: {len(huge)}')

# Per-market breakdown
from collections import defaultdict
per_mkt = defaultdict(list)
for r in rows:
    per_mkt[r['market']].append(r)
print('\n--- per-market spike counts ---')
for mkt, rs in per_mkt.items():
    spikes3 = sum(1 for r in rs if r['spike_abs'] >= 0.03)
    spikes5 = sum(1 for r in rs if r['spike_abs'] >= 0.05)
    print(f'{mkt[:55]:56} | all={len(rs)} spike>=3c={spikes3} spike>=5c={spikes5}')

# Revert WR (for spike >=3c and >=5c)
def revert_rate(rs, key):
    vals = [r[key] for r in rs if r.get(key) is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


for bucket_name, bucket in [('>=3c', big), ('>=5c', huge)]:
    print(f'\n--- Revert rates, spike {bucket_name} (n={len(bucket)}) ---')
    for w in (30, 60, 120, 360, 1440):
        rate, n = revert_rate(bucket, f'revert_{w}m')
        if rate is not None:
            print(f'  within {w} min after peak: {rate*100:.1f}% reverted (n={n})')

# Spike size distribution
if big:
    sizes = [r['spike_abs'] for r in big]
    print(f'\nspike size (>=3c): median={statistics.median(sizes)*100:.1f}c, mean={statistics.mean(sizes)*100:.1f}c, max={max(sizes)*100:.1f}c')
    ups = sum(1 for r in big if r['spike_signed'] > 0)
    dns = len(big) - ups
    print(f'  direction: up={ups} down={dns}')
    ttp = [r['time_to_peak_min'] for r in big]
    print(f'  time to peak (min): median={statistics.median(ttp):.1f} mean={statistics.mean(ttp):.1f}')

# --- Naive fade backtest ---
# Strategy: on every tweet where spike reaches >=5c in next 30m from pre_price,
# enter fade at peak-2c (simulate slippage) in opposite direction,
# exit when price comes back to pre_price ±1c OR stop-loss at spike+3c OR timeout 6h.
# Size 1 unit per trade. Track per-trade PnL in cents of underlying YES.
print('\n\n=== Naive fade backtest (spike>=5c threshold) ===')
trades = []
for r in rows:
    if r['spike_abs'] < 0.05:
        continue
    # entry: 2c slippage from peak (worse side)
    peak = r['peak_px']
    pre = r['pre_price']
    signed = r['spike_signed']
    if signed > 0:
        # YES spiked up — fade = sell YES (or buy NO). Entry: we short at peak - 0.02
        entry = peak - 0.02
        # target: exit at pre + 0.01 (good exit)
        # stop: if price goes further up by 3c from peak (entry - 0.03 if shorting? think prices)
        # P&L in c for a short: (entry - exit) * 100
    else:
        # YES spiked down — fade = buy YES. Entry: peak + 0.02
        entry = peak + 0.02
    # Scan forward up to 6h
    series = prices_j[r['market']]['series']
    series_ts = [s[0] for s in series]
    series_px = [s[1] for s in series]
    peak_ts = r['peak_ts']
    idx0 = bisect.bisect_right(series_ts, peak_ts)
    idx_end = bisect.bisect_right(series_ts, peak_ts + 6*3600)
    fwd = series_px[idx0:idx_end]
    fwd_ts = series_ts[idx0:idx_end]
    if not fwd:
        continue
    target = pre + (0.01 if signed > 0 else -0.01)
    stop_hit = None
    target_hit = None
    for p, ts in zip(fwd, fwd_ts):
        if signed > 0:
            if p <= target and target_hit is None:
                target_hit = (p, ts)
                break
            # stop: price pushes further up 3c beyond peak
            if p >= peak + 0.03 and stop_hit is None:
                stop_hit = (p, ts)
                break
        else:
            if p >= target and target_hit is None:
                target_hit = (p, ts)
                break
            if p <= peak - 0.03 and stop_hit is None:
                stop_hit = (p, ts)
                break
    if target_hit:
        exit_px, exit_ts = target_hit
        reason = 'target'
    elif stop_hit:
        exit_px, exit_ts = stop_hit
        reason = 'stop'
    else:
        exit_px = fwd[-1]
        exit_ts = fwd_ts[-1]
        reason = 'timeout'
    # PnL in cents (short if signed>0, long if signed<0)
    if signed > 0:
        pnl_c = (entry - exit_px) * 100  # short
    else:
        pnl_c = (exit_px - entry) * 100  # long
    # Subtract 2c round-trip trading cost (slippage already in entry, but add 1c on exit)
    pnl_c -= 1.0
    trades.append({
        'market': r['market'], 'tweet_ts': r['tweet_ts_utc'],
        'pre': pre, 'peak': peak, 'entry': entry, 'exit': exit_px,
        'signed': signed, 'reason': reason, 'pnl_c': pnl_c,
        'duration_min': (exit_ts - peak_ts) / 60,
    })

print(f'trades executed: {len(trades)}')
if trades:
    pnls = [t['pnl_c'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    print(f'  wins={wins} ({wins/len(trades)*100:.1f}%), losses={losses}')
    print(f'  total PnL: {sum(pnls):+.1f}c (per $1 notional per trade)')
    print(f'  median: {statistics.median(pnls):+.2f}c, mean: {statistics.mean(pnls):+.2f}c')
    print(f'  best: {max(pnls):+.1f}c, worst: {min(pnls):+.1f}c')
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    print(f'  exit reasons: {reasons}')
    durs = [t['duration_min'] for t in trades]
    print(f'  duration (min): median={statistics.median(durs):.0f}')

# Baseline: if we simply held NO exposure through the whole window (no trading around tweets)
# For each spike>=5c, just check price 6h later vs peak — this represents "no fade, just wait"
# Really baseline = doing nothing => 0 PnL. Fade must beat 0.

# Save CSV
out_csv = fr'{DATA_DIR}\tweet_market_reactions.csv'
if rows:
    keys = list(rows[0].keys())
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            r2 = {k: r.get(k) for k in keys}
            w.writerow(r2)
    print(f'\nsaved reactions csv: {out_csv} ({len(rows)} rows)')

# Save trades
out_trades = fr'{DATA_DIR}\fade_trades_sim.json'
with open(out_trades, 'w', encoding='utf-8') as f:
    json.dump(trades, f, indent=2, default=str)
print(f'saved trades: {out_trades}')

# Extra: clustering of tweets — are there tweet-bursts that make "pre_price" meaningless?
# Look at tweet time gaps
tgaps = []
tweets_sorted = sorted(tweets, key=lambda x: x['ts_unix'])
for i in range(1, len(tweets_sorted)):
    g = tweets_sorted[i]['ts_unix'] - tweets_sorted[i-1]['ts_unix']
    tgaps.append(g / 60)  # min
if tgaps:
    print(f'\n--- Tweet inter-arrival gaps (min) ---')
    print(f'  median: {statistics.median(tgaps):.1f}  mean: {statistics.mean(tgaps):.1f}')
    bursts = sum(1 for g in tgaps if g < 30)
    print(f'  <30 min gap (likely same event): {bursts}/{len(tgaps)}')
