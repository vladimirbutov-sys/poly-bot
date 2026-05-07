"""
Backtest v2: find optimal config for max monthly P&L.
Tests: end_date, neg_risk_cap, MIN_LIQUIDITY, MIN_VOLUME.
Simulates capital rotation chronologically.
"""
import json, sys, os, re
from datetime import datetime, timezone, timedelta

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

SCANNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "..", "97_scanner", "scanner_data.json")

print("Loading scanner data...")
with open(SCANNER_PATH, "r", encoding="utf-8") as f:
    sc = json.load(f)

# Content filters (same as bot)
THRESHOLD_PATTERNS = [
    r'\bo/u\b', r'\bover\s*/?\s*under\b', r'\bover\b.*\d+', r'\bunder\b.*\d+',
    r'\bmore\s+than\s+\d+', r'\bless\s+than\s+\d+', r'\bat\s+least\s+\d+', r'\bexactly\s+\d+',
    r'\bbetween\s+\d+\s*(and|-)\s*\d+', r'\b\d+\+\s*(points?|goals?|runs?|kills?|maps?)',
    r'\bspread\b', r'\bhandi?cap\b', r'\btotal\s+(points?|goals?|runs?|kills?|maps?|rounds?)',
    r'\btemperature\b', r'\bbe\s+(above|below|between|greater|at\s+least)',
    r'\bdip\s+(to|below)\b', r'\bpump\s+(to|above)\b',
]
TOXIC = [r'\bposts?\b.*\d+-\d+', r'\btweets?\b', r'\bviews\b.*\bmillion\b', r'\bsubscribers\b']
SLOW = [r'\bseason\b', r'\bmost\b', r'\btransit\b']

def is_filtered(q):
    q = q.lower()
    for p in THRESHOLD_PATTERNS + TOXIC + SLOW:
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

# Prepare ALL eligible resolved markets (before liq/vol/enddate filters)
print("Preparing markets...")
all_markets = []
for mid, m in sc.get("markets", {}).items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue

    max_p = m.get("max_price_seen", 0) or 0
    cat = (m.get("category", "") or "").lower()
    neg_risk = bool(m.get("neg_risk"))

    if cat in ("politics", "geopolitics"):
        if max_p < 0.96:
            continue
    else:
        if max_p < 0.975:
            continue
    if max_p > 0.995:
        continue

    if is_filtered(m.get("question", "")):
        continue

    rt = m.get("resolve_time_hours")
    if rt is None or rt <= 0:
        continue

    ed = parse_dt(m.get("end_date", ""))
    fs = parse_dt(m.get("first_seen", ""))
    if not ed or not fs:
        continue
    days_to_end = (ed - fs).total_seconds() / 86400
    if days_to_end < 0:
        continue

    ho = m.get("high_outcome", "")
    w = res.get("winner", "")
    if not ho or not w:
        continue

    liq = m.get("liquidity", 0) or 0
    vol = m.get("volume", 0) or 0

    all_markets.append({
        "question": m.get("question", ""),
        "neg_risk": neg_risk,
        "days_to_end": days_to_end,
        "resolve_hours": rt,
        "entry_price": min(max_p, 0.995),
        "won": ho == w,
        "category": cat,
        "first_seen": fs,
        "liquidity": liq,
        "volume": vol,
    })

all_markets.sort(key=lambda x: x["first_seen"])
print(f"Pre-filtered markets (price+content+resolved): {len(all_markets)}")

dates = [m["first_seen"] for m in all_markets]
sim_days = (max(dates) - min(dates)).total_seconds() / 86400
print(f"Data: {min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')} ({sim_days:.0f} days)")

# === CONFIG GRID ===
BET_REG = 7.50
BET_NEG = 4.00
START_BAL = 700

configs = []
for ed_reg in [2, 3, 5, 7]:
    for ed_neg in [3, 5, 7, 14]:
        for neg_cap in [100, 175, 250, 350]:
            for min_liq in [100, 200, 300, 500]:
                for min_vol in [1000, 2000, 3000]:
                    configs.append({
                        "ed_reg": ed_reg, "ed_neg": ed_neg,
                        "neg_cap": neg_cap, "min_liq": min_liq,
                        "min_vol": min_vol,
                    })

print(f"Testing {len(configs)} configurations...")

results = []
for ci, cfg in enumerate(configs):
    ed_reg = cfg["ed_reg"]
    ed_neg = cfg["ed_neg"]
    neg_cap = cfg["neg_cap"]
    min_liq = cfg["min_liq"]
    min_vol = cfg["min_vol"]

    balance = START_BAL
    neg_frozen = 0.0
    open_pos = []
    total_bets = 0
    total_wins = 0
    total_losses = 0
    total_pnl = 0.0
    total_cost = 0.0
    skip_bal = 0
    skip_neg = 0

    for m in all_markets:
        # Resolve matured
        still = []
        for pos in open_pos:
            if m["first_seen"] >= pos["rdt"]:
                balance += pos["cost"] + pos["pnl"]
                total_pnl += pos["pnl"]
                if pos["neg"]:
                    neg_frozen -= pos["cost"]
                if pos["pnl"] >= 0:
                    total_wins += 1
                else:
                    total_losses += 1
            else:
                still.append(pos)
        open_pos = still

        # Filters
        if m["liquidity"] < min_liq or m["volume"] < min_vol:
            continue
        if m["neg_risk"]:
            if m["days_to_end"] > ed_neg:
                continue
        else:
            if m["days_to_end"] > ed_reg:
                continue

        bet = BET_NEG if m["neg_risk"] else BET_REG
        if balance < bet:
            skip_bal += 1
            continue
        if m["neg_risk"] and neg_frozen + bet > neg_cap:
            skip_neg += 1
            continue

        shares = bet / m["entry_price"]
        pnl = (shares - bet) if m["won"] else -bet
        rdt = m["first_seen"] + timedelta(hours=m["resolve_hours"])

        balance -= bet
        total_bets += 1
        total_cost += bet
        if m["neg_risk"]:
            neg_frozen += bet
        open_pos.append({"rdt": rdt, "cost": bet, "pnl": pnl, "neg": m["neg_risk"]})

    # Resolve remaining
    for pos in open_pos:
        total_pnl += pos["pnl"]
        if pos["pnl"] >= 0:
            total_wins += 1
        else:
            total_losses += 1

    tot = total_wins + total_losses
    monthly_pnl = total_pnl / sim_days * 30 if sim_days > 0 else 0
    monthly_bets = total_bets / sim_days * 30 if sim_days > 0 else 0
    wr = total_wins / tot * 100 if tot > 0 else 0
    lr = total_losses / tot if tot > 0 else 0
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0

    results.append({
        **cfg, "bets": total_bets, "mo_bets": monthly_bets,
        "W": total_wins, "L": total_losses, "wr": wr, "lr": lr,
        "pnl": total_pnl, "mo_pnl": monthly_pnl, "roi": roi,
        "cost": total_cost, "sk_bal": skip_bal, "sk_neg": skip_neg,
    })

results.sort(key=lambda x: -x["mo_pnl"])

# Print top 30
print(f"\n{'#':>3} | {'eR':>2} | {'eN':>2} | {'NRc':>4} | {'Liq':>4} | {'Vol':>5} | {'Bets':>4} | {'mo/B':>4} | {'W/L':>8} | {'WR%':>5} | {'PnL':>8} | {'mo/PnL':>7} | {'ROI%':>5}")
print("-" * 100)
for i, r in enumerate(results[:30]):
    print(f"{i+1:3d} | {r['ed_reg']:2d} | {r['ed_neg']:2d} | {r['neg_cap']:4d} | {r['min_liq']:4d} | {r['min_vol']:5d} | {r['bets']:4d} | {r['mo_bets']:4.0f} | {r['W']:3d}/{r['L']:<3d} | {r['wr']:4.1f}% | ${r['pnl']:+7.2f} | ${r['mo_pnl']:+6.2f} | {r['roi']:4.2f}%")

# Current config
print("\n=== CURRENT CONFIG (ed_reg=2, ed_neg=3, neg_cap=175, liq=500, vol=3000) ===")
cur = [r for r in results if r["ed_reg"] == 2 and r["ed_neg"] == 3 and r["neg_cap"] == 175 and r["min_liq"] == 500 and r["min_vol"] == 3000]
if cur:
    r = cur[0]
    rank = results.index(r) + 1
    print(f"Rank {rank}/{len(results)}: {r['bets']} bets | {r['W']}W/{r['L']}L | WR {r['wr']:.1f}% | mo/PnL ${r['mo_pnl']:+.2f} | ROI {r['roi']:.2f}%")
# liq=500 not in grid, also check 300
cur2 = [r for r in results if r["ed_reg"] == 2 and r["ed_neg"] == 3 and r["neg_cap"] == 175 and r["min_liq"] == 300 and r["min_vol"] == 3000]
if cur2:
    r = cur2[0]
    rank = results.index(r) + 1
    print(f"liq=300: Rank {rank}/{len(results)}: {r['bets']} bets | {r['W']}W/{r['L']}L | WR {r['wr']:.1f}% | mo/PnL ${r['mo_pnl']:+.2f}")

# Sensitivity: liquidity
print("\n=== SENSITIVITY: min_liq (ed_reg=2, ed_neg=3, neg_cap=175, vol=3000) ===")
for liq in [100, 200, 300, 500]:
    r = [x for x in results if x["ed_reg"] == 2 and x["ed_neg"] == 3 and x["neg_cap"] == 175 and x["min_liq"] == liq and x["min_vol"] == 3000]
    if r:
        r = r[0]
        print(f"  liq={liq:3d}: {r['bets']:4d} bets | {r['W']}W/{r['L']}L | mo/PnL ${r['mo_pnl']:+.2f} | ROI {r['roi']:.2f}%")

# Sensitivity: volume
print("\n=== SENSITIVITY: min_vol (ed_reg=2, ed_neg=3, neg_cap=175, liq=200) ===")
for vol in [1000, 2000, 3000]:
    r = [x for x in results if x["ed_reg"] == 2 and x["ed_neg"] == 3 and x["neg_cap"] == 175 and x["min_liq"] == 200 and x["min_vol"] == vol]
    if r:
        r = r[0]
        print(f"  vol={vol:4d}: {r['bets']:4d} bets | {r['W']}W/{r['L']}L | mo/PnL ${r['mo_pnl']:+.2f} | ROI {r['roi']:.2f}%")

# Sensitivity: end_date (with looser liq/vol)
print("\n=== SENSITIVITY: ed_reg (ed_neg=5, neg_cap=175, liq=200, vol=1000) ===")
for ed in [2, 3, 5, 7]:
    r = [x for x in results if x["ed_reg"] == ed and x["ed_neg"] == 5 and x["neg_cap"] == 175 and x["min_liq"] == 200 and x["min_vol"] == 1000]
    if r:
        r = r[0]
        print(f"  ed_reg={ed}: {r['bets']:4d} bets | {r['W']}W/{r['L']}L | mo/PnL ${r['mo_pnl']:+.2f} | ROI {r['roi']:.2f}%")

# Sensitivity: neg_cap (with looser liq/vol)
print("\n=== SENSITIVITY: neg_cap (ed_reg=3, ed_neg=5, liq=200, vol=1000) ===")
for cap in [100, 175, 250, 350]:
    r = [x for x in results if x["ed_reg"] == 3 and x["ed_neg"] == 5 and x["neg_cap"] == cap and x["min_liq"] == 200 and x["min_vol"] == 1000]
    if r:
        r = r[0]
        print(f"  neg_cap={cap:3d}: {r['bets']:4d} bets | {r['W']}W/{r['L']}L | mo/PnL ${r['mo_pnl']:+.2f} | sk_neg={r['sk_neg']}")

# Best SAFE configs (loss rate < 1%, 50+ bets)
print("\n=== TOP 10 SAFE (loss_rate < 1%, bets > 50) ===")
safe = [r for r in results if r["lr"] < 0.01 and r["bets"] > 50]
safe.sort(key=lambda x: -x["mo_pnl"])
for i, r in enumerate(safe[:10]):
    rank = results.index(r) + 1
    print(f"  #{rank}: eR={r['ed_reg']} eN={r['ed_neg']} NR${r['neg_cap']} liq={r['min_liq']} vol={r['min_vol']} | {r['bets']} bets {r['W']}W/{r['L']}L | mo/PnL ${r['mo_pnl']:+.2f} | ROI {r['roi']:.2f}%")

# Show loss details for top configs
print("\n=== LOSS ANALYSIS for top-5 configs ===")
for i, cfg_r in enumerate(results[:5]):
    ed_reg = cfg_r["ed_reg"]
    ed_neg = cfg_r["ed_neg"]
    min_liq = cfg_r["min_liq"]
    min_vol = cfg_r["min_vol"]
    losses = []
    for m in all_markets:
        if m["liquidity"] < min_liq or m["volume"] < min_vol:
            continue
        if m["neg_risk"]:
            if m["days_to_end"] > ed_neg: continue
        else:
            if m["days_to_end"] > ed_reg: continue
        if not m["won"]:
            losses.append(m)
    print(f"\nConfig #{i+1} (eR={ed_reg} eN={ed_neg} liq={min_liq} vol={min_vol}): {len(losses)} losses")
    for l in losses[:5]:
        print(f"  {l['question'][:65]} | cat={l['category']} | neg={l['neg_risk']} | dte={l['days_to_end']:.1f}d | liq=${l['liquidity']:.0f} | vol=${l['volume']:.0f}")

print("\nDone.")
