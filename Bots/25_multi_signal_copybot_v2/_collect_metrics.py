"""
Metrics collector for latency/slippage analysis.

Runs once an hour. For each of our Iran trades in last 24h:
- Finds closest player trade on same market
- Computes Δ time, Δ price, penalty %
- Appends to _analytics/latency_log.jsonl

Usage:
    py -3.12 _collect_metrics.py
    # or via cron/Task Scheduler every hour
"""
import sys
import io
import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv('../98_sure_bot/.env')
OUR = os.getenv('POLYMARKET_WALLET', '').lower()

PLAYERS = {
    'Car':     '0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b',
    'aenews2': '0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1',
    'denizz':  '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73',
}

IRAN_KW = ['iran', 'israel', 'hezbollah', 'hormuz', 'yemen', 'gaza',
           'litani', 'mojtaba', 'khamenei', 'ceasefire', 'pahlavi', 'tehran']

LOG_FILE = '_analytics/latency_log.jsonl'
DEDUP_KEYS_FILE = '_analytics/latency_log_seen.json'


def is_iran(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in IRAN_KW)


def get_trades(wallet: str, limit: int = 500):
    """Fetch all trades, paginated."""
    all_trades = []
    offset = 0
    while True:
        try:
            r = requests.get(
                'https://data-api.polymarket.com/trades',
                params={'user': wallet, 'limit': limit, 'offset': offset},
                timeout=20,
            )
        except Exception as e:
            print(f"  API error: {e}")
            break
        if not r.ok:
            break
        batch = r.json()
        if not batch:
            break
        all_trades.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        time.sleep(0.2)
    return all_trades


def find_closest_player_trade(player_trades, our_trade, max_gap_sec=600):
    """Find the player trade closest in time on the same market+outcome."""
    target_title = our_trade.get('title', '')
    target_outcome = our_trade.get('outcome', '')
    target_ts = int(our_trade.get('timestamp', 0))
    target_side = our_trade.get('side', '').upper()

    best = None
    best_gap = max_gap_sec + 1

    for t in player_trades:
        if t.get('title', '') != target_title:
            continue
        if t.get('outcome', '') != target_outcome:
            continue
        if t.get('side', '').upper() != target_side:
            continue
        t_ts = int(t.get('timestamp', 0))
        gap = target_ts - t_ts  # positive = player was earlier
        if 0 < gap < best_gap:
            best_gap = gap
            best = t

    return best, best_gap if best else None


def main():
    os.makedirs('_analytics', exist_ok=True)

    # Load dedup set
    seen = set()
    if os.path.exists(DEDUP_KEYS_FILE):
        try:
            with open(DEDUP_KEYS_FILE, encoding='utf-8') as f:
                seen = set(json.load(f))
        except Exception:
            seen = set()

    print("Fetching our trades...")
    our_trades = get_trades(OUR)
    our_iran = [t for t in our_trades if is_iran(t.get('title', ''))]
    print(f"  Our Iran trades total: {len(our_iran)}")

    # Filter last 24h
    cutoff = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    our_recent = [t for t in our_iran if int(t.get('timestamp', 0)) >= cutoff]
    print(f"  Our Iran trades last 24h: {len(our_recent)}")

    # Pre-fetch player trades (one batch per player)
    print("Fetching player trades...")
    player_trades = {}
    for name, wallet in PLAYERS.items():
        trades = get_trades(wallet)
        iran_trades = [t for t in trades if is_iran(t.get('title', ''))]
        player_trades[name] = iran_trades
        print(f"  {name}: {len(iran_trades)} Iran trades")

    # Build latency records
    new_records = 0
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        for our in our_recent:
            tx_hash = our.get('transactionHash', '') or our.get('tx_hash', '')
            asset = our.get('asset', '')
            our_ts = int(our.get('timestamp', 0))

            dedup_key = f"{tx_hash}|{asset}|{our_ts}"
            if dedup_key in seen:
                continue

            # Find closest player trade for each player
            best_player = None
            best_gap = None
            best_trade = None

            for name, trades in player_trades.items():
                result = find_closest_player_trade(trades, our, max_gap_sec=1800)
                if result[0] is None:
                    continue
                p_trade, gap = result
                if best_gap is None or gap < best_gap:
                    best_player = name
                    best_gap = gap
                    best_trade = p_trade

            if best_trade is None:
                continue  # can't match

            # Compute metrics
            player_price = float(best_trade.get('price', 0))
            our_price = float(our.get('price', 0))

            price_delta = our_price - player_price
            price_pct = (price_delta / player_price * 100) if player_price > 0 else 0
            our_side = our.get('side', '').upper()

            # For BUY: worse = higher price. For SELL: worse = lower price.
            if our_side == 'BUY':
                penalty_pct = price_pct
            else:  # SELL
                penalty_pct = -price_pct

            record = {
                'our_ts': our_ts,
                'our_ts_iso': datetime.fromtimestamp(our_ts, tz=timezone.utc).isoformat(),
                'title': our.get('title', '')[:80],
                'outcome': our.get('outcome', ''),
                'side': our_side,
                'player': best_player,
                'player_ts': int(best_trade.get('timestamp', 0)),
                'gap_sec': best_gap,
                'player_price': player_price,
                'our_price': our_price,
                'price_delta': round(price_delta, 4),
                'penalty_pct': round(penalty_pct, 2),
                'our_size': float(our.get('size', 0)),
                'player_size': float(best_trade.get('size', 0)),
            }
            f.write(json.dumps(record) + '\n')
            seen.add(dedup_key)
            new_records += 1

    # Save dedup set
    with open(DEDUP_KEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(seen), f)

    print(f"\nAdded {new_records} new records to {LOG_FILE}")
    print(f"Total records ever: {len(seen)}")

    # Quick summary of last 24h
    if new_records > 0:
        print("\n=== Quick summary (all records in file) ===")
        with open(LOG_FILE, encoding='utf-8') as f:
            all_records = [json.loads(l) for l in f if l.strip()]
        by_player = {}
        for r in all_records:
            p = r['player']
            by_player.setdefault(p, {'n': 0, 'gaps': [], 'penalties': []})
            by_player[p]['n'] += 1
            by_player[p]['gaps'].append(r['gap_sec'])
            by_player[p]['penalties'].append(r['penalty_pct'])

        for p, s in by_player.items():
            avg_gap = sum(s['gaps']) / len(s['gaps'])
            avg_pen = sum(s['penalties']) / len(s['penalties'])
            print(f"  {p:<10} N={s['n']:>4} avg_gap={avg_gap:>6.1f}s avg_penalty={avg_pen:+6.2f}%")


if __name__ == '__main__':
    main()
