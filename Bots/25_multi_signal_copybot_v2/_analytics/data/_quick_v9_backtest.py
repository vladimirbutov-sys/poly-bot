"""Quick backtest of user's custom variant V9."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Reuse existing backtest infrastructure
sys.path.insert(0, r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data")

# Replicate backtest minimal core
import math
from collections import defaultdict
from datetime import datetime, timezone

ACT_PATH = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\denizz_activity_ALL.json"
CLOSED_PATH = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\denizz_closed_positions_raw.json"
RES_PATH = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\denizz_resolutions.json"

def parse_ts(s):
    if s is None: return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None

def lookup_mult(price, tiers):
    for lo, hi, m in tiers:
        if lo <= price < hi:
            return m
    return 1.0

TOPUP_RATIO_TIERS = [
    (0.00, 0.03, 0.0),
    (0.03, 0.10, 0.5),
    (0.10, 0.30, 0.75),
    (0.30, 999.0, 1.0),
]

# Common variant config
BANKROLL = 4000.0
RESERVE  = 300.0
MIN_BET_USD_LIVE = 10.0

VARIANTS = {
    "V7 (prev)": {
        "A": 31.75, "B": -177.0, "MIN": 15, "MAX": 250,
        "MAX_POS": 275,
        "PR": [(0.00,0.15,0.40),(0.15,0.30,0.70),(0.30,0.50,1.00),
               (0.50,0.70,0.85),(0.70,0.85,0.75),(0.85,0.99,0.60)],
    },
    "V9 (user)": {
        "A": 31.75, "B": -177.0, "MIN": 15, "MAX": 250,
        "MAX_POS": 300,
        "PR": [(0.00,0.15,0.40),(0.15,0.30,0.70),(0.30,0.70,1.00),
               (0.70,0.85,0.90),(0.85,0.99,0.80)],
    },
}

def formula(invested, A, B, mn, mx):
    if invested < 1: return mn
    return max(mn, min(mx, A*math.log(invested)+B))

# Load activity
with open(ACT_PATH, 'r', encoding='utf-8') as f:
    events = json.load(f)
if not isinstance(events, list):
    events = events.get('data', [])

# Build buys
buys = []
for e in events:
    if e.get('type') != 'TRADE': continue
    if e.get('side') != 'BUY': continue
    cid = e.get('conditionId'); tok = e.get('asset')
    if not cid or not tok: continue
    ts = parse_ts(e.get('timestamp'))
    if not ts: continue
    usd = float(e.get('usdcSize') or 0)
    price = float(e.get('price') or 0)
    if usd < 30: continue
    buys.append({"ts": ts, "cid": cid, "tok": tok, "usd": usd, "price": price})
buys.sort(key=lambda x: x["ts"])

# Load resolutions
with open(CLOSED_PATH, 'r', encoding='utf-8') as f:
    closed = json.load(f)
with open(RES_PATH, 'r', encoding='utf-8') as f:
    resolutions = json.load(f)

# Index ROI per (cid, tok)
roi_map = {}
for p in (closed if isinstance(closed, list) else []):
    cid = p.get('conditionId'); tok = p.get('asset')
    inv = float(p.get('totalBought') or 0)
    pnl = float(p.get('realizedPnl') or 0)
    if cid and tok and inv > 0:
        roi_map[(cid, tok)] = pnl / inv

# winner/loser from resolutions
res_map = {}
for r in (resolutions if isinstance(resolutions, list) else []):
    cid = r.get('conditionId')
    winner_tok = r.get('winnerToken') or r.get('winner_token')
    if cid and winner_tok:
        res_map[cid] = winner_tok

def simulate(cfg):
    bankroll = BANKROLL
    peak = bankroll
    max_dd = 0
    pos_invested = defaultdict(float)  # per (cid,tok)
    our_positions = defaultdict(float) # per (cid,tok) — how much we put
    trades = 0
    wins = 0
    losses = 0
    resolved = 0

    for b in buys:
        cid, tok, usd, price = b["cid"], b["tok"], b["usd"], b["price"]
        key = (cid, tok)
        prev_pos = pos_invested[key]
        pos_invested[key] += usd

        # topup ratio
        if prev_pos > 0:
            ratio = usd / (prev_pos + usd)
            topup_mult = lookup_mult(ratio, TOPUP_RATIO_TIERS)
            if topup_mult == 0.0:
                continue
        else:
            topup_mult = 1.0

        bet = formula(pos_invested[key], cfg["A"], cfg["B"], cfg["MIN"], cfg["MAX"])
        bet *= topup_mult
        bet *= lookup_mult(price, cfg["PR"])

        if bet < MIN_BET_USD_LIVE:
            continue

        # max position cap
        remaining_cap = max(0, cfg["MAX_POS"] - our_positions[key])
        if remaining_cap <= 0:
            continue
        bet = min(bet, remaining_cap)
        if bet < MIN_BET_USD_LIVE:
            continue

        # bankroll check
        if bankroll - bet < RESERVE:
            continue

        bankroll -= bet
        our_positions[key] += bet
        trades += 1

    # settle positions
    for key, invested in our_positions.items():
        cid, tok = key
        if (cid, tok) in roi_map:
            roi = roi_map[(cid, tok)]
            payout = invested * (1 + roi)
            resolved += 1
            if roi > 0: wins += 1
            else: losses += 1
        elif cid in res_map:
            winner = res_map[cid]
            if str(winner) == str(tok):
                payout = invested * 1.5  # ~3x avg ROI on win
                wins += 1
            else:
                payout = 0
                losses += 1
            resolved += 1
        else:
            payout = invested * 0.95  # unresolved 95% recovery
        bankroll += payout
        peak = max(peak, bankroll)
        dd = (peak - bankroll) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "final": bankroll, "return": (bankroll - BANKROLL) / BANKROLL,
        "dd": max_dd, "trades": trades, "resolved": resolved,
        "W": wins, "L": losses,
        "WR": wins / (wins + losses) if (wins + losses) else 0,
    }

results = {}
for name, cfg in VARIANTS.items():
    results[name] = simulate(cfg)

print(f"{'Variant':<15} {'Final':<10} {'Ret':<8} {'DD':<8} {'Trades':<8} {'Res':<5} {'W':<3} {'L':<3} {'WR':<6}")
for name, r in results.items():
    print(f"{name:<15} ${r['final']:.0f}    {r['return']*100:+.1f}%   {r['dd']*100:.1f}%   {r['trades']:<8} {r['resolved']:<5} {r['W']:<3} {r['L']:<3} {r['WR']*100:.0f}%")
