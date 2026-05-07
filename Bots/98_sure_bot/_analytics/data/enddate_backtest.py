"""
Backtest: optimal end_date limits for max monthly P&L.
Simulates capital rotation with different MAX_END_DATE configs.
Uses 97_scanner resolved data + simplified 98_sure_bot filters.
"""
import json, sys, os, re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load scanner data
print("Loading scanner data...")
SCANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "97_scanner", "scanner_data.json")
with open(SCANNER_PATH, "r", encoding="utf-8") as f:
    sc = json.load(f)

# Simplified content filters (same as bot)
THRESHOLD_PATTERNS = [
    r'\bo/u\b', r'\bover\s*/?\s*under\b', r'\bover\b.*\d+\.?\d*', r'\bunder\b.*\d+\.?\d*',
    r'\bmore\s+than\s+\d+', r'\bless\s+than\s+\d+', r'\bat\s+least\s+\d+', r'\bexactly\s+\d+',
    r'\bbetween\s+\d+\s*(and|-)\s*\d+', r'\b\d+\+\s*(points?|goals?|runs?|kills?|maps?)',
    r'\bspread\b', r'\bhandi?cap\b', r'\btotal\s+(points?|goals?|runs?|kills?|maps?|rounds?)',
    r'\btemperature\b.*\d+\s*[^\w]*[FC]\b',
    r'\bbe\s+(above|below|between|greater|at\s+least)',
    r'\bdip\s+(to|below)\b', r'\bpump\s+(to|above)\b',
]
TOXIC_KEYWORDS = [
    r'\bposts?\b.*\d+-\d+', r'\btweets?\b',
    r'\bviews\b.*\b(million|day\s*1|first\s*day)\b', r'\bsubscribers\b',
]
SLOW_KEYWORDS = [r'\bseason\b', r'\bmost\b', r'\btransit\b']

def _is_filtered(question):
    q = question.lower()
    for patterns in [THRESHOLD_PATTERNS, TOXIC_KEYWORDS, SLOW_KEYWORDS]:
        for p in patterns:
            if re.search(p, q):
                return True
    return False

def parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

# Prepare resolved markets
print("Preparing resolved markets...")
markets = []
for mid, m in sc.get("markets", {}).items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue

    max_p = m.get("max_price_seen", 0) or 0
    cat = (m.get("category", "") or "").lower()
    neg_risk = bool(m.get("neg_risk"))

    # Price filter
    if cat in ("politics", "geopolitics"):
        if max_p < 0.96:
            continue
    else:
        if max_p < 0.975:
            continue
    if max_p > 0.995:
        continue

    # Content filter
    question = m.get("question", "")
    if _is_filtered(question):
        continue

    # Liquidity/volume
    liq = m.get("liquidity", 0) or 0
    vol = m.get("volume", 0) or 0
    if liq < 500 or vol < 3000:
        continue

    # Resolve time
    rt = m.get("resolve_time_hours")
    if rt is None or rt <= 0:
        continue

    # Days to end
    ed = parse_dt(m.get("end_date", ""))
    fs = parse_dt(m.get("first_seen", ""))
    if not ed or not fs:
        continue
    days_to_end = (ed - fs).total_seconds() / 86400
    if days_to_end < 0:
        continue

    # Win/loss
    ho = m.get("high_outcome", "")
    w = res.get("winner", "")
    if not ho or not w:
        continue
    won = (ho == w)

    entry_price = min(max_p, 0.995)

    markets.append({
        "question": question,
        "neg_risk": neg_risk,
        "days_to_end": days_to_end,
        "resolve_hours": rt,
        "entry_price": entry_price,
        "won": won,
        "category": cat,
        "first_seen": fs,
    })

print(f"Eligible resolved markets: {len(markets)}")
markets.sort(key=lambda x: x["first_seen"])

all_dates = [m["first_seen"] for m in markets]
min_date = min(all_dates)
max_date = max(all_dates)
sim_days = (max_date - min_date).total_seconds() / 86400
print(f"Data range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')} ({sim_days:.0f} days)")

# === SIMULATION ===
BET_SIZES = {"regular": 7.50, "neg_risk": 4.00}
STARTING_BALANCE = 700

configs = []
for ed_reg in [2, 3, 4, 5, 7]:
    for ed_neg in [3, 5, 7, 10, 14]:
        for neg_cap in [100, 175, 250, 350]:
            configs.append({"ed_reg": ed_reg, "ed_neg": ed_neg, "neg_cap": neg_cap})

print(f"Testing {len(configs)} configurations...\n")

results = []

for cfg in configs:
    ed_reg = cfg["ed_reg"]
    ed_neg = cfg["ed_neg"]
    neg_cap = cfg["neg_cap"]

    balance = STARTING_BALANCE
    neg_frozen = 0.0
    open_positions = []

    total_bets = 0
    total_wins = 0
    total_losses = 0
    total_pnl = 0.0
    total_cost = 0.0
    skipped_balance = 0
    skipped_neg_cap = 0

    for m in markets:
        # Resolve matured positions
        still_open = []
        for pos in open_positions:
            if m["first_seen"] >= pos["resolve_dt"]:
                balance += pos["cost"] + pos["pnl"]
                total_pnl += pos["pnl"]
                if pos["neg_risk"]:
                    neg_frozen -= pos["cost"]
                if pos["pnl"] >= 0:
                    total_wins += 1
                else:
                    total_losses += 1
            else:
                still_open.append(pos)
        open_positions = still_open

        # End date filter
        if m["neg_risk"]:
            if m["days_to_end"] > ed_neg:
                continue
        else:
            if m["days_to_end"] > ed_reg:
                continue

        bet_size = BET_SIZES["neg_risk"] if m["neg_risk"] else BET_SIZES["regular"]

        if balance < bet_size:
            skipped_balance += 1
            continue

        if m["neg_risk"] and neg_frozen + bet_size > neg_cap:
            skipped_neg_cap += 1
            continue

        # Place bet
        shares = bet_size / m["entry_price"]
        pnl = (shares - bet_size) if m["won"] else -bet_size

        resolve_dt = m["first_seen"] + timedelta(hours=m["resolve_hours"])
        balance -= bet_size
        total_bets += 1
        total_cost += bet_size

        if m["neg_risk"]:
            neg_frozen += bet_size

        open_positions.append({
            "resolve_dt": resolve_dt,
            "cost": bet_size,
            "pnl": pnl,
            "neg_risk": m["neg_risk"],
        })

    # Resolve remaining
    for pos in open_positions:
        total_pnl += pos["pnl"]
        if pos["pnl"] >= 0:
            total_wins += 1
        else:
            total_losses += 1

    monthly_pnl = total_pnl / sim_days * 30 if sim_days > 0 else 0
    monthly_bets = total_bets / sim_days * 30 if sim_days > 0 else 0
    total_resolved = total_wins + total_losses
    wr = total_wins / total_resolved * 100 if total_resolved > 0 else 0
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    loss_rate = total_losses / total_resolved if total_resolved > 0 else 0

    results.append({
        **cfg,
        "total_bets": total_bets,
        "monthly_bets": monthly_bets,
        "wins": total_wins,
        "losses": total_losses,
        "wr": wr,
        "loss_rate": loss_rate,
        "total_pnl": total_pnl,
        "monthly_pnl": monthly_pnl,
        "roi": roi,
        "total_cost": total_cost,
        "skipped_balance": skipped_balance,
        "skipped_neg_cap": skipped_neg_cap,
    })

# Sort by monthly PnL
results.sort(key=lambda x: -x["monthly_pnl"])

print(f"{'#':>3} | {'ed_r':>4} | {'ed_n':>4} | {'NRcap':>6} | {'Bets':>5} | {'mo/B':>5} | {'W/L':>10} | {'WR%':>6} | {'PnL':>9} | {'mo/PnL':>8} | {'ROI%':>6} | {'sk$':>4} | {'skNR':>5}")
print("-" * 115)
for i, r in enumerate(results[:25]):
    print(f"{i+1:3d} | {r['ed_reg']:4d} | {r['ed_neg']:4d} | ${r['neg_cap']:4d} | {r['total_bets']:5d} | {r['monthly_bets']:5.0f} | {r['wins']:4d}/{r['losses']:<4d} | {r['wr']:5.1f}% | ${r['total_pnl']:+8.2f} | ${r['monthly_pnl']:+7.2f} | {r['roi']:5.2f}% | {r['skipped_balance']:4d} | {r['skipped_neg_cap']:5d}")

# Current config
print("\n=== CURRENT CONFIG ===")
current = [r for r in results if r["ed_reg"] == 2 and r["ed_neg"] == 3 and r["neg_cap"] == 175]
if current:
    r = current[0]
    rank = results.index(r) + 1
    print(f"Rank {rank}/{len(results)}: ed_reg={r['ed_reg']}, ed_neg={r['ed_neg']}, neg_cap=${r['neg_cap']}")
    print(f"  {r['total_bets']} bets | {r['wins']}W/{r['losses']}L | WR {r['wr']:.1f}% | PnL ${r['total_pnl']:+.2f} | mo/PnL ${r['monthly_pnl']:+.2f} | ROI {r['roi']:.2f}%")

# Sensitivity: change one param at a time
print("\n=== SENSITIVITY: ed_reg (ed_neg=3, neg_cap=175) ===")
for ed in [2, 3, 4, 5, 7]:
    r = [x for x in results if x["ed_reg"] == ed and x["ed_neg"] == 3 and x["neg_cap"] == 175]
    if r:
        r = r[0]
        print(f"  ed_reg={ed}: {r['total_bets']:4d} bets | mo/PnL ${r['monthly_pnl']:+7.2f} | WR {r['wr']:.1f}% | losses={r['losses']} | skip_bal={r['skipped_balance']} skip_neg={r['skipped_neg_cap']}")

print("\n=== SENSITIVITY: ed_neg (ed_reg=2, neg_cap=175) ===")
for ed in [3, 5, 7, 10, 14]:
    r = [x for x in results if x["ed_reg"] == 2 and x["ed_neg"] == ed and x["neg_cap"] == 175]
    if r:
        r = r[0]
        print(f"  ed_neg={ed:2d}: {r['total_bets']:4d} bets | mo/PnL ${r['monthly_pnl']:+7.2f} | WR {r['wr']:.1f}% | losses={r['losses']} | skip_bal={r['skipped_balance']} skip_neg={r['skipped_neg_cap']}")

print("\n=== SENSITIVITY: neg_cap (ed_reg=2, ed_neg=3) ===")
for cap in [100, 175, 250, 350]:
    r = [x for x in results if x["ed_reg"] == 2 and x["ed_neg"] == 3 and x["neg_cap"] == cap]
    if r:
        r = r[0]
        print(f"  neg_cap=${cap:3d}: {r['total_bets']:4d} bets | mo/PnL ${r['monthly_pnl']:+7.2f} | WR {r['wr']:.1f}% | losses={r['losses']} | skip_bal={r['skipped_balance']} skip_neg={r['skipped_neg_cap']}")

# Best with conservative loss rate
print("\n=== BEST with loss_rate < 0.5% ===")
safe = [r for r in results if r["loss_rate"] < 0.005 and r["total_bets"] > 50]
safe.sort(key=lambda x: -x["monthly_pnl"])
for r in safe[:5]:
    rank = results.index(r) + 1
    print(f"  #{rank}: ed_reg={r['ed_reg']}, ed_neg={r['ed_neg']}, neg_cap=${r['neg_cap']} | {r['total_bets']} bets | {r['wins']}W/{r['losses']}L | mo/PnL ${r['monthly_pnl']:+.2f} | ROI {r['roi']:.2f}%")

# Best with aggressive approach
print("\n=== BEST overall (any loss rate) ===")
for r in results[:5]:
    print(f"  #{results.index(r)+1}: ed_reg={r['ed_reg']}, ed_neg={r['ed_neg']}, neg_cap=${r['neg_cap']} | {r['total_bets']} bets | {r['wins']}W/{r['losses']}L | mo/PnL ${r['monthly_pnl']:+.2f} | ROI {r['roi']:.2f}%")

print("\nDone.")
