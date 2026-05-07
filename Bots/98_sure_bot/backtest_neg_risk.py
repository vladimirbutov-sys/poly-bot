"""Backtest: neg_risk impact on strategy with FIXED redemption.

Compares:
1. CURRENT: skip all neg_risk (check_skip_neg_risk active)
2. ALLOW_NEG_RISK: allow neg_risk (remove check_skip_neg_risk)
3. ALLOW_NEG_RISK_POLITICS_ONLY: allow neg_risk only for politics/geopolitics

For each: win rate, # bets, resolve time, monthly PnL estimate.
Uses 97_scanner resolved data as ground truth.
"""
import json
import re
from datetime import datetime, timezone

# Load scanner data
print("Loading scanner data...", flush=True)
with open("C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json") as f:
    scanner = json.load(f)
scanner = scanner["markets"]  # actual markets dict
print(f"Loaded {len(scanner)} markets")

# Current config values
PRICE_THRESHOLD_DEFAULT = 0.975
PRICE_THRESHOLD_POLITICS = 0.96
MAX_PRICE = 0.995
MIN_LIQUIDITY = 500
MIN_VOLUME = 3000

POLITICS_CATEGORIES = {"politics", "geopolitics"}
ALL_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                         "american_football", "tennis", "fighting", "cricket", "soccer"}

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
WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b', r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
    r'\d+\s*[°]?\s*[FC]\b.*\btemperature\b', r'\d+\s*[°]?\s*[FC]\b.*\bhighest\s+temp\b',
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
MIN_VOLUME_FINANCIAL = 50000


def matches_any(text, patterns):
    for p in patterns:
        if re.search(p, text):
            return True
    return False


def apply_filters(market, skip_neg_risk=True, allow_neg_risk_politics=False):
    """Apply all current filters. Returns (pass, reason)."""
    price = market.get("max_price_seen", 0)
    question = (market.get("question", "") or "").lower()
    category = (market.get("category", "") or "").lower()
    neg_risk = market.get("neg_risk", False)
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

    # Neg risk check
    if neg_risk and skip_neg_risk:
        if allow_neg_risk_politics and category in POLITICS_CATEGORIES:
            pass
        else:
            return False, "neg_risk"

    # Liquidity
    if liquidity < MIN_LIQUIDITY:
        return False, "low_liquidity"

    # Volume
    if volume < MIN_VOLUME:
        return False, "low_volume"

    # Coin flip
    if matches_any(question, COIN_FLIP_PATTERNS):
        return False, "coin_flip"

    # Sports win only
    if category in ALL_SPORTS_CATEGORIES:
        if matches_any(question, SPORTS_BAD_PATTERNS):
            return False, "sports_ou_spread"

    # Threshold
    if matches_any(question, THRESHOLD_PATTERNS):
        return False, "threshold"

    # Weather
    if matches_any(question, WEATHER_PATTERNS):
        return False, "weather"

    # Slow keywords
    if matches_any(question, SLOW_KEYWORDS):
        return False, "slow_keywords"

    # Financial assets
    for p in FINANCIAL_ASSETS:
        if re.search(p, question):
            if volume < MIN_VOLUME_FINANCIAL:
                return False, "financial_low_vol"
            break

    return True, "passed"


# Filter to resolved markets only
resolved = []
for mid, m in scanner.items():
    won = m.get("high_outcome_won")
    if won is not None:  # resolved
        resolved.append(m)
    elif m.get("resolved") and isinstance(m.get("resolution"), dict):
        # Alternative format: check resolution.winner == high_outcome
        res = m["resolution"]
        high = m.get("high_outcome", "")
        winner = res.get("winner", "")
        if winner:
            m["high_outcome_won"] = (winner == high)
            resolved.append(m)

print(f"Resolved markets: {len(resolved)}")

# Count neg_risk in resolved
neg_resolved = sum(1 for m in resolved if m.get("neg_risk", False))
print(f"  of which neg_risk: {neg_resolved}")

# Run backtest for each configuration
configs = [
    ("CURRENT (skip neg_risk)", {"skip_neg_risk": True, "allow_neg_risk_politics": False}),
    ("ALLOW ALL neg_risk", {"skip_neg_risk": False, "allow_neg_risk_politics": False}),
    ("ALLOW neg_risk POLITICS only", {"skip_neg_risk": True, "allow_neg_risk_politics": True}),
]

results = {}
for config_name, kwargs in configs:
    wins = 0
    losses = 0
    neg_risk_wins = 0
    neg_risk_losses = 0
    resolve_hours_neg = []
    resolve_hours_reg = []
    categories_neg = {}
    categories_reg = {}
    loss_details = []
    price_sum_neg = 0
    price_sum_reg = 0

    for m in resolved:
        ok, reason = apply_filters(m, **kwargs)
        if not ok:
            continue

        won = m.get("high_outcome_won", False)
        is_neg = m.get("neg_risk", False)
        cat = (m.get("category", "") or "").lower()
        price = m.get("max_price_seen", 0)

        if won:
            wins += 1
            if is_neg:
                neg_risk_wins += 1
                categories_neg[cat] = categories_neg.get(cat, 0) + 1
                price_sum_neg += price
            else:
                categories_reg[cat] = categories_reg.get(cat, 0) + 1
                price_sum_reg += price
        else:
            losses += 1
            if is_neg:
                neg_risk_losses += 1
            loss_details.append({
                "question": m.get("question", "")[:80],
                "category": cat,
                "neg_risk": is_neg,
                "price": price,
            })

        # Resolve time estimate (first_seen to last_seen)
        fs = m.get("first_seen", "")
        ls = m.get("last_seen", "")
        if fs and ls:
            try:
                t0 = datetime.fromisoformat(fs.replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(ls.replace("Z", "+00:00"))
                hours = (t1 - t0).total_seconds() / 3600
                if hours > 0:
                    if is_neg:
                        resolve_hours_neg.append(hours)
                    else:
                        resolve_hours_reg.append(hours)
            except Exception:
                pass

    total = wins + losses

    neg_resolve_med = sorted(resolve_hours_neg)[len(resolve_hours_neg)//2] if resolve_hours_neg else 0
    reg_resolve_med = sorted(resolve_hours_reg)[len(resolve_hours_reg)//2] if resolve_hours_reg else 0
    avg_price_neg = price_sum_neg / neg_risk_wins if neg_risk_wins > 0 else 0
    avg_price_reg = price_sum_reg / (wins - neg_risk_wins) if (wins - neg_risk_wins) > 0 else 0

    results[config_name] = {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total * 100 if total > 0 else 0,
        "neg_risk_wins": neg_risk_wins,
        "neg_risk_losses": neg_risk_losses,
        "reg_wins": wins - neg_risk_wins,
        "reg_losses": losses - neg_risk_losses,
        "neg_resolve_median_h": round(neg_resolve_med, 1),
        "reg_resolve_median_h": round(reg_resolve_med, 1),
        "avg_price_neg": round(avg_price_neg, 4),
        "avg_price_reg": round(avg_price_reg, 4),
        "categories_neg": categories_neg,
        "categories_reg": categories_reg,
        "loss_details": loss_details,
    }

# Print results
for name, r in results.items():
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  Total bets: {r['total']}  (W:{r['wins']} L:{r['losses']})")
    print(f"  Win rate: {r['win_rate']:.2f}%")
    print(f"  --- Regular ---")
    print(f"    W/L: {r['reg_wins']}/{r['reg_losses']}, resolve median: {r['reg_resolve_median_h']}h, avg price: {r['avg_price_reg']}")
    print(f"    Categories: {r['categories_reg']}")
    print(f"  --- Neg_risk ---")
    print(f"    W/L: {r['neg_risk_wins']}/{r['neg_risk_losses']}, resolve median: {r['neg_resolve_median_h']}h, avg price: {r['avg_price_neg']}")
    print(f"    Categories: {r['categories_neg']}")
    if r['loss_details']:
        print(f"  --- LOSSES ---")
        for l in r['loss_details']:
            print(f"    [{l['category']}] neg={l['neg_risk']} price={l['price']:.3f}: {l['question']}")

# Capital efficiency analysis
print(f"\n{'='*60}")
print("  CAPITAL EFFICIENCY ANALYSIS")
print(f"{'='*60}")

bankroll = 700  # ~current total capital after redemptions
bet_size = 10
scanner_days = 3.7

for name, r in results.items():
    reg_per_day = (r['reg_wins'] + r['reg_losses']) / scanner_days
    neg_per_day = (r['neg_risk_wins'] + r['neg_risk_losses']) / scanner_days

    reg_resolve_h = max(r['reg_resolve_median_h'], 1)
    neg_resolve_h = max(r['neg_resolve_median_h'], 1)

    # Average concurrent positions
    reg_concurrent = reg_per_day * reg_resolve_h / 24
    neg_concurrent = neg_per_day * neg_resolve_h / 24
    total_concurrent = reg_concurrent + neg_concurrent

    max_concurrent = bankroll / bet_size

    # Monthly PnL: (wins * avg_profit - losses * bet_size) / scanner_days * 30
    # avg_profit per $10 bet depends on avg price
    # profit_per_win = $10 * (1/price - 1) ... actually shares = cost/price, payout = shares
    # At price 0.99: buy $10 of shares @ 0.99 = 10.10 shares. Payout = $10.10. Profit = $0.10
    reg_price = r['avg_price_reg'] if r['avg_price_reg'] > 0 else 0.993
    neg_price = r['avg_price_neg'] if r['avg_price_neg'] > 0 else 0.993

    reg_profit_per_win = bet_size * (1 / reg_price - 1)
    neg_profit_per_win = bet_size * (1 / neg_price - 1)

    total_profit = (r['reg_wins'] * reg_profit_per_win +
                    r['neg_risk_wins'] * neg_profit_per_win -
                    r['losses'] * bet_size)
    monthly_pnl = total_profit / scanner_days * 30

    # Capital turnover = total bets * bet_size / (bankroll * scanner_days) * 30
    turnover = r['total'] * bet_size / bankroll / scanner_days * 30

    print(f"\n  {name}:")
    print(f"    Bets/day: {reg_per_day:.1f} reg + {neg_per_day:.1f} neg = {reg_per_day+neg_per_day:.1f}")
    print(f"    Avg concurrent: {reg_concurrent:.1f} reg + {neg_concurrent:.1f} neg = {total_concurrent:.1f}")
    print(f"    Max concurrent slots ($700/$10): {max_concurrent:.0f}")
    print(f"    Capital utilization: {total_concurrent/max_concurrent*100:.0f}%")
    print(f"    Avg profit/win: reg=${reg_profit_per_win:.3f}, neg=${neg_profit_per_win:.3f}")
    print(f"    Raw PnL in {scanner_days}d: ${total_profit:.2f}")
    print(f"    Monthly PnL estimate: ${monthly_pnl:.0f}")
    print(f"    Capital turnover/month: {turnover:.1f}x")

# Save results
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "data_source": "97_scanner resolved markets",
    "total_resolved": len(resolved),
    "neg_risk_resolved": neg_resolved,
    "bankroll_assumed": bankroll,
    "bet_size": bet_size,
    "scanner_days": scanner_days,
    "results": {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()},
}
with open("_analytics/data/backtest_neg_risk_strategy_2026-03-20.json", "w") as f:
    json.dump(output, f, indent=2, default=str)
print("\nSaved to _analytics/data/backtest_neg_risk_strategy_2026-03-20.json")
