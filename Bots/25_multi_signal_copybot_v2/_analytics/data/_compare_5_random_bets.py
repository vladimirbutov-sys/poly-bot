"""Pick 5 random bets from our history, compute AS IS vs TO BE sizing."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import json, math, random
from datetime import datetime, timezone

random.seed(42)  # reproducible

POSITIONS = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\positions.json"
ACTIVITY  = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\denizz_activity_ALL.json"

# AS IS
A_OLD, B_OLD, MIN_OLD, MAX_OLD = 31.75, -177.0, 20.0, 200.0
# TO BE
A_NEW, B_NEW, MIN_NEW, MAX_NEW = 30.0, -167.0, 15.0, 250.0

PRICE_BET_MULT = [(0.00, 0.82, 1.0), (0.82, 0.99, 0.65)]
PRICE_RISK_TIERS = [
    (0.00, 0.15, 0.40),
    (0.15, 0.30, 0.70),
    (0.30, 0.50, 1.00),
    (0.50, 0.70, 0.85),
    (0.70, 0.85, 0.75),
    (0.85, 0.99, 0.60),
]

def lookup_mult(price, tiers):
    for lo, hi, m in tiers:
        if lo <= price < hi:
            return m
    return 1.0

def compute_base(invested, A, B, mn, mx):
    if invested < 1: return mn
    raw = A * math.log(invested) + B
    return max(mn, min(mx, raw))

def parse_ts(s):
    if not s: return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None

# Load positions
with open(POSITIONS, 'r', encoding='utf-8') as f:
    pos_data = json.load(f)
positions = pos_data.get('positions', {})

# Filter: signal_player=denizz, cost_usd>=10, has entry_price and timestamp
eligible = []
for k, p in positions.items():
    if p.get('signal_player') != 'denizz': continue
    if (p.get('cost_usd') or 0) < 10: continue
    if not p.get('entry_price'): continue
    if not p.get('timestamp'): continue
    if p.get('tier') == 'manual': continue
    eligible.append((k, p))

print(f"Eligible positions: {len(eligible)}")

# Pick 5 random
sample = random.sample(eligible, 5)

# Load denizz activity, index by (condition_id, asset) with list of (ts, usdc, price, side)
with open(ACTIVITY, 'r', encoding='utf-8') as f:
    activity = json.load(f)

# activity is likely a list
events = activity if isinstance(activity, list) else activity.get('data', [])
print(f"Total activity events: {len(events)}")

# Build index: (conditionId, asset) -> sorted list of BUY events
from collections import defaultdict
idx = defaultdict(list)
for e in events:
    if e.get('type') != 'TRADE': continue
    if e.get('side') != 'BUY': continue
    cid = e.get('conditionId')
    asset = e.get('asset')
    if not cid or not asset: continue
    ts = e.get('timestamp')
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        dt = parse_ts(ts)
    if not dt: continue
    usdc = float(e.get('usdcSize') or 0)
    price = float(e.get('price') or 0)
    idx[(cid, asset)].append((dt, usdc, price))

# For each sample, find denizz cumulative invested at our entry ts
for k, p in sample:
    cid = p.get('condition_id')
    tok = p.get('token_id')
    our_ts = parse_ts(p.get('timestamp'))
    our_price = p.get('avg_entry') or p.get('entry_price')
    our_cost = p.get('cost_usd')
    title = p.get('title')
    outcome = p.get('outcome')

    events_for = idx.get((cid, tok), [])
    cumulative = 0.0
    for dt, usdc, price in sorted(events_for):
        if dt <= our_ts:
            cumulative += usdc
    denizz_inv = cumulative

    # Compute AS IS
    base_old = compute_base(denizz_inv, A_OLD, B_OLD, MIN_OLD, MAX_OLD)
    pbm = lookup_mult(our_price, PRICE_BET_MULT)
    # simulate final AS IS bet without topup/horizon (unknown at this stage)
    as_is = base_old * pbm

    # Compute TO BE
    base_new = compute_base(denizz_inv, A_NEW, B_NEW, MIN_NEW, MAX_NEW)
    prm = lookup_mult(our_price, PRICE_RISK_TIERS)
    to_be = base_new * pbm * prm

    delta_pct = ((to_be - as_is) / as_is * 100) if as_is > 0 else 0

    print("=" * 90)
    print(f"Title: {title[:80]}")
    print(f"  Outcome: {outcome}  Entry price: {our_price:.3f}  Our timestamp: {our_ts.isoformat()[:16]}")
    print(f"  Denizz invested at signal: ${denizz_inv:,.0f}")
    print(f"  AS IS actual bet (recorded): ${our_cost:.2f}")
    print(f"  AS IS formula-recalc: base={base_old:.2f} × price_mult={pbm} = ${as_is:.2f}")
    print(f"  TO BE formula-recalc: base={base_new:.2f} × price_mult={pbm} × price_risk={prm} = ${to_be:.2f}")
    print(f"  Δ: {delta_pct:+.1f}%  (TO BE vs AS IS recalc)")
