"""
Backtest v3: analyze loss rate by parameter bucket.
Goal: find which filters can be safely relaxed to get more bets.
Uses full 97_scanner resolved data (30K+ markets).
"""
import json, sys, os, re
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import statistics

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

SCANNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "..", "97_scanner", "scanner_data.json")

print("Loading scanner data...")
with open(SCANNER_PATH, "r", encoding="utf-8") as f:
    sc = json.load(f)

# Content filters
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

# Prepare markets: only price + content filters (no liq/vol/enddate)
print("Preparing markets (price + content filter only)...")
markets = []
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

    ho = m.get("high_outcome", "")
    w = res.get("winner", "")
    if not ho or not w:
        continue

    ed = parse_dt(m.get("end_date", ""))
    fs = parse_dt(m.get("first_seen", ""))
    days_to_end = None
    if ed and fs:
        days_to_end = (ed - fs).total_seconds() / 86400
        if days_to_end < 0:
            days_to_end = None

    rt = m.get("resolve_time_hours")
    liq = m.get("liquidity", 0) or 0
    vol = m.get("volume", 0) or 0

    markets.append({
        "question": m.get("question", ""),
        "neg_risk": neg_risk,
        "days_to_end": days_to_end,
        "resolve_hours": rt if rt and rt > 0 else None,
        "entry_price": min(max_p, 0.995),
        "won": ho == w,
        "category": cat,
        "liquidity": liq,
        "volume": vol,
    })

print(f"Total after price+content filter: {len(markets)}")
wins = sum(1 for m in markets if m["won"])
losses = sum(1 for m in markets if not m["won"])
print(f"W/L: {wins}/{losses} (WR {wins/(wins+losses)*100:.2f}%)")

# =========================================================================
# ANALYSIS 1: Loss rate by VOLUME bucket
# =========================================================================
print("\n" + "=" * 80)
print("ANALYSIS 1: Loss rate by VOLUME bucket")
print("=" * 80)
vol_buckets = [
    ("$0-100", 0, 100),
    ("$100-500", 100, 500),
    ("$500-1K", 500, 1000),
    ("$1K-2K", 1000, 2000),
    ("$2K-3K", 2000, 3000),
    ("$3K-5K", 3000, 5000),
    ("$5K-10K", 5000, 10000),
    ("$10K-50K", 10000, 50000),
    ("$50K+", 50000, 1e12),
]
print(f"{'Bucket':>12} | {'Total':>6} | {'W':>5} | {'L':>3} | {'LR%':>6} | {'Losses':>40}")
print("-" * 90)
for name, lo, hi in vol_buckets:
    subset = [m for m in markets if lo <= m["volume"] < hi]
    w = sum(1 for m in subset if m["won"])
    l = sum(1 for m in subset if not m["won"])
    t = w + l
    lr = l / t * 100 if t > 0 else 0
    loss_examples = [m["question"][:38] for m in subset if not m["won"]][:2]
    loss_str = "; ".join(loss_examples) if loss_examples else ""
    print(f"{name:>12} | {t:6d} | {w:5d} | {l:3d} | {lr:5.2f}% | {loss_str[:40]}")

# =========================================================================
# ANALYSIS 2: Loss rate by LIQUIDITY bucket
# =========================================================================
print("\n" + "=" * 80)
print("ANALYSIS 2: Loss rate by LIQUIDITY bucket")
print("=" * 80)
liq_buckets = [
    ("$0-100", 0, 100),
    ("$100-200", 100, 200),
    ("$200-300", 200, 300),
    ("$300-500", 300, 500),
    ("$500-1K", 500, 1000),
    ("$1K+", 1000, 1e12),
]
print(f"{'Bucket':>12} | {'Total':>6} | {'W':>5} | {'L':>3} | {'LR%':>6}")
print("-" * 50)
for name, lo, hi in liq_buckets:
    subset = [m for m in markets if lo <= m["liquidity"] < hi]
    w = sum(1 for m in subset if m["won"])
    l = sum(1 for m in subset if not m["won"])
    t = w + l
    lr = l / t * 100 if t > 0 else 0
    print(f"{name:>12} | {t:6d} | {w:5d} | {l:3d} | {lr:5.2f}%")

# =========================================================================
# ANALYSIS 3: Loss rate by DAYS_TO_END bucket (markets with valid end_date)
# =========================================================================
print("\n" + "=" * 80)
print("ANALYSIS 3: Loss rate by DAYS_TO_END bucket")
print("=" * 80)
ed_buckets = [
    ("0-1d", 0, 1), ("1-2d", 1, 2), ("2-3d", 2, 3), ("3-5d", 3, 5),
    ("5-7d", 5, 7), ("7-14d", 7, 14), ("14d+", 14, 9999), ("no_ed", -1, -1),
]
print(f"{'Bucket':>8} | {'Total':>6} | {'W':>5} | {'L':>3} | {'LR%':>6} | {'Resolve med':>11}")
print("-" * 60)
for name, lo, hi in ed_buckets:
    if lo == -1:
        subset = [m for m in markets if m["days_to_end"] is None]
    else:
        subset = [m for m in markets if m["days_to_end"] is not None and lo <= m["days_to_end"] < hi]
    w = sum(1 for m in subset if m["won"])
    l = sum(1 for m in subset if not m["won"])
    t = w + l
    lr = l / t * 100 if t > 0 else 0
    rh = [m["resolve_hours"] for m in subset if m["resolve_hours"]]
    med = f"{statistics.median(rh):.1f}h" if rh else "n/a"
    print(f"{name:>8} | {t:6d} | {w:5d} | {l:3d} | {lr:5.2f}% | {med:>11}")

# =========================================================================
# ANALYSIS 4: Loss rate by NEG_RISK
# =========================================================================
print("\n" + "=" * 80)
print("ANALYSIS 4: Loss rate by NEG_RISK")
print("=" * 80)
for nr in [False, True]:
    subset = [m for m in markets if m["neg_risk"] == nr]
    w = sum(1 for m in subset if m["won"])
    l = sum(1 for m in subset if not m["won"])
    t = w + l
    lr = l / t * 100 if t > 0 else 0
    label = "neg_risk" if nr else "regular"
    print(f"  {label:10s}: {w}W/{l}L (LR {lr:.2f}%) n={t}")

# =========================================================================
# ANALYSIS 5: Cumulative — what happens as we relax filters
# =========================================================================
print("\n" + "=" * 80)
print("ANALYSIS 5: Cumulative filter relaxation (ordered by impact)")
print("=" * 80)

# Start with strictest, progressively relax
configs_to_test = [
    ("CURRENT: vol>=3K, liq>=500, eR<=2, eN<=3", 3000, 500, 2, 3),
    ("vol>=2K, liq>=500, eR<=2, eN<=3", 2000, 500, 2, 3),
    ("vol>=1K, liq>=500, eR<=2, eN<=3", 1000, 500, 2, 3),
    ("vol>=1K, liq>=300, eR<=2, eN<=3", 1000, 300, 2, 3),
    ("vol>=1K, liq>=200, eR<=2, eN<=3", 1000, 200, 2, 3),
    ("vol>=1K, liq>=200, eR<=3, eN<=5", 1000, 200, 3, 5),
    ("vol>=1K, liq>=200, eR<=5, eN<=7", 1000, 200, 5, 7),
    ("vol>=1K, liq>=100, eR<=5, eN<=7", 1000, 100, 5, 7),
    ("vol>=500, liq>=100, eR<=5, eN<=7", 500, 100, 5, 7),
    ("NO FILTERS (price+content only)", 0, 0, 9999, 9999),
]

print(f"{'Config':>45} | {'Total':>5} | {'W':>5} | {'L':>3} | {'LR%':>6} | {'Est mo/PnL':>10}")
print("-" * 95)

for label, min_vol, min_liq, max_ed_reg, max_ed_neg in configs_to_test:
    subset = []
    for m in markets:
        if m["volume"] < min_vol or m["liquidity"] < min_liq:
            continue
        if m["days_to_end"] is not None:
            if m["neg_risk"]:
                if m["days_to_end"] > max_ed_neg:
                    continue
            else:
                if m["days_to_end"] > max_ed_reg:
                    continue
        else:
            continue  # skip no end_date
        subset.append(m)

    w = sum(1 for m in subset if m["won"])
    l = sum(1 for m in subset if not m["won"])
    t = w + l
    lr = l / t * 100 if t > 0 else 0

    # Estimate monthly PnL: avg_bet ~$6, avg_ROI ~1.5%, minus losses
    avg_bet = 6.0
    avg_roi_per_win = 0.015 * avg_bet  # ~$0.09 per win
    loss_cost = avg_bet  # lose full bet
    monthly_markets = t / 9 * 30  # 9 days of data -> 30 days
    monthly_pnl = monthly_markets * (avg_roi_per_win * (1 - lr/100) - loss_cost * lr/100)

    print(f"{label:>45} | {t:5d} | {w:5d} | {l:3d} | {lr:5.2f}% | ${monthly_pnl:+9.2f}")

# =========================================================================
# ANALYSIS 6: All losses — what are they?
# =========================================================================
print("\n" + "=" * 80)
print("ANALYSIS 6: ALL losses in price+content filtered set")
print("=" * 80)
all_losses = [m for m in markets if not m["won"]]
print(f"Total losses: {len(all_losses)}")
print()
for i, m in enumerate(all_losses):
    print(f"{i+1:2d}. {m['question'][:70]}")
    print(f"    cat={m['category']:12s} neg={m['neg_risk']} vol=${m['volume']:.0f} liq=${m['liquidity']:.0f} dte={m['days_to_end']}")
    print()

print("Done.")
