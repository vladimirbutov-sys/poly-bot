"""
Backtest merge-prep detection logic on denizz + Car historical trades.

Algorithm:
  1. Fetch all trades for each player (paginated)
  2. Replay chronologically, tracking cumulative position per (cid, outcome)
  3. For each BUY:
     - Snapshot position BEFORE this buy
     - Apply detect_merge_prep logic (ratio-based)
     - Mark as "would_skip" if merge-prep detected
  4. For each BUY, check "ground truth": did a MERGE happen on this cid
     within 24h AFTER the buy? → confirms it was merge-prep
  5. Compute confusion matrix:
        TP = skipped AND merge happened   (correct skip)
        FP = skipped AND NO merge         (false skip, lost signal)
        TN = took    AND NO merge         (correct take)
        FN = took    AND merge happened   (false take, took merge-prep as signal)
  6. Simulate bot behavior: if we would have SKIPped buys,
     what's the impact on our bot's entries today?

Usage: py -3.12 _backtest_merge_prep.py
"""
import sys
import io
import os
import json
import time
import requests
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PLAYERS = {
    'Car':    '0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b',
    'denizz': '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73',
}

MIN_OPPOSITE_SIZE = 500.0
MAX_RATIO = 5.0
MERGE_LOOKAHEAD_SEC = 24 * 3600  # 24h window to detect merge after buy


def fetch_all(user, endpoint, max_records=2500):
    """Paginated fetch from data-api."""
    out = []
    offset = 0
    while True:
        try:
            r = requests.get(
                f'https://data-api.polymarket.com/{endpoint}',
                params={'user': user, 'limit': 500, 'offset': offset},
                timeout=20,
            )
        except Exception as e:
            print(f'  fetch err: {e}')
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


def classify_merge_prep(opp_size, our_size):
    """Return (is_merge_prep, reason_code)."""
    if opp_size < MIN_OPPOSITE_SIZE:
        return False, 'dust'
    if our_size <= 0:
        return True, 'only_opp'
    ratio = opp_size / our_size
    if ratio <= MAX_RATIO:
        return True, f'ratio_{ratio:.1f}'
    return False, f'ratio_{ratio:.1f}_high'


def backtest_player(name, wallet):
    print(f'\n=== {name} ({wallet[:10]}...) ===')

    # Fetch trades (BUY + SELL) — needed to track position over time
    print('  fetching trades...')
    trades = fetch_all(wallet, 'trades')
    print(f'  got {len(trades)} trades')

    # Fetch activity for merges (same endpoint as monitor)
    print('  fetching activity (for merges)...')
    activity = fetch_all(wallet, 'activity')
    merges = [a for a in activity if (a.get('type') or '').upper() in ('MERGE', 'CONVERSION')]
    print(f'  got {len(merges)} merges')

    # Build merge timestamps per cid for lookahead check
    merge_ts_by_cid = defaultdict(list)
    for m in merges:
        cid = m.get('conditionId', '')
        ts = int(m.get('timestamp', 0) or 0)
        if cid and ts > 0:
            merge_ts_by_cid[cid].append(ts)

    # Sort trades chronologically
    trades_sorted = sorted(trades, key=lambda t: int(t.get('timestamp', 0) or 0))

    # Cumulative position tracker: (cid, outcome_str) → net shares
    position = defaultdict(float)

    # Evaluate each BUY
    buys_evaluated = 0
    skipped_would = 0
    true_positive = 0   # skip + merge happened
    false_positive = 0  # skip + no merge
    true_negative = 0   # take + no merge
    false_negative = 0  # take + merge happened (we missed catching)
    examples_skipped = []
    examples_bad_take = []

    for t in trades_sorted:
        cid = t.get('conditionId', '')
        outcome = (t.get('outcome', '') or '').strip().capitalize()
        side = (t.get('side', '') or '').upper()
        size = float(t.get('size', 0) or 0)
        price = float(t.get('price', 0) or 0)
        ts = int(t.get('timestamp', 0) or 0)
        title = t.get('title', '')[:50]

        if not cid or not outcome or size <= 0:
            continue

        if side == 'BUY':
            opposite = 'No' if outcome == 'Yes' else 'Yes'
            # Snapshot BEFORE applying this buy
            opp_size = position[(cid, opposite)]
            our_size_before = position[(cid, outcome)]

            is_mp, reason = classify_merge_prep(opp_size, our_size_before)
            buys_evaluated += 1

            # Ground truth: was there a merge on this cid within lookahead?
            merge_happened = any(
                ts < m_ts <= ts + MERGE_LOOKAHEAD_SEC
                for m_ts in merge_ts_by_cid.get(cid, [])
            )

            if is_mp:
                skipped_would += 1
                if merge_happened:
                    true_positive += 1
                    if len(examples_skipped) < 5:
                        examples_skipped.append((title, opposite, opp_size, outcome, our_size_before, reason, 'MERGE_OK'))
                else:
                    false_positive += 1
                    if len([e for e in examples_skipped if 'NO_MERGE' in e[-1]]) < 5:
                        examples_skipped.append((title, opposite, opp_size, outcome, our_size_before, reason, 'NO_MERGE'))
            else:
                if merge_happened:
                    false_negative += 1
                    if len(examples_bad_take) < 5:
                        examples_bad_take.append((title, opposite, opp_size, outcome, our_size_before, reason))
                else:
                    true_negative += 1

            # Apply buy to cumulative position
            position[(cid, outcome)] += size
        elif side == 'SELL':
            position[(cid, outcome)] -= size
            if position[(cid, outcome)] < 0:
                position[(cid, outcome)] = 0

    total = buys_evaluated
    if total == 0:
        print('  no buys to evaluate')
        return

    precision = true_positive / skipped_would if skipped_would > 0 else 0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0
    skip_rate = skipped_would / total

    print(f'\n  BUYs evaluated:        {total}')
    print(f'  Would SKIP (merge-prep): {skipped_would} ({skip_rate*100:.1f}%)')
    print(f'    TP (correct skip, merge happened):  {true_positive}')
    print(f'    FP (false skip, no merge):          {false_positive}  ← signal lost')
    print(f'  Would TAKE:            {total - skipped_would}')
    print(f'    TN (correct take):                  {true_negative}')
    print(f'    FN (took merge-prep as signal):     {false_negative}  ← bad signal')
    print(f'  Precision: {precision*100:.1f}% (of skipped, how many were real merges)')
    print(f'  Recall:    {recall*100:.1f}% (of merges, how many we caught)')

    print(f'\n  Sample SKIPPED buys:')
    for ex in examples_skipped[:6]:
        print(f'    {ex[6]:<9} {ex[5]:<14} opp={ex[1]}:{ex[2]:>5.0f} our={ex[3]}:{ex[4]:>5.0f} | {ex[0]}')
    if examples_bad_take:
        print(f'\n  Sample TAKEN-but-merged buys (missed):')
        for ex in examples_bad_take[:5]:
            print(f'    {ex[5]:<14} opp={ex[1]}:{ex[2]:>5.0f} our={ex[3]}:{ex[4]:>5.0f} | {ex[0]}')

    return {
        'player': name,
        'total': total,
        'skipped': skipped_would,
        'tp': true_positive,
        'fp': false_positive,
        'fn': false_negative,
        'precision': precision,
        'recall': recall,
    }


def simulate_bot_impact():
    """Check our bot's actual entries in positions.json — how many would
    have been SKIPped by the new merge-prep rule?"""
    print('\n\n=== BOT IMPACT: current open positions ===\n')
    try:
        with open('positions.json', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f'  tracker load err: {e}')
        return

    # For each open position, fetch player's current opposite-side size
    # and see what the rule would say IF the player made another buy now.
    affected = 0
    for oid, p in data.get('positions', {}).items():
        if p.get('status') not in ('open', 'filled'):
            continue
        sp = p.get('signal_player', '')
        if sp not in PLAYERS:
            continue
        cid = p.get('condition_id', '')
        our_outcome = (p.get('outcome', '') or '').strip().capitalize()
        opposite = 'No' if our_outcome == 'Yes' else 'Yes'
        if not cid:
            continue

        try:
            r = requests.get(
                'https://data-api.polymarket.com/positions',
                params={'user': PLAYERS[sp], 'market': cid, 'sizeThreshold': 0},
                timeout=10,
            )
            positions = r.json() if r.ok else []
        except Exception:
            continue

        opp_size = 0
        our_side_size = 0
        for pp in positions:
            out = (pp.get('outcome', '') or '').strip().capitalize()
            sz = float(pp.get('size', 0) or 0)
            if out == opposite:
                opp_size = sz
            elif out == our_outcome:
                our_side_size = sz

        is_mp, reason = classify_merge_prep(opp_size, our_side_size)
        if is_mp:
            affected += 1
            print(f"  WOULD-SKIP if new buy now: {sp} {opposite}={opp_size:.0f} {our_outcome}={our_side_size:.0f} ({reason}) | {p.get('title','')[:45]}")

    if affected == 0:
        print('  0 current positions affected by rule (none show merge-prep signature now)')
    else:
        print(f'\n  {affected} open positions would have merge-prep condition NOW (next buy on them would be skipped)')


def main():
    print('Backtesting merge-prep detection')
    print(f'  rule: opp >= {MIN_OPPOSITE_SIZE} sh AND opp/our_side <= {MAX_RATIO}x')
    print(f'  lookahead for merge confirmation: {MERGE_LOOKAHEAD_SEC//3600}h')

    results = []
    for name, wallet in PLAYERS.items():
        r = backtest_player(name, wallet)
        if r:
            results.append(r)

    simulate_bot_impact()

    print('\n\n=== SUMMARY ===')
    print(f'{"Player":<10} {"Total":>6} {"Skip%":>6} {"Precision":>10} {"Recall":>8}')
    for r in results:
        print(f'{r["player"]:<10} {r["total"]:>6} {r["skipped"]/r["total"]*100:>5.1f}% '
              f'{r["precision"]*100:>9.1f}% {r["recall"]*100:>7.1f}%')


if __name__ == '__main__':
    main()
