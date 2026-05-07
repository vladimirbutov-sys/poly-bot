"""Fetch 20-day hourly price history + live bid/ask for Iran open positions."""
import json
import os
import time
import statistics
import httpx
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_PATH = os.path.join(HERE, 'iran_open_snapshot.json')
OUT_PATH = os.path.join(HERE, 'iran_range_data.json')

with open(SNAP_PATH, 'r', encoding='utf-8') as f:
    markets = json.load(f)

print(f'Fetching data for {len(markets)} markets...')

def fetch_history(token_id):
    """Try multiple time windows to get ~20d hourly."""
    # prices-history supports interval=1w or explicit startTs/endTs
    end_ts = int(time.time())
    start_ts = end_ts - 20 * 86400
    url = 'https://clob.polymarket.com/prices-history'
    for params in [
        {'market': token_id, 'startTs': start_ts, 'endTs': end_ts, 'fidelity': 60},
        {'market': token_id, 'interval': '1w', 'fidelity': 60},
        {'market': token_id, 'interval': '1m', 'fidelity': 60},
    ]:
        try:
            r = httpx.get(url, params=params, timeout=15.0)
            if r.status_code == 200:
                js = r.json()
                hist = js.get('history', [])
                if hist:
                    return hist
        except Exception as e:
            print(f'  fetch err: {e}')
    return []

def fetch_book(token_id):
    url = 'https://clob.polymarket.com/book'
    try:
        r = httpx.get(url, params={'token_id': token_id}, timeout=10.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

def compute_stats(history, outcome):
    """history is list of {t, p}. p is YES price always (we convert for NO)."""
    if not history:
        return None
    prices = [float(h['p']) for h in history if 'p' in h]
    if len(prices) < 10:
        return None
    # if outcome == 'No', convert to NO-side price
    if outcome == 'No':
        prices_side = [1 - p for p in prices]
    else:
        prices_side = prices
    p_min = min(prices_side)
    p_max = max(prices_side)
    p_med = statistics.median(prices_side)
    p_mean = statistics.mean(prices_side)
    p_std = statistics.stdev(prices_side) if len(prices_side) > 1 else 0
    q1 = sorted(prices_side)[len(prices_side)//4]
    q3 = sorted(prices_side)[3*len(prices_side)//4]
    iqr = q3 - q1
    # max drawdown (peak to trough subsequent)
    peak = prices_side[0]; max_dd = 0
    for p in prices_side:
        if p > peak:
            peak = p
        dd = peak - p
        if dd > max_dd:
            max_dd = dd
    # max rally
    trough = prices_side[0]; max_rally = 0
    for p in prices_side:
        if p < trough:
            trough = p
        r = p - trough
        if r > max_rally:
            max_rally = r
    # daily moves - bin by day and count >10% swings
    days = {}
    for h, pside in zip(history, prices_side):
        t = h.get('t', 0)
        d = int(t // 86400)
        days.setdefault(d, []).append(pside)
    big_moves = 0
    for d, arr in days.items():
        if len(arr) < 2: continue
        if max(arr) - min(arr) >= 0.10:
            big_moves += 1
    vol_score = p_std / p_med if p_med > 0 else 0
    # current price (last)
    curr = prices_side[-1]
    # position on range
    pos_on_range = (curr - p_min) / (p_max - p_min) if p_max > p_min else 0.5
    return dict(
        n=len(prices_side),
        min=p_min, max=p_max, median=p_med, mean=p_mean, stdev=p_std,
        q1=q1, q3=q3, iqr=iqr, max_dd=max_dd, max_rally=max_rally,
        range_width=p_max - p_min, big_daily_moves=big_moves,
        vol_score=vol_score, current=curr, pos_on_range=pos_on_range,
        first_ts=history[0].get('t'), last_ts=history[-1].get('t'),
    )

results = []
for i, m in enumerate(markets):
    tid = m.get('token_id')
    title = m.get('title', '')[:60]
    print(f'[{i+1}/{len(markets)}] {title}')
    if not tid:
        print('  no token_id, skipping')
        m['error'] = 'no_token_id'
        results.append(m)
        continue
    hist = fetch_history(tid)
    stats = compute_stats(hist, m.get('outcome'))
    book = fetch_book(tid)
    # bid/ask
    bid = ask = None
    if book:
        bids = book.get('bids', [])
        asks = book.get('asks', [])
        if bids:
            bid = max(float(b['price']) for b in bids)
        if asks:
            ask = min(float(a['price']) for a in asks)
    m['history_n'] = len(hist) if hist else 0
    m['stats'] = stats
    m['bid'] = bid
    m['ask'] = ask
    m['history'] = hist  # keep for later analysis
    results.append(m)
    time.sleep(0.15)

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f'Saved to {OUT_PATH}')
print(f'Markets with stats: {sum(1 for r in results if r.get("stats"))}/{len(results)}')
