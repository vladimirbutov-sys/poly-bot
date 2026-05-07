"""Scan positions.json for double-counting: multiple tracker rows on same (cid, token)."""
import json, os, sys, io, requests
from collections import defaultdict
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

load_dotenv('../98_sure_bot/.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()
DATA_API = 'https://data-api.polymarket.com'

with open('positions.json', encoding='utf-8') as f:
    data = json.load(f)

# Group tracker rows by (cid, token)
groups = defaultdict(list)
for key, pos in data.get('positions', {}).items():
    cid = pos.get('condition_id', '')
    token = str(pos.get('token_id', ''))
    if cid and token:
        groups[(cid, token)].append((key, pos))

# Find groups with >1 row
dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
print(f"Total (cid, token) groups: {len(groups)}")
print(f"Groups with >1 tracker row: {len(dup_groups)}")

if not dup_groups:
    print("\n✓ No duplicates. All positions tracked exactly once.")
    sys.exit(0)

# Fetch on-chain
print("\nFetching on-chain positions...")
onchain = {}
try:
    resp = requests.get(f'{DATA_API}/positions',
        params={'user': WALLET, 'limit': 500, 'sizeThreshold': 0},
        timeout=20)
    for p in resp.json():
        cid = p.get('conditionId', '')
        token = str(p.get('asset', ''))
        onchain[(cid, token)] = {
            'size': float(p.get('size', 0) or 0),
            'initialValue': float(p.get('initialValue', 0) or 0),
            'title': p.get('title', ''),
        }
    print(f"  Fetched {len(onchain)} on-chain positions.")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Analyze each duplicate group
print(f"\n{'='*78}\nDUPLICATE GROUPS — detailed analysis\n{'='*78}")
concerning = []
for (cid, token), rows in dup_groups.items():
    title = rows[0][1].get('title', '?')[:50]
    tracker_sum_all = sum(float(p.get('size_shares', 0) or 0) for _, p in rows)
    tracker_sum_open = sum(float(p.get('size_shares', 0) or 0) for _, p in rows if p.get('status') == 'open')
    tracker_cost_all = sum(float(p.get('cost_usd', 0) or 0) for _, p in rows)
    tracker_cost_open = sum(float(p.get('cost_usd', 0) or 0) for _, p in rows if p.get('status') == 'open')

    onchain_info = onchain.get((cid, token), {'size': 0, 'initialValue': 0})
    oc_size = onchain_info['size']
    oc_cost = onchain_info['initialValue']

    statuses = [p.get('status') for _, p in rows]
    n_open = statuses.count('open')

    print(f"\n  📍 {title}")
    print(f"     Rows: {len(rows)} ({', '.join(statuses)})")
    print(f"     Tracker: {tracker_sum_all:.2f} sh (all) / {tracker_sum_open:.2f} sh (open)")
    print(f"     Cost   : ${tracker_cost_all:.2f} (all) / ${tracker_cost_open:.2f} (open)")
    print(f"     On-chain: {oc_size:.2f} sh, initial ${oc_cost:.2f}")

    # Flag concerning cases
    diff_all = tracker_sum_all - oc_size
    diff_open = tracker_sum_open - oc_size

    if abs(diff_all) > 0.5 and abs(diff_open) > 0.5:
        # neither matches → drift
        if oc_size < 0.5 and tracker_sum_open < 0.5:
            print(f"     ✓ OK: all rows closed, on-chain empty — historical only")
        elif n_open >= 2 and abs(tracker_sum_open - 2*oc_size) < 0.5:
            concerning.append((cid, token, title, 'OPEN_DOUBLE_COUNT'))
            print(f"     ⚠  CONCERN: {n_open} OPEN rows sum to 2× on-chain — DOUBLE-COUNT")
        elif n_open == 0 and abs(tracker_sum_all - 2*oc_size) < 0.5 and oc_size > 0.5:
            concerning.append((cid, token, title, 'CLOSED_DOUBLE_COUNT_HISTORICAL'))
            print(f"     ⚠  CONCERN: all rows closed but sum to 2× on-chain — stats inflated")
        else:
            concerning.append((cid, token, title, 'DRIFT'))
            print(f"     ⚠  CONCERN: drift {diff_all:+.2f} (all) / {diff_open:+.2f} (open)")
    elif abs(diff_open) < 0.5:
        print(f"     ✓ OK: open rows match on-chain")
    elif abs(diff_all) < 0.5 and tracker_sum_open < 0.5:
        print(f"     ✓ OK: all-row sum matches on-chain, historical closed rows")

print(f"\n{'='*78}\nSUMMARY\n{'='*78}")
print(f"  Total duplicate groups   : {len(dup_groups)}")
print(f"  Concerning (needs review): {len(concerning)}")
for cid, token, title, kind in concerning:
    print(f"    [{kind}] {title}")

if not concerning:
    print("\n✓ All duplicate groups are benign (historical rows, on-chain matches).")
