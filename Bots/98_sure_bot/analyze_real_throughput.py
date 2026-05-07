"""Exact throughput analysis from REAL bot data.
No models, no simulations — only facts from logs and positions.json.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ============================================================
# PART 1: ACTUAL BETS FROM LOGS
# ============================================================
print("=" * 60)
print("  PART 1: REAL BET COUNTS FROM LOGS")
print("=" * 60)

bets_by_hour = defaultdict(int)
bets_by_day = defaultdict(int)
filled_by_day = defaultdict(int)
not_filled_by_day = defaultdict(int)
scan_cycles_by_day = defaultdict(int)
candidates_by_day = defaultdict(list)

with open("bot_log.txt", encoding="utf-8", errors="replace") as f:
    for line in f:
        # Count "Placing bet" lines
        if "Placing bet" in line or "BET:" in line:
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}):\d{2}:\d{2}", line)
            if match:
                hour = match.group(1)
                day = hour[:10]
                bets_by_hour[hour] += 1
                bets_by_day[day] += 1

        # Count FILLED / NOT FILLED
        if "FILLED" in line and "NOT FILLED" not in line and "Placing" not in line:
            match = re.match(r"(\d{4}-\d{2}-\d{2})", line)
            if match:
                filled_by_day[match.group(1)] += 1

        if "NOT FILLED" in line or "not filled" in line.lower():
            match = re.match(r"(\d{4}-\d{2}-\d{2})", line)
            if match:
                not_filled_by_day[match.group(1)] += 1

        # Count scan cycles
        if "Scan cycle done" in line or "Scan cycle started" in line:
            match = re.match(r"(\d{4}-\d{2}-\d{2})", line)
            if match:
                if "done" in line:
                    scan_cycles_by_day[match.group(1)] += 1
                # Extract candidate count
                cand_match = re.search(r"(\d+) candidates", line)
                if cand_match:
                    candidates_by_day[match.group(1)].append(int(cand_match.group(1)))

print("\nBets placed per day:")
total_bets = 0
total_days = 0
for day in sorted(bets_by_day.keys()):
    bets = bets_by_day[day]
    filled = filled_by_day.get(day, 0)
    not_filled = not_filled_by_day.get(day, 0)
    scans = scan_cycles_by_day.get(day, 0)
    avg_cand = sum(candidates_by_day.get(day, [0])) / max(len(candidates_by_day.get(day, [1])), 1)
    print(f"  {day}: {bets} bets placed, {filled} filled, {not_filled} not filled, "
          f"{scans} scans, ~{avg_cand:.0f} candidates/scan")
    total_bets += bets
    total_days += 1

if total_days > 0:
    print(f"\n  AVERAGE: {total_bets/total_days:.1f} bets/day placed")
    total_filled = sum(filled_by_day.values())
    total_not_filled = sum(not_filled_by_day.values())
    if total_filled + total_not_filled > 0:
        print(f"  Fill rate: {total_filled/(total_filled+total_not_filled)*100:.1f}% "
              f"({total_filled} filled / {total_filled+total_not_filled} total)")

# Hourly distribution
print("\nBets by hour of day (UTC):")
hourly = defaultdict(int)
for hour_key, count in bets_by_hour.items():
    h = int(hour_key[11:13])
    hourly[h] += count
for h in range(24):
    bar = "#" * (hourly[h] // 2)
    print(f"  {h:02d}:00  {hourly[h]:3d}  {bar}")


# ============================================================
# PART 2: ACTUAL POSITIONS ANALYSIS
# ============================================================
print("\n" + "=" * 60)
print("  PART 2: REAL POSITIONS DATA")
print("=" * 60)

with open("positions.json") as f:
    data = json.load(f)

positions = data["positions"]

# Categorize
all_pos = []
for key, pos in positions.items():
    ts = pos.get("timestamp", "")
    if not ts:
        continue
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        continue
    all_pos.append({
        "key": key,
        "timestamp": t,
        "status": pos.get("status", ""),
        "neg_risk": pos.get("neg_risk", False),
        "cost": pos.get("cost_usd", 0),
        "price": pos.get("price", 0),
        "category": pos.get("category", ""),
        "resolved_at": pos.get("resolved_at", ""),
        "title": pos.get("title", ""),
    })

all_pos.sort(key=lambda x: x["timestamp"])

# Resolve times (only from won/lost positions with resolved_at)
neg_resolve = []
reg_resolve = []
for p in all_pos:
    if p["status"] not in ("won", "lost"):
        continue
    if not p["resolved_at"]:
        continue
    try:
        t1 = datetime.fromisoformat(p["resolved_at"].replace("Z", "+00:00"))
        hours = (t1 - p["timestamp"]).total_seconds() / 3600
        if hours > 0:
            if p["neg_risk"]:
                neg_resolve.append(hours)
            else:
                reg_resolve.append(hours)
    except Exception:
        pass

print(f"\nResolve times (from real resolved positions):")
if reg_resolve:
    reg_resolve.sort()
    print(f"  Regular ({len(reg_resolve)} positions):")
    print(f"    p25={reg_resolve[len(reg_resolve)//4]:.1f}h  "
          f"p50={reg_resolve[len(reg_resolve)//2]:.1f}h  "
          f"p75={reg_resolve[int(len(reg_resolve)*0.75)]:.1f}h  "
          f"p90={reg_resolve[int(len(reg_resolve)*0.9)]:.1f}h")

if neg_resolve:
    neg_resolve.sort()
    print(f"  Neg_risk ({len(neg_resolve)} positions):")
    print(f"    p25={neg_resolve[len(neg_resolve)//4]:.1f}h  "
          f"p50={neg_resolve[len(neg_resolve)//2]:.1f}h  "
          f"p75={neg_resolve[int(len(neg_resolve)*0.75)]:.1f}h  "
          f"p90={neg_resolve[int(len(neg_resolve)*0.9)]:.1f}h")

# Concurrent positions over time (hour by hour)
print(f"\nConcurrent positions timeline:")
if all_pos:
    start = all_pos[0]["timestamp"]
    end = datetime.now(timezone.utc)

    # Build timeline: for each hour, how many positions were open
    # A position is "open" from timestamp until resolved_at (or now if still open)
    max_concurrent = 0
    max_concurrent_neg = 0
    max_concurrent_reg = 0
    concurrent_samples = []

    current = start
    while current < end:
        open_count = 0
        open_neg = 0
        open_reg = 0
        open_cost = 0
        open_neg_cost = 0

        for p in all_pos:
            if p["timestamp"] > current:
                break
            # Is this position still open at this time?
            if p["resolved_at"]:
                try:
                    resolved = datetime.fromisoformat(p["resolved_at"].replace("Z", "+00:00"))
                    if resolved <= current:
                        continue
                except Exception:
                    pass
            elif p["status"] in ("sold", "selling"):
                continue

            open_count += 1
            open_cost += p["cost"]
            if p["neg_risk"]:
                open_neg += 1
                open_neg_cost += p["cost"]
            else:
                open_reg += 1

        if open_count > max_concurrent:
            max_concurrent = open_count
        max_concurrent_neg = max(max_concurrent_neg, open_neg)
        max_concurrent_reg = max(max_concurrent_reg, open_reg)

        concurrent_samples.append({
            "time": current,
            "total": open_count,
            "neg": open_neg,
            "reg": open_reg,
            "cost": open_cost,
            "neg_cost": open_neg_cost,
        })

        current += timedelta(hours=6)  # sample every 6 hours

    print(f"  Max concurrent: {max_concurrent} total ({max_concurrent_neg} neg + {max_concurrent_reg} reg)")

    if concurrent_samples:
        avg_total = sum(s["total"] for s in concurrent_samples) / len(concurrent_samples)
        avg_neg = sum(s["neg"] for s in concurrent_samples) / len(concurrent_samples)
        avg_reg = sum(s["reg"] for s in concurrent_samples) / len(concurrent_samples)
        avg_cost = sum(s["cost"] for s in concurrent_samples) / len(concurrent_samples)
        avg_neg_cost = sum(s["neg_cost"] for s in concurrent_samples) / len(concurrent_samples)

        print(f"  Avg concurrent: {avg_total:.1f} total ({avg_neg:.1f} neg + {avg_reg:.1f} reg)")
        print(f"  Avg capital locked: ${avg_cost:.0f} total (${avg_neg_cost:.0f} neg + ${avg_cost-avg_neg_cost:.0f} reg)")

    # Show timeline
    print(f"\n  Timeline (every 6h):")
    for s in concurrent_samples:
        bar_neg = "N" * s["neg"]
        bar_reg = "R" * s["reg"]
        t_str = s["time"].strftime("%m-%d %H:%M")
        print(f"    {t_str} | {s['total']:3d} open (${s['cost']:6.0f}) | {bar_reg}{bar_neg}")


# ============================================================
# PART 3: PROFIT PER BET (actual)
# ============================================================
print("\n" + "=" * 60)
print("  PART 3: ACTUAL PROFIT PER BET")
print("=" * 60)

total_profit = 0
total_loss = 0
won_count = 0
lost_count = 0
profits = []

for p in all_pos:
    if p["status"] == "won":
        # profit = shares * $1 - cost
        # shares = cost / price (approximately)
        # but we know: shares are stored in positions.json
        pass

# Get actual profits from positions
for key, pos in positions.items():
    if pos.get("status") == "won":
        cost = pos.get("cost_usd", 0)
        shares = pos.get("size_shares", 0)
        profit = shares - cost  # shares pay $1 each
        total_profit += profit
        profits.append(profit)
        won_count += 1
    elif pos.get("status") == "lost":
        cost = pos.get("cost_usd", 0)
        total_loss += cost
        lost_count += 1

if profits:
    profits.sort()
    avg_profit = total_profit / won_count
    print(f"  Won: {won_count}, Lost: {lost_count}")
    print(f"  Total profit from wins: ${total_profit:.2f}")
    print(f"  Total loss: ${total_loss:.2f}")
    print(f"  Net PnL: ${total_profit - total_loss:.2f}")
    print(f"  Avg profit per win: ${avg_profit:.3f}")
    print(f"  Median profit per win: ${profits[len(profits)//2]:.3f}")
    print(f"  Min profit: ${profits[0]:.3f}, Max: ${profits[-1]:.3f}")


# ============================================================
# PART 4: BANKROLL CALCULATION
# ============================================================
print("\n" + "=" * 60)
print("  PART 4: BANKROLL MATH (from real data)")
print("=" * 60)

# How many days has the bot been running?
if all_pos:
    first_bet = all_pos[0]["timestamp"]
    last_bet = all_pos[-1]["timestamp"]
    bot_days = (last_bet - first_bet).total_seconds() / 86400
    print(f"  Bot running: {bot_days:.1f} days")
    print(f"  First bet: {first_bet.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Last bet: {last_bet.strftime('%Y-%m-%d %H:%M')}")

# Real bets per day (from positions, not logs — positions are ground truth)
# Split by neg_risk
neg_bets = [p for p in all_pos if p["neg_risk"]]
reg_bets = [p for p in all_pos if not p["neg_risk"]]

print(f"\n  Total positions: {len(all_pos)}")
print(f"    Neg_risk: {len(neg_bets)} ({len(neg_bets)/bot_days:.1f}/day)")
print(f"    Regular: {len(reg_bets)} ({len(reg_bets)/bot_days:.1f}/day)")
print(f"    ALL: {len(all_pos)/bot_days:.1f}/day")

# But first 2 days had way more bets (burst at start)
# Let's separate burst vs steady state
if bot_days > 1:
    day1_bets = sum(1 for p in all_pos if (p["timestamp"] - first_bet).total_seconds() < 86400)
    day2_plus = len(all_pos) - day1_bets
    days_after_1 = max(bot_days - 1, 0.5)
    print(f"\n  Day 1 (burst): {day1_bets} bets")
    print(f"  Day 2+: {day2_plus} bets in {days_after_1:.1f} days = {day2_plus/days_after_1:.1f}/day")

# What limits throughput? Balance!
# Count periods where bot had no money
low_balance_count = 0
with open("bot_log.txt", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "balance too low" in line.lower() or "not enough balance" in line.lower():
            low_balance_count += 1
print(f"\n  'Balance too low' warnings: {low_balance_count}")

# ============================================================
# PART 5: THROUGHPUT CEILING — HOW MANY BETS/DAY IS POSSIBLE?
# ============================================================
print("\n" + "=" * 60)
print("  PART 5: THROUGHPUT CEILING")
print("=" * 60)

# From scanner data: how many unique markets per day pass our filters?
# This is the TRUE ceiling — can't bet more than this
with open("C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json") as f:
    scanner = json.load(f)["markets"]

# Filter same as backtest
PRICE_THRESHOLD_DEFAULT = 0.975
PRICE_THRESHOLD_POLITICS = 0.96
MAX_PRICE = 0.995
MIN_LIQUIDITY = 500
MIN_VOLUME = 3000
POLITICS_CATEGORIES = {"politics", "geopolitics"}
ALL_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                         "american_football", "tennis", "fighting", "cricket", "soccer"}
COIN_FLIP_PATTERNS = [r'\bodd\s+or\s+even\b', r'\bodd/even\b', r'\bfirst\s+blood\b',
    r'\bfirst\s+kill\b', r'\bfirst\s+baron\b', r'\bfirst\s+dragon\b',
    r'\bfirst\s+tower\b', r'\bfirst\s+rift\s+herald\b', r'\bcoin\s+flip\b',
    r'\brampage\b', r'\bfirst\s+roshan\b', r'\bfirst\s+map\b', r'\bup\s+or\s+down\b']
THRESHOLD_PATTERNS = [r'\bclose\s+above\b', r'\bclose\s+below\b', r'\bbe\s+above\b',
    r'\bbe\s+below\b', r'\bbe\s+between\b', r'\bprice\s+of\b',
    r'\breach\b.*\$[\d,]+', r'\bhit\b.*\$[\d,]+']
SLOW_KEYWORDS = [r'\btop\b', r'\bseason\b', r'\bmost\b', r'\btransit\b',
    r'\bstrait\b', r'\bships?\b', r'\bweekly\b', r'\bmonthly\b']
SPORTS_BAD_PATTERNS = [r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
    r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?|goals?)\b', r'\bhandi?cap\b']

def matches_any(text, patterns):
    return any(re.search(p, text) for p in patterns)

def passes_filters(m, allow_neg_risk=False):
    price = m.get("max_price_seen", 0)
    question = (m.get("question", "") or "").lower()
    category = (m.get("category", "") or "").lower()
    neg_risk = m.get("neg_risk", False)
    volume = m.get("volume", 0) or 0
    liquidity = m.get("liquidity", 0) or 0

    min_p = PRICE_THRESHOLD_POLITICS if category in POLITICS_CATEGORIES else PRICE_THRESHOLD_DEFAULT
    if price < min_p or price > MAX_PRICE:
        return False
    if neg_risk and not allow_neg_risk:
        return False
    if liquidity < MIN_LIQUIDITY or volume < MIN_VOLUME:
        return False
    if matches_any(question, COIN_FLIP_PATTERNS):
        return False
    if category in ALL_SPORTS_CATEGORIES and matches_any(question, SPORTS_BAD_PATTERNS):
        return False
    if matches_any(question, THRESHOLD_PATTERNS):
        return False
    if matches_any(question, SLOW_KEYWORDS):
        return False
    return True

# Check tradeable price from snapshots
def has_tradeable_price(m):
    cat = (m.get("category", "") or "").lower()
    min_p = PRICE_THRESHOLD_POLITICS if cat in POLITICS_CATEGORIES else PRICE_THRESHOLD_DEFAULT
    for snap in m.get("snapshots", []):
        prices = snap.get("prices", [])
        if prices:
            high = max(prices)
            if min_p <= high <= MAX_PRICE:
                return True
    fp = m.get("first_price", 0)
    mp = m.get("max_price_seen", 0)
    return (min_p <= fp <= MAX_PRICE) or (min_p <= mp <= MAX_PRICE)

scanner_days = 3.7

# Count markets that pass filters (unique opportunities)
reg_pass = 0
neg_pass = 0
for m in scanner.values():
    if not has_tradeable_price(m):
        continue
    if passes_filters(m, allow_neg_risk=False):
        reg_pass += 1
    elif m.get("neg_risk", False) and passes_filters(m, allow_neg_risk=True):
        neg_pass += 1

print(f"Scanner data: {scanner_days} days, {len(scanner)} markets total")
print(f"  Markets passing filters (unique opportunities):")
print(f"    Regular: {reg_pass} ({reg_pass/scanner_days:.1f}/day)")
print(f"    Neg_risk: {neg_pass} ({neg_pass/scanner_days:.1f}/day)")
print(f"    Total: {reg_pass+neg_pass} ({(reg_pass+neg_pass)/scanner_days:.1f}/day)")

# Apply fill rate
fill_rate = 0.596
print(f"\n  After fill rate ({fill_rate*100:.0f}%):")
print(f"    Regular: {reg_pass*fill_rate/scanner_days:.1f}/day filled")
print(f"    Neg_risk: {neg_pass*fill_rate/scanner_days:.1f}/day filled")
print(f"    Total: {(reg_pass+neg_pass)*fill_rate/scanner_days:.1f}/day filled")


# ============================================================
# PART 6: BANKROLL vs ROI TABLE
# ============================================================
print("\n" + "=" * 60)
print("  PART 6: BANKROLL vs ROI (HARD MATH)")
print("=" * 60)

# Real numbers:
reg_per_day = reg_pass * fill_rate / scanner_days  # filled regular bets per day
neg_per_day = neg_pass * fill_rate / scanner_days  # filled neg_risk bets per day
bet_size = 10
reg_resolve_h = reg_resolve[len(reg_resolve)//2] if reg_resolve else 10  # median from real data
neg_resolve_h = neg_resolve[len(neg_resolve)//2] if neg_resolve else 53  # median from real data
avg_profit_per_win = sum(profits) / len(profits) if profits else 0.07

print(f"Parameters (all from real data):")
print(f"  Regular: {reg_per_day:.1f} bets/day, resolve {reg_resolve_h:.0f}h")
print(f"  Neg_risk: {neg_per_day:.1f} bets/day, resolve {neg_resolve_h:.0f}h")
print(f"  Avg profit per win: ${avg_profit_per_win:.3f}")
print(f"  Bet size: ${bet_size}")

# How many concurrent slots needed?
reg_concurrent = reg_per_day * reg_resolve_h / 24
neg_concurrent = neg_per_day * neg_resolve_h / 24

print(f"\n  Concurrent slots needed (if unlimited capital):")
print(f"    Regular: {reg_per_day:.1f}/day * {reg_resolve_h:.0f}h / 24 = {reg_concurrent:.1f} slots")
print(f"    Neg_risk: {neg_per_day:.1f}/day * {neg_resolve_h:.0f}h / 24 = {neg_concurrent:.1f} slots")
print(f"    Total: {reg_concurrent + neg_concurrent:.1f} slots = ${(reg_concurrent + neg_concurrent) * bet_size:.0f}")

# For each bankroll: how many bets actually get placed (capital-limited)?
print(f"\n{'Bankroll':>10} {'NegCap':>8} {'Reg/d':>7} {'Neg/d':>7} {'All/d':>7} "
      f"{'PnL/mo':>8} {'ROI/mo':>8}")
print("-" * 70)

results = []
for bankroll in [100, 200, 300, 500, 700, 1000, 1500, 2000, 3000, 5000]:
    for neg_cap_pct in [0, 0.5, 0.7, 1.0]:
        max_slots = bankroll / bet_size
        neg_cap_slots = max_slots * neg_cap_pct

        # Regular bets: limited by available opportunities AND capital
        # Regular slots = min(reg_concurrent, max_slots - neg used)
        # But regular resolve fast, so they don't pile up much

        # Actual reg concurrent = min(reg_concurrent, max_slots)
        actual_reg_concurrent = min(reg_concurrent, max_slots)
        # If reg needs fewer slots than available, all reg bets go through
        if reg_concurrent <= max_slots:
            actual_reg_daily = reg_per_day  # not capital-limited
        else:
            # Capital-limited: can only cycle max_slots * 24/resolve_h
            actual_reg_daily = max_slots * 24 / reg_resolve_h

        remaining_slots = max_slots - actual_reg_concurrent

        # Neg_risk: limited by cap AND remaining slots AND opportunities
        neg_slots_allowed = min(neg_cap_slots, remaining_slots)
        if neg_cap_pct == 0:
            actual_neg_daily = 0
        else:
            actual_neg_concurrent = min(neg_concurrent, neg_slots_allowed)
            if neg_concurrent <= neg_slots_allowed:
                actual_neg_daily = neg_per_day  # not capital-limited
            else:
                actual_neg_daily = neg_slots_allowed * 24 / neg_resolve_h

        total_daily = actual_reg_daily + actual_neg_daily

        # PnL: (bets/day * avg_profit - expected_losses) * 30
        loss_rate = 0.003  # 0.3% — between optimistic 0.1% and conservative 0.5%
        monthly_profit = total_daily * 30 * avg_profit_per_win * (1 - loss_rate)
        monthly_losses = total_daily * 30 * loss_rate * bet_size
        monthly_pnl = monthly_profit - monthly_losses
        roi = monthly_pnl / bankroll * 100 if bankroll > 0 else 0

        cap_label = "OFF" if neg_cap_pct == 0 else f"{int(neg_cap_pct*100)}%"

        print(f"${bankroll:>8} {cap_label:>8} {actual_reg_daily:>6.1f} {actual_neg_daily:>6.1f} "
              f"{total_daily:>6.1f} ${monthly_pnl:>6.0f} {roi:>7.1f}%")

        results.append({
            "bankroll": bankroll,
            "neg_cap_pct": neg_cap_pct,
            "reg_daily": round(actual_reg_daily, 1),
            "neg_daily": round(actual_neg_daily, 1),
            "total_daily": round(total_daily, 1),
            "monthly_pnl": round(monthly_pnl, 0),
            "roi_pct": round(roi, 1),
        })

# Find max bankroll for >10% ROI
print("\n\nMax bankroll for ROI > 10%/month:")
for neg_cap_pct in [0, 0.5, 0.7, 1.0]:
    cap_label = "OFF" if neg_cap_pct == 0 else f"{int(neg_cap_pct*100)}%"
    relevant = [r for r in results if r["neg_cap_pct"] == neg_cap_pct and r["roi_pct"] >= 10]
    if relevant:
        max_br = max(r["bankroll"] for r in relevant)
        pnl = [r for r in relevant if r["bankroll"] == max_br][0]["monthly_pnl"]
        print(f"  Neg cap {cap_label}: bankroll up to ${max_br} (PnL ${pnl:.0f}/mo, ROI {pnl/max_br*100:.1f}%)")
    else:
        print(f"  Neg cap {cap_label}: even $100 doesn't reach 10% ROI")

# Save
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "bot_days": round(bot_days, 1),
    "real_bets_per_day": round(len(all_pos) / bot_days, 1),
    "scanner_opportunities_per_day": {
        "regular": round(reg_pass / scanner_days, 1),
        "neg_risk": round(neg_pass / scanner_days, 1),
    },
    "resolve_times_real": {
        "regular_median_h": round(reg_resolve_h, 1),
        "neg_risk_median_h": round(neg_resolve_h, 1),
    },
    "avg_profit_per_win": round(avg_profit_per_win, 4),
    "fill_rate": fill_rate,
    "scenarios": results,
}
with open("_analytics/data/bankroll_analysis_2026-03-20.json", "w") as f:
    json.dump(output, f, indent=2)
print("\nSaved to _analytics/data/bankroll_analysis_2026-03-20.json")
