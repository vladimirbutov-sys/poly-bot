"""
On-chain reconciler — SAFE version (v2, 2026-04-09).

Design principles after Hezbollah double-counting incident:
  1. Group tracker records by (cid, token) — multiple tracker rows can share
     one on-chain token (tier upgrades, top-ups, orphan entries).
  2. Compare SUM of tracker shares to on-chain, not per-record.
  3. Never auto-close a position based on guesses. Only the explicit case
     "on-chain total == 0 for this (cid, token)" is allowed to auto-resolve.
  4. Every mutation is logged to _reconcile_audit.log with full context.
  5. All drift is reported but not auto-"fixed".

Modes of action:
  - LOG_ONLY: if on-chain > 0 but differs from tracker sum, just log.
  - AUTO_CLOSE: if on-chain == 0 AND there is a recent SELL covering the
    full tracker sum AND no ambiguity, close ALL tracker records in the
    group proportionally.

Runs from _metrics_loop.py every 5 min.
"""
import sys
import io
import json
import os
import shutil
import time
import requests
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv('../98_sure_bot/.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()

POSITIONS_FILE = 'positions.json'
AUDIT_LOG = '_reconcile_audit.log'
DATA_API = 'https://data-api.polymarket.com'


def audit_log(msg):
    """Append to audit log with timestamp."""
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    try:
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(f'[{ts}] {msg}\n')
    except Exception:
        pass


def fetch_onchain_positions():
    """All current on-chain positions keyed by (conditionId, asset)."""
    out = {}
    offset = 0
    while True:
        try:
            r = requests.get(
                f'{DATA_API}/positions',
                params={'user': WALLET, 'limit': 500, 'offset': offset, 'sizeThreshold': 0},
                timeout=20,
            )
            if not r.ok:
                break
            batch = r.json()
            if not batch:
                break
            for p in batch:
                key = (p.get('conditionId', ''), p.get('asset', ''))
                out[key] = p
            if len(batch) < 500:
                break
            offset += 500
            time.sleep(0.2)
        except Exception as e:
            print(f'[reconcile] fetch error: {e}')
            break
    return out


def fetch_recent_sells():
    """All our recent SELL trades indexed by (conditionId, asset)."""
    out = {}
    offset = 0
    while True:
        try:
            r = requests.get(
                f'{DATA_API}/trades',
                params={'user': WALLET, 'limit': 500, 'offset': offset},
                timeout=20,
            )
            if not r.ok:
                break
            batch = r.json()
            if not batch:
                break
            for t in batch:
                if (t.get('side', '') or '').upper() != 'SELL':
                    continue
                key = (t.get('conditionId', ''), t.get('asset', ''))
                out.setdefault(key, []).append(t)
            if len(batch) < 500:
                break
            offset += 500
            time.sleep(0.2)
            if offset > 2000:
                break
        except Exception as e:
            print(f'[reconcile] trades error: {e}')
            break
    return out


def compute_sell_fill(trades, target_shares):
    """VWAP fill simulation — match target_shares against trades in chronological order.
    Returns (revenue, shares_accounted, latest_ts).
    """
    trades_sorted = sorted(trades, key=lambda x: -int(x.get('timestamp', 0) or 0))
    revenue = 0.0
    accounted = 0.0
    latest_ts = 0
    for t in trades_sorted:
        sz = float(t.get('size', 0) or 0)
        pr = float(t.get('price', 0) or 0)
        ts = int(t.get('timestamp', 0) or 0)
        if sz <= 0 or pr <= 0:
            continue
        if accounted + sz > target_shares * 1.005:
            take = target_shares - accounted
            if take <= 0:
                break
            revenue += take * pr
            accounted += take
            latest_ts = max(latest_ts, ts)
            break
        revenue += sz * pr
        accounted += sz
        latest_ts = max(latest_ts, ts)
        if accounted >= target_shares * 0.995:
            break
    return revenue, accounted, latest_ts


def reconcile():
    if not WALLET:
        print('[reconcile] ERROR: no wallet in env')
        return
    if not os.path.exists(POSITIONS_FILE):
        print(f'[reconcile] ERROR: {POSITIONS_FILE} not found')
        return

    with open(POSITIONS_FILE, encoding='utf-8') as f:
        data = json.load(f)

    on_chain = fetch_onchain_positions()
    sells_by_key = fetch_recent_sells()

    # === STEP 1: Group tracker open records by (cid, token) ===
    groups = defaultdict(list)
    for oid, p in data.get('positions', {}).items():
        if p.get('status') not in ('open', 'filled'):
            continue
        cid = p.get('condition_id', '') or ''
        tok = p.get('token_id', '') or ''
        if not cid or not tok:
            continue
        groups[(cid, tok)].append((oid, p))

    drift_warnings = []
    auto_closed = []
    mutations = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # === STEP 2: Process each group ===
    for (cid, tok), records in groups.items():
        tracker_sum = sum(float(p.get('size_shares', 0) or 0) for _, p in records)
        onchain_pos = on_chain.get((cid, tok))
        onchain_size = float(onchain_pos.get('size', 0) or 0) if onchain_pos else 0
        title = records[0][1].get('title', '')[:50]
        delta = tracker_sum - onchain_size

        if abs(delta) < 0.5:
            continue  # in sync

        # CASE 1: on-chain == 0 — market closed or we fully sold
        if onchain_size < 0.5:
            trades = sells_by_key.get((cid, tok), [])
            if not trades:
                drift_warnings.append(
                    f'{title} — tracker sum {tracker_sum:.1f} but on-chain 0 AND no SELL trades '
                    f'(market may have resolved, need manual redeem/close)'
                )
                continue

            revenue, accounted, latest_ts = compute_sell_fill(trades, tracker_sum)
            if accounted < tracker_sum * 0.9:
                drift_warnings.append(
                    f'{title} — on-chain 0, tracker {tracker_sum:.1f} sh, but recent SELLs '
                    f'only cover {accounted:.1f} sh. Skipping auto-close.'
                )
                continue

            # Distribute the sell proportionally across all records in the group
            ts_iso = (datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat()
                      if latest_ts else now_iso)
            avg_price = revenue / accounted if accounted > 0 else 0

            for oid, p in records:
                rec_shares = float(p.get('size_shares', 0) or 0)
                if rec_shares < 0.1:
                    continue
                pct = rec_shares / tracker_sum
                rec_revenue = revenue * pct
                rec_cost = float(p.get('cost_usd', 0) or 0)
                rec_pnl = round(rec_revenue - rec_cost, 2)

                p['status'] = 'sold'
                p['size_shares'] = 0.0
                p['final_pnl'] = rec_pnl
                if 'sells' not in p:
                    p['sells'] = []
                p['sells'].append({
                    'shares': round(rec_shares, 2),
                    'price': round(avg_price, 4),
                    'revenue': round(rec_revenue, 2),
                    'pnl': rec_pnl,
                    'reason': 'reconciled_from_onchain_group',
                    'timestamp': ts_iso,
                })
                mutations.append(
                    f'CLOSE oid={oid[:14]} shares={rec_shares:.1f} revenue=${rec_revenue:.2f} pnl=${rec_pnl:+.2f} title={title}'
                )
            auto_closed.append(
                f'{title} — closed {len(records)} records, total {tracker_sum:.1f} sh, revenue ${revenue:.2f}'
            )
            continue

        # CASE 2: on-chain > 0 — DRIFT but NOT auto-close
        # This is where the old reconciler broke Hezbollah. We now only log.
        if delta > 0.5:
            drift_warnings.append(
                f'{title} — tracker sum {tracker_sum:.1f} > on-chain {onchain_size:.1f} '
                f'(diff +{delta:.1f}). Possible missing sell in tracker OR over-counting. LOG ONLY.'
            )
        else:
            drift_warnings.append(
                f'{title} — tracker sum {tracker_sum:.1f} < on-chain {onchain_size:.1f} '
                f'(diff {delta:.1f}). Extra on-chain shares — likely from another bot on same wallet. LOG ONLY.'
            )

    # === STEP 3: Persist changes (only if auto_closed non-empty) ===
    if mutations:
        backup_name = f'{POSITIONS_FILE}.backup_reconcile_{int(time.time())}'
        shutil.copy(POSITIONS_FILE, backup_name)
        tmp = POSITIONS_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, POSITIONS_FILE)

        for m in mutations:
            audit_log(m)
        audit_log(f'SUMMARY reconciled={len(auto_closed)} warnings={len(drift_warnings)} backup={backup_name}')

    # Also log warnings to audit (even without mutations)
    if drift_warnings:
        for w in drift_warnings:
            audit_log(f'DRIFT {w}')

    # === STEP 4: Report ===
    now_str = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
    print(f'[reconcile v2] {now_str} — auto-closed groups: {len(auto_closed)}, drift warnings: {len(drift_warnings)}')
    for ac in auto_closed:
        print(f'  CLOSE: {ac}')
    for w in drift_warnings[:10]:
        print(f'  WARN:  {w}')
    if len(drift_warnings) > 10:
        print(f'  ... and {len(drift_warnings) - 10} more drift warnings (see {AUDIT_LOG})')


if __name__ == '__main__':
    reconcile()
