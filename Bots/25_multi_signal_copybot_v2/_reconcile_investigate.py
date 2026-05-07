"""
Drift investigator. For each (cid, token) where tracker disagrees with
on-chain, show full reconstruction from trades API + tracker records,
and propose corrective actions.

Usage:
    py -3.12 -X utf8 _reconcile_investigate.py              # all drift markets
    py -3.12 -X utf8 _reconcile_investigate.py "Hezbollah"  # filter by title substring
"""
import sys
import io
import os
import json
import requests
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv('../98_sure_bot/.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()

filter_substr = sys.argv[1].lower() if len(sys.argv) > 1 else None


def fetch_market_activity(cid):
    """Fetch ALL our activity on a market (trades + merges + splits + redeems)."""
    acts = []
    offset = 0
    while True:
        try:
            r = requests.get(
                'https://data-api.polymarket.com/activity',
                params={'user': WALLET, 'market': cid, 'limit': 100, 'offset': offset},
                timeout=15,
            )
            if not r.ok:
                break
            batch = r.json()
            if not batch:
                break
            acts.extend(batch)
            if len(batch) < 100:
                break
            offset += 100
            if offset > 500:
                break
        except Exception:
            break
    return acts


def fetch_onchain(cid, token):
    try:
        r = requests.get('https://data-api.polymarket.com/positions',
            params={'user': WALLET, 'market': cid, 'sizeThreshold': 0}, timeout=15)
        if r.ok:
            for p in r.json():
                if p.get('asset','') == token:
                    return p
    except Exception:
        pass
    return None


def main():
    with open('positions.json', encoding='utf-8') as f:
        data = json.load(f)

    # Group open/filled tracker records by (cid, token)
    groups = defaultdict(list)
    for oid, p in data.get('positions', {}).items():
        if p.get('status') not in ('open', 'filled'):
            continue
        cid = p.get('condition_id', '') or ''
        tok = p.get('token_id', '') or ''
        if not cid or not tok:
            continue
        groups[(cid, tok)].append((oid, p))

    print(f'Scanning {len(groups)} tracker (cid,token) groups for drift...\n')

    drift_found = 0
    for (cid, tok), records in groups.items():
        tracker_sum = sum(float(p.get('size_shares', 0) or 0) for _, p in records)
        oc = fetch_onchain(cid, tok)
        oc_size = float(oc.get('size', 0) or 0) if oc else 0
        delta = tracker_sum - oc_size

        if abs(delta) < 0.5:
            continue

        title = records[0][1].get('title', '')[:60]
        if filter_substr and filter_substr not in title.lower():
            continue

        drift_found += 1
        print('=' * 100)
        print(f'DRIFT #{drift_found}: {title}')
        print('=' * 100)
        print(f'  cid:    {cid}')
        print(f'  token:  {tok[:40]}...')
        print(f'  tracker sum: {tracker_sum:.1f} sh')
        print(f'  on-chain:    {oc_size:.1f} sh')
        print(f'  diff:        {delta:+.1f} sh')
        print()

        # Show tracker records
        print(f'  TRACKER RECORDS ({len(records)}):')
        print(f'    {"OID":<18} {"status":<8} {"out":<4} {"shares":>8} {"cost":>8} {"entry":>6} {"timestamp"}')
        for oid, p in records:
            print(f'    {oid[:14]:<18} {p.get("status",""):<8} {p.get("outcome",""):<4} '
                  f'{float(p.get("size_shares",0)):>8.1f} ${float(p.get("cost_usd",0)):>6.2f} '
                  f'{float(p.get("avg_entry") or p.get("entry_price",0)):>6.3f} '
                  f'{p.get("timestamp","")[:16]}')
            if p.get('sells'):
                for s in p['sells']:
                    print(f'      SELL {s.get("shares",0):.1f}@{s.get("price",0):.3f} '
                          f'reason={s.get("reason","")[:30]} ts={s.get("timestamp","")[:16]}')
        print()

        # On-chain activity
        print(f'  ON-CHAIN ACTIVITY on this token:')
        acts = fetch_market_activity(cid)
        acts = [a for a in acts if a.get('asset','') == tok]
        acts.sort(key=lambda x: int(x.get('timestamp', 0) or 0))
        cum_shares = 0
        cum_cost = 0
        print(f'    {"date":<16} {"type":<8} {"side":<4} {"shares":>8} {"price":>6} {"usd":>8}  cumulative')
        for a in acts:
            ts_raw = int(a.get('timestamp', 0) or 0)
            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc).strftime('%m-%d %H:%M')
            type_ = a.get('type', '')
            side = (a.get('side', '') or '').upper()
            sz = float(a.get('size', 0) or 0)
            pr = float(a.get('price', 0) or 0)
            usd = sz * pr
            if side == 'BUY':
                cum_shares += sz
                cum_cost += usd
            elif side == 'SELL':
                if cum_shares > 0:
                    avg = cum_cost / cum_shares
                    cum_cost -= sz * avg
                    cum_shares -= sz
                    if cum_shares < 0.01:
                        cum_shares = 0
                        cum_cost = 0
            print(f'    {ts:<16} {type_:<8} {side:<4} {sz:>8.1f} {pr:>6.3f} ${usd:>7.2f}  cum={cum_shares:.1f} cost=${cum_cost:.2f}')
        print()
        print(f'  Reconstructed on-chain state from activity: {cum_shares:.1f} sh')
        print(f'  Actual on-chain (positions API):             {oc_size:.1f} sh')
        if abs(cum_shares - oc_size) < 0.5:
            print(f'  ✅ Activity reconciles with positions API')
        else:
            print(f'  ⚠️ Activity vs positions API mismatch: {cum_shares - oc_size:+.1f} sh')

        # Diagnosis
        print()
        print('  DIAGNOSIS:')
        total_tracker_sells = sum(
            float(s.get('shares', 0) or 0)
            for _, p in records
            for s in p.get('sells', [])
        )
        onchain_sells = sum(float(a.get('size', 0) or 0)
                            for a in acts
                            if (a.get('side', '') or '').upper() == 'SELL')
        print(f'    tracker shows total sells: {total_tracker_sells:.1f} sh')
        print(f'    on-chain total sells:      {onchain_sells:.1f} sh')

        onchain_buys = sum(float(a.get('size', 0) or 0)
                           for a in acts
                           if (a.get('side', '') or '').upper() == 'BUY')
        tracker_buys = sum(float(p.get('size_shares', 0) or 0) + sum(float(s.get('shares', 0) or 0) for s in p.get('sells', []))
                           for _, p in records)
        print(f'    tracker shows total buys:  {tracker_buys:.1f} sh')
        print(f'    on-chain total buys:       {onchain_buys:.1f} sh')

        if delta > 0:
            print('    → tracker over-counts. Either:')
            print('      (a) A sell happened but was not recorded in tracker, OR')
            print('      (b) Tracker has a "ghost" entry — some shares that never existed')
        else:
            print('    → on-chain has extra shares. Either:')
            print('      (a) Another bot (sure_bot, weather_bot) has position on same wallet, OR')
            print('      (b) Manual trade via Polymarket UI, OR')
            print('      (c) Orphan from pre-tracker era')
        print()

    print(f'\nTotal drift groups analyzed: {drift_found}')


if __name__ == '__main__':
    main()
