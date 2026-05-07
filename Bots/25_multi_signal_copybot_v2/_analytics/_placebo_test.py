"""Placebo test: compare revert rates after actual Trump Iran tweets vs random non-tweet timestamps.
If revert rates are similar, the 'fade tweet' strategy has no edge vs baseline market volatility."""
import json, sys, io, bisect, random, statistics
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
random.seed(42)

DATA = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data'
tweets_j = json.load(open(fr'{DATA}\trump_iran_tweets.json', encoding='utf-8'))
tweets = tweets_j['strict_iran_in_content']
tweet_times = set(t['ts_unix'] for t in tweets)
prices_j = json.load(open(fr'{DATA}\iran_prices_60d.json', encoding='utf-8'))


def window_stats(series_ts, series_px, t_tweet):
    idx_pre = bisect.bisect_right(series_ts, t_tweet - 60) - 1
    if idx_pre < 0:
        return None
    pre_price = series_px[idx_pre]
    idx_start = bisect.bisect_left(series_ts, t_tweet)
    idx_end_30 = bisect.bisect_right(series_ts, t_tweet + 30*60)
    window_prices = series_px[idx_start:idx_end_30]
    if not window_prices:
        return None
    max_up = max(window_prices) - pre_price
    max_dn = pre_price - min(window_prices)
    spike_abs = max(max_up, max_dn)
    spike_signed = max_up if max_up >= max_dn else -max_dn
    if max_up >= max_dn:
        peak_px = pre_price + max_up
        peak_idx_rel = window_prices.index(max(window_prices))
    else:
        peak_px = pre_price - max_dn
        peak_idx_rel = window_prices.index(min(window_prices))
    peak_ts = series_ts[idx_start + peak_idx_rel]
    out = {'pre_price': pre_price, 'spike_abs': spike_abs, 'spike_signed': spike_signed,
           'peak_px': peak_px, 'peak_ts': peak_ts}
    for w_min in (30, 60, 120, 360, 1440):
        i_start = bisect.bisect_right(series_ts, peak_ts)
        i_end = bisect.bisect_right(series_ts, peak_ts + w_min*60)
        sub = series_px[i_start:i_end]
        if not sub:
            out[f'rev_{w_min}'] = None
            continue
        if spike_signed > 0:
            out[f'rev_{w_min}'] = bool(any(p <= pre_price + 0.02 for p in sub))
        else:
            out[f'rev_{w_min}'] = bool(any(p >= pre_price - 0.02 for p in sub))
    return out


# Generate random placebo timestamps — same count as real tweets, per market
real_rows = []
placebo_rows = []

for slug, md in prices_j.items():
    series = md['series']
    if not series:
        continue
    series_ts = [s[0] for s in series]
    series_px = [s[1] for s in series]
    t0, t1 = series_ts[0] + 3600, series_ts[-1] - 30*3600
    # Real tweets
    for tw in tweets:
        s = window_stats(series_ts, series_px, tw['ts_unix'])
        if s:
            s['market'] = slug
            real_rows.append(s)
    # Placebo: random timestamps, avoiding ±60min around actual tweets
    for _ in range(len(tweets)):
        for attempt in range(20):
            cand = random.randint(t0, t1)
            if all(abs(cand - tt) > 3600 for tt in tweet_times):
                s = window_stats(series_ts, series_px, cand)
                if s:
                    s['market'] = slug
                    placebo_rows.append(s)
                break


def summarize(rows, label, thresh):
    big = [r for r in rows if r['spike_abs'] >= thresh]
    print(f'\n=== {label} (spike>={thresh*100:.0f}c) ===')
    print(f'  total windows: {len(rows)}, with-spike: {len(big)} ({len(big)/max(len(rows),1)*100:.1f}%)')
    if not big:
        return
    print(f'  mean spike size: {statistics.mean([r["spike_abs"] for r in big])*100:.1f}c')
    for w in (30, 60, 120, 360, 1440):
        vals = [r[f'rev_{w}'] for r in big if r.get(f'rev_{w}') is not None]
        if vals:
            print(f'  revert within {w}m: {sum(vals)/len(vals)*100:.1f}% (n={len(vals)})')


print(f'real rows: {len(real_rows)}, placebo rows: {len(placebo_rows)}')
for thresh in (0.03, 0.05):
    summarize(real_rows, 'REAL TWEETS', thresh)
    summarize(placebo_rows, 'PLACEBO (random times)', thresh)

# Key question: does the revert rate differ between real and placebo?
# If yes -> the tweet IS a signal
# If no -> markets revert the same way without tweets, no edge
