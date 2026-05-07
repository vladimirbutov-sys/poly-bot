"""Generate all-trades report."""
import sys, io, json, requests, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
load_dotenv('../98_sure_bot/.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()

with open('positions.json', encoding='utf-8') as f:
    data = json.load(f)

# Get fresh on-chain positions
pos_now = {}
offset = 0
while True:
    r = requests.get('https://data-api.polymarket.com/positions',
                     params={'user': WALLET, 'limit': 500, 'offset': offset}, timeout=20)
    if not r.ok:
        break
    b = r.json()
    if not b:
        break
    for p in b:
        key = (p.get('conditionId', ''), p.get('asset', ''))
        pos_now[key] = p
    if len(b) < 500:
        break
    offset += 500
    time.sleep(0.2)

print(f"Loaded {len(pos_now)} on-chain positions")

# Fetch denizz trades once and build (conditionId) → first BUY data map.
# Used to show "Denizz Entry" column so we can see how late we entered.
# Keyed by conditionId (not asset) so we can compare cross-outcome (Yes vs No).
DENIZZ_WALLET = '0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73'
denizz_first_buy = {}  # conditionId → {ts, price, outcome, asset}
_off = 0
while True:
    try:
        r = requests.get('https://data-api.polymarket.com/trades',
                         params={'user': DENIZZ_WALLET, 'limit': 500, 'offset': _off},
                         timeout=20)
    except Exception as e:
        print(f'denizz trades fetch error: {e}')
        break
    if not r.ok:
        break
    batch = r.json()
    if not batch:
        break
    for t in batch:
        if (t.get('side', '') or '').upper() != 'BUY':
            continue
        cid = t.get('conditionId', '')
        if not cid:
            continue
        ts = int(t.get('timestamp', 0) or 0)
        price = float(t.get('price', 0) or 0)
        if price <= 0:
            continue
        cur = denizz_first_buy.get(cid)
        if cur is None or ts < cur['ts']:
            denizz_first_buy[cid] = {
                'ts': ts,
                'price': price,
                'outcome': t.get('outcome', ''),
                'asset': t.get('asset', ''),
            }
    if len(batch) < 500:
        break
    _off += 500
    time.sleep(0.2)
    if _off > 3000:  # safety
        break
print(f"Loaded denizz first-buy map: {len(denizz_first_buy)} markets")

rows = []
for oid, p in data['positions'].items():
    title = p.get('title', '')
    sp = p.get('signal_player', 'manual') or 'manual'
    tier = p.get('tier', '?')
    # Use avg_entry if present (reflects top-ups / partial sells), else fall back to entry_price
    entry = p.get('avg_entry') or p.get('entry_price', 0)
    cost = p.get('cost_usd', 0)
    shares = p.get('size_shares', 0)
    outcome = p.get('outcome', '?')
    timestamp = p.get('timestamp', '')
    status = p.get('status', '?')
    cid = p.get('condition_id', '')
    token = p.get('token_id', '')

    sells = p.get('sells', [])
    last_sell_ts = ''
    last_sell_price = None
    sell_reason = ''
    if sells:
        last = sorted(sells, key=lambda s: s.get('timestamp', ''))[-1]
        last_sell_ts = last.get('timestamp', '')
        last_sell_price = last.get('price', 0)
        sell_reason = last.get('reason', '')

    realized_pnl = p.get('final_pnl')
    if realized_pnl is None:
        realized_pnl = sum(s.get('pnl', 0) for s in sells) if sells else None

    cur_price = None
    cur_value = None
    unrealized = None
    if status in ('open', 'filled'):
        key = (cid, token)
        api_pos = pos_now.get(key)
        if api_pos:
            cur_price = float(api_pos.get('curPrice', 0) or 0)
            # Per-record unrealized: use THIS record's shares × (curPrice − avg_entry).
            # Do NOT use api_pos['cashPnl'] — it's the wallet-wide PnL on this token,
            # which gets mis-applied to all tracker rows when the same token has
            # multiple entries (tier upgrades, top-ups).
            record_avg = p.get('avg_entry') or p.get('entry_price') or 0
            record_shares = float(p.get('size_shares', 0) or 0)
            if cur_price > 0 and record_avg > 0 and record_shares > 0:
                cur_value = round(record_shares * cur_price, 2)
                unrealized = round(record_shares * (cur_price - record_avg), 2)
            else:
                cur_value = float(api_pos.get('currentValue', 0) or 0)
                unrealized = float(api_pos.get('cashPnl', 0) or 0)

    hold_hours = ''
    if timestamp and last_sell_ts:
        try:
            t1 = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            t2 = datetime.fromisoformat(last_sell_ts.replace('Z', '+00:00'))
            hold_hours = round((t2 - t1).total_seconds() / 3600, 1)
        except Exception:
            pass

    # Denizz first-buy lookup by conditionId. If denizz bought the OPPOSITE
    # outcome, we keep the data but flag it — prices aren't directly comparable
    # across sides (our_outcome_price ≈ 1 − opposite_outcome_price).
    d_first = denizz_first_buy.get(cid)
    denizz_entry_price = None
    denizz_entry_dt = ''
    denizz_outcome = ''
    if d_first:
        denizz_entry_price = d_first['price']
        denizz_entry_dt = datetime.fromtimestamp(d_first['ts'], tz=timezone.utc).strftime('%m-%d %H:%M')
        denizz_outcome = d_first['outcome']

    rows.append({
        'entry_dt': timestamp[:16].replace('T', ' ') if timestamp else '',
        'exit_dt': last_sell_ts[:16].replace('T', ' ') if last_sell_ts else '',
        'player': sp,
        'tier': tier,
        'title': title[:60],
        'outcome': outcome,
        'shares': round(shares, 1),
        'entry_price': entry,
        'denizz_entry_price': denizz_entry_price,
        'denizz_entry_dt': denizz_entry_dt,
        'denizz_outcome': denizz_outcome,
        'cost': round(cost, 2),
        'exit_price': last_sell_price if last_sell_price is not None else (cur_price if cur_price else None),
        'status': status,
        'realized_pnl': round(realized_pnl, 2) if realized_pnl is not None else None,
        'unrealized_pnl': round(unrealized, 2) if unrealized is not None else None,
        'cur_value': round(cur_value, 2) if cur_value is not None else None,
        'hold_h': hold_hours,
        'reason': sell_reason,
    })


def total_pnl(r):
    return (r['realized_pnl'] or 0) + (r['unrealized_pnl'] or 0)


def sort_key(r):
    """Sort by cost desc (large first) — applied within open/closed groups."""
    return -r['cost']


open_rows = sorted([r for r in rows if r['status'] in ('open', 'filled')], key=sort_key)
closed_rows = sorted([r for r in rows if r['status'] in ('won', 'lost', 'sold')], key=sort_key)
rows = open_rows + closed_rows

closed = [r for r in rows if r['status'] in ('won', 'lost', 'sold')]
open_p = [r for r in rows if r['status'] in ('open', 'filled')]

total_realized = sum(r['realized_pnl'] for r in closed if r['realized_pnl'] is not None)
total_unrealized = sum(r['unrealized_pnl'] for r in open_p if r['unrealized_pnl'] is not None)

lines = []
lines.append("# Multi Copy Bot — все сделки с момента создания")
lines.append("")
lines.append(f"**Обновлено:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
lines.append("**Источник:** positions.json + Polymarket positions API (для open позиций)")
lines.append("**Сортировка:** по Total PnL (realized + unrealized) убывание")
lines.append("")
lines.append(f"**Total positions:** {len(rows)}")
lines.append(f"- Closed: **{len(closed)}**")
lines.append(f"- Open: **{len(open_p)}**")
lines.append("")

lines.append("## PnL Summary")
lines.append("")
lines.append("| Metric | Value |")
lines.append("|--------|-------|")
lines.append(f"| Realized PnL | **${total_realized:+,.2f}** |")
lines.append(f"| Unrealized PnL | **${total_unrealized:+,.2f}** |")
lines.append(f"| **TOTAL PnL** | **${total_realized + total_unrealized:+,.2f}** |")
lines.append("")

# === Sanity check: tracker vs on-chain drift ===
from collections import defaultdict as _dd
_tracker_by_key = _dd(float)
for oid, _p in data.get('positions', {}).items():
    if _p.get('status') not in ('open', 'filled'):
        continue
    _cid = _p.get('condition_id', '') or ''
    _tok = _p.get('token_id', '') or ''
    if _cid and _tok:
        _tracker_by_key[(_cid, _tok)] += float(_p.get('size_shares', 0) or 0)

_drift_rows = []
for (_cid, _tok), _tracker_sum in _tracker_by_key.items():
    _oc = pos_now.get((_cid, _tok))
    _onchain_size = float(_oc.get('size', 0) or 0) if _oc else 0
    _delta = _tracker_sum - _onchain_size
    if abs(_delta) < 0.5:
        continue
    # Lookup title
    _title = ''
    for oid, _p in data.get('positions', {}).items():
        if _p.get('condition_id', '') == _cid and _p.get('token_id', '') == _tok:
            _title = _p.get('title', '')[:50]
            break
    _drift_rows.append((_title, _tracker_sum, _onchain_size, _delta))

if _drift_rows:
    lines.append("## ⚠️ Tracker vs on-chain drift (sanity check)")
    lines.append("")
    lines.append("| Market | Tracker sum | On-chain | Diff | Note |")
    lines.append("|--------|-------------|----------|------|------|")
    for _title, _tsum, _onsz, _delta in sorted(_drift_rows, key=lambda x: -abs(x[3])):
        _note = 'tracker over-counts (missing sell in tracker?)' if _delta > 0 else 'extra on-chain shares (other bot on wallet?)'
        lines.append(f"| {_title} | {_tsum:.1f} | {_onsz:.1f} | {_delta:+.1f} | {_note} |")
    lines.append("")


by_player = {}
for r in rows:
    sp = r['player']
    if sp not in by_player:
        by_player[sp] = {'count': 0, 'realized': 0, 'unrealized': 0, 'cost': 0}
    by_player[sp]['count'] += 1
    by_player[sp]['cost'] += r['cost']
    if r['realized_pnl'] is not None:
        by_player[sp]['realized'] += r['realized_pnl']
    if r['unrealized_pnl'] is not None:
        by_player[sp]['unrealized'] += r['unrealized_pnl']

lines.append("## PnL by Signal Player")
lines.append("")
lines.append("| Player | Trades | Cost | Realized | Unrealized | Total | ROI |")
lines.append("|--------|--------|------|----------|------------|-------|-----|")
for sp, s in sorted(by_player.items(), key=lambda x: -(x[1]['realized'] + x[1]['unrealized'])):
    total = s['realized'] + s['unrealized']
    roi = (total / s['cost'] * 100) if s['cost'] > 0 else 0
    lines.append(f"| **{sp}** | {s['count']} | ${s['cost']:,.2f} | ${s['realized']:+,.2f} | ${s['unrealized']:+,.2f} | **${total:+,.2f}** | {roi:+.2f}% |")
lines.append("")

def _denizz_comparison(r):
    """Return (denizz_entry_label, vs_denizz_label).
    Handles 3 cases:
      1. denizz on same outcome → multiplier + upside ratio
      2. denizz on opposite outcome → normalize to same side
      3. denizz has no buy on this market → "—"
      4. we entered before denizz → "we entered first"
    """
    d_price = r.get('denizz_entry_price')
    d_dt = r.get('denizz_entry_dt', '')
    d_outcome = r.get('denizz_outcome', '') or ''
    our_outcome = r.get('outcome', '') or ''
    our_entry = r.get('entry_price', 0)

    if not d_price or d_price <= 0 or our_entry <= 0:
        return "—", "—"

    # Parse timestamps to detect if WE entered first
    our_ts_str = r.get('entry_dt', '')
    try:
        our_dt = datetime.fromisoformat(our_ts_str.replace(' ', 'T') + ':00+00:00') if our_ts_str else None
    except Exception:
        our_dt = None

    # If outcomes differ, normalize denizz price to OUR side (price_our_side ≈ 1 − price_opposite)
    same_side = (d_outcome.strip().lower() == our_outcome.strip().lower())
    if same_side:
        denizz_equiv_price = d_price
        side_note = ''
    else:
        denizz_equiv_price = 1.0 - d_price
        side_note = ' [opp→norm]'

    denizz_label = f"{d_price:.3f} {d_outcome} ({d_dt}){side_note}" if d_dt else f"{d_price:.3f} {d_outcome}{side_note}"

    # Metric 1: cost multiplier — how many times more (less) we pay
    if denizz_equiv_price > 0:
        mult = our_entry / denizz_equiv_price
    else:
        mult = float('inf')

    # Metric 2: upside ratio — how much upside to $1 denizz has vs us
    denizz_upside = (1.0 - denizz_equiv_price) / denizz_equiv_price if denizz_equiv_price > 0 else 0
    our_upside = (1.0 - our_entry) / our_entry if our_entry > 0 else 0
    upside_ratio = (denizz_upside / our_upside) if our_upside > 0 else float('inf')

    # Label
    if mult >= 1.05:
        # We pay more
        if upside_ratio >= 10:
            vs_label = f"{mult:.1f}× paid, {upside_ratio:.0f}× less upside"
        else:
            vs_label = f"{mult:.1f}× paid, {upside_ratio:.1f}× less upside"
    elif mult <= 0.95:
        # We got cheaper
        inv_mult = 1 / mult if mult > 0 else 0
        inv_upside = 1 / upside_ratio if upside_ratio > 0 else 0
        vs_label = f"{inv_mult:.1f}× cheaper, {inv_upside:.1f}× more upside"
    else:
        vs_label = "≈ same entry"

    return denizz_label, vs_label


def render_table(rows_list, header):
    lines.append(f"## {header}")
    lines.append("")
    lines.append("| # | Entry date | Exit date | Player | Tier | Out | Entry | Denizz Entry | vs Denizz | Exit/Cur | ROI % | Shares | Cost | Real PnL | Unr PnL | Hold(h) | Status | Title |")
    lines.append("|---|-----------|-----------|--------|------|-----|-------|-------------|-----------|----------|-------|--------|------|----------|---------|---------|--------|-------|")
    for i, r in enumerate(rows_list, 1):
        exit_str = f"{r['exit_price']:.3f}" if r['exit_price'] is not None else "—"
        rp = f"${r['realized_pnl']:+.2f}" if r['realized_pnl'] is not None else "—"
        up = f"${r['unrealized_pnl']:+.2f}" if r['unrealized_pnl'] is not None else "—"
        hold = r['hold_h'] if r['hold_h'] != '' else "—"
        # ROI % = (exit - entry) / entry * 100
        if r['exit_price'] is not None and r['entry_price'] > 0:
            roi_pct = (r['exit_price'] - r['entry_price']) / r['entry_price'] * 100
            roi_str = f"{roi_pct:+.1f}%"
        else:
            roi_str = "—"
        denizz_str, vs_denizz_str = _denizz_comparison(r)
        lines.append(f"| {i} | {r['entry_dt']} | {r['exit_dt'] or '—'} | {r['player']} | {r['tier']} | {r['outcome']} | {r['entry_price']:.3f} | {denizz_str} | {vs_denizz_str} | {exit_str} | {roi_str} | {r['shares']} | ${r['cost']:.2f} | {rp} | {up} | {hold} | {r['status']} | {r['title']} |")
    lines.append("")

render_table(open_rows, f"Open positions ({len(open_rows)}) — sorted by Cost desc")
render_table(closed_rows, f"Closed positions ({len(closed_rows)}) — sorted by Cost desc")

lines.append("## Top 10 by Cost (largest bets)")
lines.append("")
lines.append("| # | Status | Cost | Total PnL | Player | Title |")
lines.append("|---|--------|------|-----------|--------|-------|")
for i, r in enumerate(sorted(rows, key=lambda x: -x['cost'])[:10], 1):
    tp = (r['realized_pnl'] or 0) + (r['unrealized_pnl'] or 0)
    lines.append(f"| {i} | {r['status']} | ${r['cost']:.2f} | ${tp:+.2f} | {r['player']} | {r['title']} |")

report_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
report_path = f'_analytics/{report_date}_all-trades-report.md'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print(f"\nUpdated {report_path}\n")
print(f"Total positions: {len(rows)}")
print(f"Closed: {len(closed)}, Open: {len(open_p)}")
print(f"Realized:   ${total_realized:+,.2f}")
print(f"Unrealized: ${total_unrealized:+,.2f}")
print(f"TOTAL:      ${total_realized + total_unrealized:+,.2f}")
print()
print("By player:")
for sp, s in sorted(by_player.items(), key=lambda x: -(x[1]['realized'] + x[1]['unrealized'])):
    total = s['realized'] + s['unrealized']
    roi = (total / s['cost'] * 100) if s['cost'] > 0 else 0
    print(f"  {sp:<10} N={s['count']:>3} cost=${s['cost']:>8,.2f} total=${total:>+8,.2f} ROI={roi:+.2f}%")
