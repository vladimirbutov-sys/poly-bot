"""One-shot Iran-Iraq reconciliation check. Read-only."""
import os, json, sys, io, requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

load_dotenv('../98_sure_bot/.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()
DATA_API = 'https://data-api.polymarket.com'

CID = "0x6f19d9353a050b75146deab85790798008f71b699232e5e237e2f46d2cb5dc2b"
TOKEN = "66460795347859666410868463972730459751676418383303025822420990211445692242831"

# --- 1. Tracker state ---
with open('positions.json', encoding='utf-8') as f:
    data = json.load(f)

tracker_rows = []
for key, pos in data.get('positions', {}).items():
    if pos.get('condition_id') == CID:
        tracker_rows.append((key, pos))

print("=" * 78)
print("TRACKER STATE (positions.json)")
print("=" * 78)
total_shares_open = 0
total_shares_all = 0
total_cost_open = 0
total_cost_all = 0
for key, pos in tracker_rows:
    print(f"\n  Key        : {key}")
    print(f"  Status     : {pos.get('status')}")
    print(f"  Shares     : {pos.get('size_shares'):,.2f}")
    print(f"  Cost USD   : ${pos.get('cost_usd'):,.2f}")
    print(f"  Avg entry  : ${pos.get('avg_entry'):.4f}")
    print(f"  Entered    : {pos.get('timestamp')}")
    print(f"  Adopted    : {pos.get('_adopted_from', '—')}")
    print(f"  Manual addns: {len(pos.get('manual_additions', []))}")
    print(f"  Sells      : {len(pos.get('sells', []))}")
    shares = float(pos.get('size_shares') or 0)
    cost = float(pos.get('cost_usd') or 0)
    total_shares_all += shares
    total_cost_all += cost
    if pos.get('status') == 'open':
        total_shares_open += shares
        total_cost_open += cost

print(f"\n  TRACKER totals (any status) : {total_shares_all:,.2f} sh, cost ${total_cost_all:,.2f}")
print(f"  TRACKER totals (open only)  : {total_shares_open:,.2f} sh, cost ${total_cost_open:,.2f}")

# --- 2. On-chain state ---
print("\n" + "=" * 78)
print("ON-CHAIN STATE (Polymarket data-api)")
print("=" * 78)

onchain_match = None
try:
    resp = requests.get(
        f'{DATA_API}/positions',
        params={'user': WALLET, 'limit': 500, 'sizeThreshold': 0},
        timeout=15,
    )
    arr = resp.json()
    print(f"  API returned: {len(arr)} positions for wallet {WALLET[:10]}...{WALLET[-4:]}")
    for p in arr:
        if p.get('conditionId') == CID:
            onchain_match = p
            break
except Exception as e:
    print(f"  ERROR fetching on-chain: {e}")

if onchain_match:
    print(f"\n  Matched Iran-Iraq position on-chain:")
    print(f"    Title     : {onchain_match.get('title', '—')}")
    print(f"    Outcome   : {onchain_match.get('outcome', '—')}")
    print(f"    Size      : {onchain_match.get('size', 0):,.2f} shares")
    print(f"    Avg price : ${float(onchain_match.get('avgPrice', 0) or 0):.4f}")
    print(f"    Current $ : ${float(onchain_match.get('currentValue', 0) or 0):,.2f}")
    print(f"    Initial $ : ${float(onchain_match.get('initialValue', 0) or 0):,.2f}")
    print(f"    Realized  : ${float(onchain_match.get('realizedPnl', 0) or 0):,.2f}")
else:
    print("  ⚠️  No Iran-Iraq position found on-chain.")

# --- 3. Verdict ---
print("\n" + "=" * 78)
print("VERDICT")
print("=" * 78)
onchain_shares = float(onchain_match.get('size', 0) or 0) if onchain_match else 0
onchain_cost = float(onchain_match.get('initialValue', 0) or 0) if onchain_match else 0

print(f"\n  On-chain shares  : {onchain_shares:,.2f}")
print(f"  Tracker sum (all): {total_shares_all:,.2f}")
print(f"  Tracker sum (open): {total_shares_open:,.2f}")

diff_all = total_shares_all - onchain_shares
diff_open = total_shares_open - onchain_shares

if abs(onchain_shares - total_shares_all) < 0.5:
    print(f"\n  ✓ On-chain matches tracker SUM (all statuses) exactly.")
    print(f"    → Tracker has correct number of rows for this position.")
elif abs(onchain_shares - total_shares_all / 2) < 0.5:
    print(f"\n  ⚠ On-chain = HALF of tracker sum. DOUBLE-COUNTING detected.")
    print(f"    → Two tracker rows each claim the same 114.16 shares — only one real.")
    print(f"    → Overstated cost_usd by ~${total_cost_all - onchain_cost:,.2f} across tracker.")
elif abs(total_shares_open - onchain_shares) < 0.5:
    print(f"\n  ✓ On-chain matches tracker OPEN rows exactly.")
    print(f"    → Closed/lost rows in tracker are historical, no double-count concern.")
else:
    print(f"\n  ⚠ Drift of {diff_all:+.2f} (all) / {diff_open:+.2f} (open) shares.")

# --- 4. PnL impact ---
print(f"\n  COST BASIS IMPACT")
print(f"  Sum of tracker cost_usd : ${total_cost_all:,.2f}")
print(f"  On-chain initial value  : ${onchain_cost:,.2f}")
cost_overstatement = total_cost_all - onchain_cost
print(f"  Overstatement in tracker: ${cost_overstatement:,.2f}")

print("\n" + "=" * 78)
