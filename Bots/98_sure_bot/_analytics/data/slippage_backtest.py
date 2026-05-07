"""Slippage & Stale Price backtest for 98_sure_bot."""
import re
import json
import os

BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(BOT_DIR, "bot_log.txt")
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")

# ── Parse log ──
placing_re = re.compile(r'Placing bet: (.+?) \| price ([0-9.]+) -> limit ([0-9.]+) \| \$([0-9.]+)')
not_filled_re = re.compile(r'NOT FILLED \(TIMEOUT\): (.+)')
stale_skip_re = re.compile(r'STALE PRICE SKIP: (.+?) \| Gamma=([0-9.]+), CLOB=([0-9.]+)')
stale_re = re.compile(r'STALE PRICE: Gamma=([0-9.]+), CLOB=([0-9.]+), diff=([0-9.]+)')

bets = []
not_filled_titles = set()
stale_events = []

with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        m = placing_re.search(line)
        if m:
            bets.append({
                "title": m.group(1).strip()[:60],
                "price": float(m.group(2)),
                "limit": float(m.group(3)),
                "slippage": round(float(m.group(3)) - float(m.group(2)), 4),
                "amount": float(m.group(4)),
            })

        m2 = not_filled_re.search(line)
        if m2:
            not_filled_titles.add(m2.group(1).strip()[:60])

        m3 = stale_skip_re.search(line)
        if m3:
            stale_events.append({
                "title": m3.group(1).strip()[:60],
                "gamma": float(m3.group(2)),
                "clob": float(m3.group(3)),
                "diff": round(float(m3.group(2)) - float(m3.group(3)), 4),
            })
        else:
            m4 = stale_re.search(line)
            if m4:
                stale_events.append({
                    "title": "(from warning line)",
                    "gamma": float(m4.group(1)),
                    "clob": float(m4.group(2)),
                    "diff": float(m4.group(3)),
                })

# Mark filled
for b in bets:
    b["filled"] = b["title"] not in not_filled_titles

# ── SECTION 1: Fill rate by price bucket ──
buckets = [
    (0.960, 0.975, "politics 96-97.5c"),
    (0.975, 0.985, "97.5-98.5c"),
    (0.985, 0.990, "98.5-99c"),
    (0.990, 0.996, "99-99.5c"),
]

print("=" * 90)
print("  SECTION 1: FILL RATE BY PRICE BUCKET")
print("=" * 90)
print(f"{'Bucket':20s} | {'Total':>6s} | {'Filled':>6s} | {'Unfilled':>8s} | {'Fill%':>6s} | {'AvgSlip':>8s}")
print("-" * 70)

for lo, hi, label in buckets:
    in_bucket = [b for b in bets if lo <= b["price"] < hi]
    filled = [b for b in in_bucket if b["filled"]]
    n = len(in_bucket)
    fill_pct = len(filled) / n * 100 if n > 0 else 0
    avg_slip = sum(b["slippage"] for b in in_bucket) / n if n > 0 else 0
    print(f"{label:20s} | {n:6d} | {len(filled):6d} | {n - len(filled):8d} | {fill_pct:5.1f}% | {avg_slip:8.4f}")

total = len(bets)
total_filled = sum(1 for b in bets if b["filled"])
print("-" * 70)
print(f"{'TOTAL':20s} | {total:6d} | {total_filled:6d} | {total - total_filled:8d} | {total_filled / total * 100:5.1f}%")

# ── SECTION 2: Slippage distribution ──
print()
print("=" * 90)
print("  SECTION 2: FILL RATE BY SLIPPAGE VALUE")
print("=" * 90)
slip_vals = sorted(set(round(b["slippage"], 3) for b in bets))
print(f"{'Slippage':>10s} | {'Total':>6s} | {'Filled':>6s} | {'Unfilled':>8s} | {'Fill%':>6s}")
print("-" * 50)
for sv in slip_vals:
    in_slip = [b for b in bets if round(b["slippage"], 3) == sv]
    filled = [b for b in in_slip if b["filled"]]
    n = len(in_slip)
    fill_pct = len(filled) / n * 100 if n > 0 else 0
    print(f"{sv:10.3f} | {n:6d} | {len(filled):6d} | {n - len(filled):8d} | {fill_pct:5.1f}%")

# ── SECTION 3: ROI impact ──
print()
print("=" * 90)
print("  SECTION 3: ROI IMPACT — CURRENT vs PROPOSED SLIPPAGE")
print("=" * 90)

current_rules = [(0.960, 0.975, 0.005), (0.975, 0.985, 0.004), (0.985, 0.990, 0.003), (0.990, 0.995, 0.002)]
proposed_rules = [(0.960, 0.975, 0.006), (0.975, 0.985, 0.005), (0.985, 0.990, 0.004), (0.990, 0.995, 0.003)]

for label, rules in [("CURRENT", current_rules), ("PROPOSED +0.001", proposed_rules)]:
    total_cost = 0
    total_payout = 0
    count = 0
    for b in bets:
        if b["filled"]:
            for lo, hi, slip in rules:
                if lo <= b["price"] < hi:
                    limit = min(b["price"] + slip, 0.995)
                    cost_per_share = limit
                    payout_per_share = 1.0  # $1 on win
                    roi_per_share = (payout_per_share - cost_per_share) / cost_per_share
                    total_cost += b["amount"]
                    total_payout += b["amount"] / cost_per_share  # shares * $1
                    count += 1
                    break

    if total_cost > 0:
        avg_roi = (total_payout - total_cost) / total_cost * 100
        lost_to_slip = total_payout - total_cost
        print(f"{label}:")
        print(f"  Filled trades: {count}")
        print(f"  Total invested: ${total_cost:.2f}")
        print(f"  Expected payout (all win): ${total_payout:.2f}")
        print(f"  Gross profit: ${total_payout - total_cost:.2f}")
        print(f"  Avg ROI per trade: {avg_roi:.3f}%")
        print()

# Per-bucket ROI comparison
print("Per-bucket ROI comparison:")
print(f"{'Bucket':20s} | {'Current ROI':>12s} | {'Proposed ROI':>12s} | {'ROI loss':>10s}")
print("-" * 65)
for lo, hi, label in buckets:
    in_bucket = [b for b in bets if lo <= b["price"] < hi and b["filled"]]
    if not in_bucket:
        continue
    for rl_label, rules in [("current", current_rules), ("proposed", proposed_rules)]:
        for rlo, rhi, slip in rules:
            if rlo == lo:
                avg_price = sum(b["price"] for b in in_bucket) / len(in_bucket)
                limit = min(avg_price + slip, 0.995)
                roi = (1.0 - limit) / limit * 100
                if rl_label == "current":
                    c_roi = roi
                else:
                    p_roi = roi
                break
    print(f"{label:20s} | {c_roi:11.3f}% | {p_roi:11.3f}% | {c_roi - p_roi:9.3f}%")

# ── SECTION 4: What-if analysis ──
# If slippage were higher, would previously unfilled bets have filled?
# We can't know for sure, but we can estimate: unfilled bets with slippage=X
# could potentially fill if we raised slippage to X+0.001
print()
print("=" * 90)
print("  SECTION 4: WHAT-IF — ADDITIONAL FILLS WITH +0.001 SLIPPAGE")
print("=" * 90)
print()
print("NOTE: We cannot know if raising limit price would have resulted in fills.")
print("This estimates the MAXIMUM potential impact assuming all would fill.")
print()

# Look at unfilled bets grouped by their slippage bucket
for lo, hi, label in buckets:
    unfilled_in_bucket = [b for b in bets if lo <= b["price"] < hi and not b["filled"]]
    filled_in_bucket = [b for b in bets if lo <= b["price"] < hi and b["filled"]]
    n_unfilled = len(unfilled_in_bucket)
    n_filled = len(filled_in_bucket)
    if n_unfilled == 0 and n_filled == 0:
        continue

    # Current slippage for this bucket
    for rlo, rhi, slip in current_rules:
        if rlo == lo:
            cur_slip = slip
            break

    new_slip = cur_slip + 0.001
    avg_price_unfilled = sum(b["price"] for b in unfilled_in_bucket) / n_unfilled if n_unfilled else 0

    # If these unfilled bets had filled at price + new_slip
    additional_cost = sum(b["amount"] for b in unfilled_in_bucket)
    if avg_price_unfilled > 0:
        limit_new = min(avg_price_unfilled + new_slip, 0.995)
        additional_shares = additional_cost / limit_new
        additional_profit = additional_shares - additional_cost  # on win
        roi_new = additional_profit / additional_cost * 100 if additional_cost > 0 else 0
    else:
        additional_profit = 0
        roi_new = 0

    print(f"{label}:")
    print(f"  Current fill: {n_filled} filled, {n_unfilled} unfilled ({n_filled/(n_filled+n_unfilled)*100:.0f}% fill rate)")
    print(f"  Slippage: {cur_slip:.3f} -> {new_slip:.3f}")
    print(f"  Max additional if ALL unfilled had filled: {n_unfilled} trades, ${additional_cost:.0f} invested")
    print(f"  Max additional profit (assume all win): ${additional_profit:.2f} (ROI {roi_new:.2f}%)")
    print()

# ── SECTION 5: STALE PRICE EVENTS ──
print()
print("=" * 90)
print("  SECTION 5: STALE PRICE SKIP ANALYSIS")
print("=" * 90)
print(f"{'Title':60s} | {'Gamma':>6s} | {'CLOB':>6s} | {'Diff':>6s}")
print("-" * 85)
for s in stale_events:
    print(f"{s['title']:60s} | {s['gamma']:6.3f} | {s['clob']:6.3f} | {s['diff']:6.3f}")

print()
if stale_events:
    print(f"Total stale skips: {len(stale_events)}")
    avg_diff = sum(s["diff"] for s in stale_events) / len(stale_events)
    min_diff = min(s["diff"] for s in stale_events)
    max_diff = max(s["diff"] for s in stale_events)
    print(f"Average divergence: {avg_diff:.4f} ({avg_diff * 100:.1f}c)")
    print(f"Range: {min_diff:.4f} - {max_diff:.4f}")
    print(f"Median divergence: {sorted(s['diff'] for s in stale_events)[len(stale_events)//2]:.4f}")

    # Would any of these have been safe buys?
    print()
    print("ANALYSIS: Were these safe to buy?")
    print("If Gamma=0.98 but CLOB=0.88, the TRUE price is ~0.88.")
    print("Buying at 0.88 for a 96%+ outcome would give 12%+ ROI if it wins.")
    print("But the Gamma price (0.98) was STALE — the market already moved.")
    print("The CLOB price reflects REAL liquidity. A drop from 0.98 to 0.88")
    print("means the market is questioning the outcome — HIGHER RISK.")
    print()
    high_risk = sum(1 for s in stale_events if s["diff"] >= 0.05)
    medium_risk = sum(1 for s in stale_events if 0.03 <= s["diff"] < 0.05)
    print(f"High risk (diff >= 5c): {high_risk} events — likely active matches/events")
    print(f"Medium risk (3-5c diff): {medium_risk} events — Gamma cache lag")

# Save data for report
output = {
    "total_bets": total,
    "total_filled": total_filled,
    "fill_rate": total_filled / total * 100,
    "stale_events": stale_events,
    "stale_count": len(stale_events),
}
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slippage_backtest_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nData saved: {out_path}")
