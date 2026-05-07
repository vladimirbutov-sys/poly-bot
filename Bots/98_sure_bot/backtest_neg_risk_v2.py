"""Backtest v2: Should we allow neg_risk markets now that redemption works?

Approach: look at markets blocked ONLY by neg_risk filter.
Uses snapshots from scanner to find markets that were in tradeable price range.
"""
import json
import re
from datetime import datetime, timezone

print("Loading scanner data...", flush=True)
with open("C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json") as f:
    scanner = json.load(f)["markets"]
print(f"Loaded {len(scanner)} markets")

# Config
PRICE_THRESHOLD_DEFAULT = 0.975
PRICE_THRESHOLD_POLITICS = 0.96
MAX_PRICE = 0.995
MIN_LIQUIDITY = 500
MIN_VOLUME = 3000
POLITICS_CATEGORIES = {"politics", "geopolitics"}
ALL_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                         "american_football", "tennis", "fighting", "cricket", "soccer"}
MIN_VOLUME_FINANCIAL = 50000

# Patterns
COIN_FLIP_PATTERNS = [
    r'\bodd\s+or\s+even\b', r'\bodd/even\b', r'\bfirst\s+blood\b',
    r'\bfirst\s+kill\b', r'\bfirst\s+baron\b', r'\bfirst\s+dragon\b',
    r'\bfirst\s+tower\b', r'\bfirst\s+rift\s+herald\b', r'\bcoin\s+flip\b',
    r'\brampage\b', r'\bfirst\s+roshan\b', r'\bfirst\s+map\b', r'\bup\s+or\s+down\b',
]
THRESHOLD_PATTERNS = [
    r'\bclose\s+above\b', r'\bclose\s+below\b', r'\bbe\s+above\b', r'\bbe\s+below\b',
    r'\bbe\s+between\b', r'\bbe\s+greater\s+than\b', r'\bbe\s+less\s+than\b',
    r'\bprice\s+of\b', r'\breach\b.*\$[\d,]+', r'\bhit\b.*\$[\d,]+',
    r'\bfall\s+(to|below)\b.*\$[\d,]+', r'\bdrop\s+(to|below)\b.*\$[\d,]+',
    r'\brise\s+(to|above)\b.*\$[\d,]+',
]
SLOW_KEYWORDS = [r'\btop\b', r'\bseason\b', r'\bmost\b', r'\btransit\b', r'\bstrait\b',
                 r'\bships?\b', r'\bweekly\b', r'\bmonthly\b']
FINANCIAL_ASSETS = [
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b', r'\bbtc\b', r'\beth\b',
    r'\bsol\b', r'\bdogecoin\b', r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bgold\s*price\b',
    r'\bcrude\s*oil\b', r'\btsla\b', r'\bnvda\b', r'\btesla\b', r'\bnvidia\b',
    r'\baapl\b', r'\bamzn\b', r'\bgoogl\b', r'\bmeta\b', r'\bmsft\b',
    r'\bmicrostrategy\b', r'\btreasury\s*yield\b', r'\bfed\s*rate\b',
]
SPORTS_BAD_PATTERNS = [
    r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
    r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?|goals?)\b', r'\bhandi?cap\b',
]
WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b', r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
]


def matches_any(text, patterns):
    for p in patterns:
        if re.search(p, text):
            return True
    return False


def apply_non_neg_filters(market, price):
    """Apply ALL filters EXCEPT neg_risk. Returns (pass, reason)."""
    question = (market.get("question", "") or "").lower()
    category = (market.get("category", "") or "").lower()
    volume = market.get("volume", 0) or 0
    liquidity = market.get("liquidity", 0) or 0

    # Price check
    if category in POLITICS_CATEGORIES:
        if price < PRICE_THRESHOLD_POLITICS:
            return False, "price_low"
    else:
        if price < PRICE_THRESHOLD_DEFAULT:
            return False, "price_low"
    if price > MAX_PRICE:
        return False, "price_too_high"

    if liquidity < MIN_LIQUIDITY:
        return False, "low_liquidity"
    if volume < MIN_VOLUME:
        return False, "low_volume"
    if matches_any(question, COIN_FLIP_PATTERNS):
        return False, "coin_flip"
    if category in ALL_SPORTS_CATEGORIES and matches_any(question, SPORTS_BAD_PATTERNS):
        return False, "sports_ou_spread"
    if matches_any(question, THRESHOLD_PATTERNS):
        return False, "threshold"
    if matches_any(question, WEATHER_PATTERNS):
        return False, "weather"
    if matches_any(question, SLOW_KEYWORDS):
        return False, "slow_keywords"
    for p in FINANCIAL_ASSETS:
        if re.search(p, question):
            if volume < MIN_VOLUME_FINANCIAL:
                return False, "financial_low_vol"
            break

    return True, "passed"


def get_tradeable_price(market):
    """Find if market had a price in tradeable range at any snapshot.
    Returns the best (lowest above threshold) price, or None.
    """
    snapshots = market.get("snapshots", [])
    category = (market.get("category", "") or "").lower()
    min_price = PRICE_THRESHOLD_POLITICS if category in POLITICS_CATEGORIES else PRICE_THRESHOLD_DEFAULT

    tradeable_prices = []
    for snap in snapshots:
        prices = snap.get("prices", [])
        if not prices:
            continue
        high_price = max(prices) if prices else 0
        if min_price <= high_price <= MAX_PRICE:
            tradeable_prices.append(high_price)

    # Also check first_price and max_price_seen
    for p in [market.get("first_price", 0), market.get("max_price_seen", 0)]:
        if p and min_price <= p <= MAX_PRICE:
            tradeable_prices.append(p)

    return min(tradeable_prices) if tradeable_prices else None


# === ANALYSIS ===
resolved = [m for m in scanner.values() if m.get("high_outcome_won") is not None]
print(f"Resolved markets: {len(resolved)}")

# Split into neg_risk and regular
neg_resolved = [m for m in resolved if m.get("neg_risk", False)]
reg_resolved = [m for m in resolved if not m.get("neg_risk", False)]
print(f"  neg_risk: {len(neg_resolved)}, regular: {len(reg_resolved)}")

# 1. Markets that pass ALL filters (current: neg_risk blocked)
current_passed = []
current_blocked_by_neg = []  # would pass if neg_risk allowed
reasons_current = {}
reasons_neg_blocked = {}

for m in resolved:
    price = get_tradeable_price(m)
    if price is None:
        reasons_current["no_tradeable_price"] = reasons_current.get("no_tradeable_price", 0) + 1
        continue

    ok, reason = apply_non_neg_filters(m, price)
    if not ok:
        reasons_current[reason] = reasons_current.get(reason, 0) + 1
        continue

    # Passes all non-neg filters
    is_neg = m.get("neg_risk", False)
    m["_tradeable_price"] = price  # store for analysis

    if is_neg:
        current_blocked_by_neg.append(m)
        reasons_current["neg_risk"] = reasons_current.get("neg_risk", 0) + 1
    else:
        current_passed.append(m)

print(f"\n=== FILTER FUNNEL ===")
for k, v in sorted(reasons_current.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
print(f"  PASSED (current): {len(current_passed)}")
print(f"  Blocked ONLY by neg_risk: {len(current_blocked_by_neg)}")

# 2. Win rates
def analyze_group(markets, label):
    wins = sum(1 for m in markets if m.get("high_outcome_won"))
    losses = sum(1 for m in markets if not m.get("high_outcome_won"))
    total = wins + losses
    wr = wins / total * 100 if total > 0 else 0

    cats = {}
    prices = []
    resolve_hours = []
    for m in markets:
        cat = (m.get("category", "") or "").lower()
        cats[cat] = cats.get(cat, 0) + 1
        prices.append(m.get("_tradeable_price", m.get("max_price_seen", 0)))

        # Resolve time from snapshots
        snaps = m.get("snapshots", [])
        if len(snaps) >= 2:
            try:
                t0 = datetime.fromisoformat(snaps[0]["timestamp"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(snaps[-1]["timestamp"].replace("Z", "+00:00"))
                hours = (t1 - t0).total_seconds() / 3600
                if hours > 0:
                    resolve_hours.append(hours)
            except Exception:
                pass

    avg_price = sum(prices) / len(prices) if prices else 0
    med_resolve = sorted(resolve_hours)[len(resolve_hours)//2] if resolve_hours else 0
    avg_resolve = sum(resolve_hours) / len(resolve_hours) if resolve_hours else 0

    print(f"\n  {label}:")
    print(f"    Total: {total} (W:{wins} L:{losses})")
    print(f"    Win rate: {wr:.2f}%")
    print(f"    Avg entry price: {avg_price:.4f}")
    print(f"    Resolve time: median {med_resolve:.1f}h, avg {avg_resolve:.1f}h ({len(resolve_hours)} samples)")
    print(f"    Categories: {cats}")

    if losses > 0:
        print(f"    LOSSES:")
        for m in markets:
            if not m.get("high_outcome_won"):
                print(f"      [{m.get('category','')}] {m.get('question','')[:70]}")
                print(f"        price={m.get('_tradeable_price', m.get('max_price_seen',0)):.4f}, vol=${m.get('volume',0):.0f}")

    return {
        "total": total, "wins": wins, "losses": losses, "win_rate": wr,
        "avg_price": avg_price, "median_resolve_h": med_resolve,
        "avg_resolve_h": avg_resolve, "categories": cats,
    }

print(f"\n{'='*60}")
print("  PERFORMANCE COMPARISON")
print(f"{'='*60}")

stats_current = analyze_group(current_passed, "CURRENT (non-neg_risk only)")
stats_neg_blocked = analyze_group(current_blocked_by_neg, "BLOCKED by neg_risk (would be added)")
stats_combined = analyze_group(current_passed + current_blocked_by_neg, "COMBINED (if neg_risk allowed)")

# 3. Capital efficiency
print(f"\n{'='*60}")
print("  CAPITAL EFFICIENCY MODEL")
print(f"{'='*60}")

scanner_days = 3.7
bankroll = 700
bet_size = 10

for label, stats, markets in [
    ("CURRENT", stats_current, current_passed),
    ("WITH neg_risk", stats_combined, current_passed + current_blocked_by_neg),
]:
    bets_per_day = stats["total"] / scanner_days
    concurrent = bets_per_day * max(stats["median_resolve_h"], 1) / 24
    max_slots = bankroll / bet_size

    # Monthly PnL
    avg_p = stats["avg_price"] if stats["avg_price"] > 0 else 0.99
    profit_per_win = bet_size * (1.0 / avg_p - 1.0)
    total_profit = stats["wins"] * profit_per_win - stats["losses"] * bet_size
    monthly_pnl = total_profit / scanner_days * 30

    print(f"\n  {label}:")
    print(f"    Bets in {scanner_days}d: {stats['total']}")
    print(f"    Bets/day: {bets_per_day:.1f}")
    print(f"    Avg concurrent: {concurrent:.1f} (max slots: {max_slots:.0f})")
    print(f"    Profit/win: ${profit_per_win:.3f}")
    print(f"    Raw PnL in {scanner_days}d: ${total_profit:.2f}")
    print(f"    Monthly PnL estimate: ${monthly_pnl:.0f}")
    print(f"    Capital turnover/month: {stats['total'] * bet_size / bankroll / scanner_days * 30:.1f}x")

# 4. Neg_risk resolve time comparison (from actual bot data)
print(f"\n{'='*60}")
print("  NEG_RISK RESOLVE TIME (from actual bot positions)")
print(f"{'='*60}")

with open("positions.json") as f:
    positions = json.load(f)

neg_resolve = []
reg_resolve = []
for pos in positions["positions"].values():
    ts = pos.get("timestamp", "")
    resolved_at = pos.get("resolved_at", "")
    if ts and resolved_at and pos.get("status") == "won":
        try:
            t0 = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            hours = (t1 - t0).total_seconds() / 3600
            if pos.get("neg_risk"):
                neg_resolve.append(hours)
            else:
                reg_resolve.append(hours)
        except Exception:
            pass

if neg_resolve:
    neg_resolve.sort()
    print(f"  Neg_risk ({len(neg_resolve)} positions):")
    print(f"    Median: {neg_resolve[len(neg_resolve)//2]:.1f}h")
    print(f"    Avg: {sum(neg_resolve)/len(neg_resolve):.1f}h")
    print(f"    Min: {neg_resolve[0]:.1f}h, Max: {neg_resolve[-1]:.1f}h")

if reg_resolve:
    reg_resolve.sort()
    print(f"  Regular ({len(reg_resolve)} positions):")
    print(f"    Median: {reg_resolve[len(reg_resolve)//2]:.1f}h")
    print(f"    Avg: {sum(reg_resolve)/len(reg_resolve):.1f}h")
    print(f"    Min: {reg_resolve[0]:.1f}h, Max: {reg_resolve[-1]:.1f}h")

if neg_resolve and reg_resolve:
    ratio = (sum(neg_resolve)/len(neg_resolve)) / (sum(reg_resolve)/len(reg_resolve))
    print(f"\n  Neg_risk resolves {ratio:.1f}x slower than regular")

# Save
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "scanner_days": scanner_days,
    "total_resolved": len(resolved),
    "current_passed": stats_current,
    "neg_risk_blocked": stats_neg_blocked,
    "combined": stats_combined,
    "neg_resolve_hours_actual": neg_resolve,
    "reg_resolve_hours_actual": reg_resolve,
}
with open("_analytics/data/backtest_neg_risk_strategy_2026-03-20.json", "w") as f:
    json.dump(output, f, indent=2, default=str)
print("\nSaved to _analytics/data/backtest_neg_risk_strategy_2026-03-20.json")
