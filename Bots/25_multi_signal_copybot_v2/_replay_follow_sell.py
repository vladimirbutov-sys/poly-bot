"""Replay follow-sell logic against denizz activity history.

For each LARGE sell (>=500 shares OR >=$300 usdcSize) in the
`denizz_activity_ALL.json` dump, simulate what would happen if the monitor
caught the event and passed it to `exit_manager.handle_player_sell`.

We track for each event:
  - monitor_would_fire  : would the dedupe key catch this (given prior history)
  - peak_size_at_event  : running peak up to that point
  - prior_size          : player size BEFORE this sell
  - post_size           : player size AFTER this sell
  - sold_pct            : delta / prior
  - correct_tier_frac   : what FOLLOW_SELL_TIERS would apply
  - would_skip_reason   : "dust" / "price_gap" / "cross_player" / None

This is pure offline analysis — no network, no tracker, no orders.
"""
import io
import os
import sys
import json
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

ACTIVITY_PATH = os.path.join(BOT_DIR, "_analytics", "data", "denizz_activity_ALL.json")

with open(ACTIVITY_PATH, "r", encoding="utf-8") as f:
    activity = json.load(f)

print(f"Loaded {len(activity)} events from {ACTIVITY_PATH}")

# Sort chronologically (ascending)
activity.sort(key=lambda e: int(e.get("timestamp", 0) or 0))

# ------------------------------------------------------------------
# Build per-(cid, asset) running balance so we can simulate peak_size
# and sold_pct-from-prior exactly like exit_manager does.
# ------------------------------------------------------------------
running = defaultdict(float)      # (cid, asset) -> current size
peak = defaultdict(float)         # (cid, asset) -> running peak

def _on_event(e, running, peak):
    """Update running balance. Returns (prior, post, delta)."""
    ev_type = (e.get("type") or "").upper()
    cid = e.get("conditionId", "")
    asset = str(e.get("asset", ""))
    size = float(e.get("size", 0) or 0)
    side = (e.get("side") or "").upper()
    key = (cid, asset)
    prior = running[key]
    delta = 0.0
    if ev_type == "TRADE":
        if side == "BUY":
            delta = size
            running[key] = prior + size
        elif side == "SELL":
            delta = -size
            running[key] = max(0.0, prior - size)
    elif ev_type == "MERGE":
        delta = -size
        running[key] = max(0.0, prior - size)
    elif ev_type == "SPLIT":
        delta = size
        running[key] = prior + size
    elif ev_type == "REDEEM":
        delta = -prior
        running[key] = 0.0
    post = running[key]
    peak[key] = max(peak[key], post)
    return prior, post, delta


# ------------------------------------------------------------------
# Decision matrix (copied from exit_manager without mutation)
# ------------------------------------------------------------------
from config import FOLLOW_SELL_TIERS_PROFIT, FOLLOW_SELL_TIERS_LOSS

def follow_sell_fraction(sold_pct, we_in_profit):
    tiers = FOLLOW_SELL_TIERS_PROFIT if we_in_profit else FOLLOW_SELL_TIERS_LOSS
    for lo, hi, frac in tiers:
        if lo <= sold_pct < hi:
            return frac
    return 0.0


# ------------------------------------------------------------------
# Walk the history, tagging each LARGE sell
# ------------------------------------------------------------------
LARGE_SIZE_THRESHOLD = 500.0    # shares
LARGE_USD_THRESHOLD = 300.0     # usdc

large_sells = []
all_sells_count = 0
dedup_seen = set()              # monitor dedupe keys (with size+price)
dedup_seen_old = set()          # documentary: old broken key
dedup_collisions_new = 0
dedup_collisions_old = 0

for e in activity:
    ev_type = (e.get("type") or "").upper()
    prior, post, delta = _on_event(e, running, peak)

    if ev_type != "TRADE":
        continue
    side = (e.get("side") or "").upper()
    if side != "SELL":
        continue
    all_sells_count += 1

    size = abs(float(e.get("size", 0) or 0))
    usdc = float(e.get("usdcSize", 0) or 0)
    price = float(e.get("price", 0) or 0)
    is_large = (size >= LARGE_SIZE_THRESHOLD) or (usdc >= LARGE_USD_THRESHOLD)
    if not is_large:
        continue

    # === monitor dedupe key evaluation ===
    tx = e.get("transactionHash", "") or ""
    cond = e.get("conditionId", "") or ""
    ts = str(e.get("timestamp", ""))
    new_key = f"{tx}_{cond}_{ts}_{size}_{price}"
    old_key = f"{tx}_{cond}_{ts}"
    new_would_collide = new_key in dedup_seen
    old_would_collide = old_key in dedup_seen_old
    if new_would_collide:
        dedup_collisions_new += 1
    if old_would_collide:
        dedup_collisions_old += 1
    dedup_seen.add(new_key)
    dedup_seen_old.add(old_key)

    # === compute sold_pct as exit_manager would ===
    cid = e.get("conditionId", "")
    asset = str(e.get("asset", ""))
    k = (cid, asset)
    # In live code: sold_pct = delta / cached_size, where cached_size ≈ prior
    sold_pct = (prior - post) / prior if prior > 0 else 0.0
    peak_size = peak[k]

    # For replay: we don't know "our" position; we simulate both profit/loss paths.
    frac_profit = follow_sell_fraction(sold_pct, True)
    frac_loss = follow_sell_fraction(sold_pct, False)

    # Classify outcome the code WOULD take if we held a matching position:
    # - If sold_pct < dust threshold for both tables → skip
    # - Else a follow-sell would fire (subject to dedupe)
    skip_reason = None
    if frac_profit == 0 and frac_loss == 0:
        skip_reason = "dust_both_tables"
    elif new_would_collide:
        skip_reason = "dedupe_collision_new"

    large_sells.append({
        "ts": int(e.get("timestamp", 0) or 0),
        "dt": datetime.fromtimestamp(int(e.get("timestamp", 0) or 0), tz=timezone.utc).isoformat(),
        "title": e.get("title", ""),
        "cond": cond,
        "asset": asset,
        "size": size,
        "price": price,
        "usdc": usdc,
        "prior": prior,
        "post": post,
        "sold_pct": sold_pct,
        "peak_at_event": peak_size,
        "sold_pct_from_peak": (prior - post) / peak_size if peak_size > 0 else 0.0,
        "frac_profit": frac_profit,
        "frac_loss": frac_loss,
        "new_key_collision": new_would_collide,
        "old_key_collision": old_would_collide,
        "skip_reason": skip_reason,
        "tx": tx,
    })


# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------
print("\n" + "=" * 70)
print("REPLAY RESULTS — follow-sell coverage on denizz SELLs (historical)")
print("=" * 70)

print(f"\nAll TRADE/SELL events in history : {all_sells_count}")
print(f"LARGE (>=500 sh OR >=$300)       : {len(large_sells)}")

from collections import Counter
reasons = Counter(s["skip_reason"] for s in large_sells)
print("\nDisposition of LARGE sells:")
for r, n in reasons.most_common():
    label = r or "would_fire_correctly"
    print(f"  {label:<30} : {n}  ({n/len(large_sells):.1%})")

# Now the core numbers
would_fire = sum(1 for s in large_sells if s["skip_reason"] is None)
pct_fire = would_fire / len(large_sells) * 100 if large_sells else 0
print(f"\nCORE NUMBER: {would_fire}/{len(large_sells)} ({pct_fire:.1f}%) large sells would trigger follow-sell")

# Monitor dedupe collision analysis
print(f"\nMonitor dedupe collisions:")
print(f"  NEW key (tx,cond,ts,size,price) : {dedup_collisions_new} collisions out of {len(large_sells)}")
print(f"  OLD key (tx,cond,ts)            : {dedup_collisions_old} collisions (these would be MISSED without fix)")

# If the old key would have missed sells that the new key catches, that's the
# value of the 2026-04-17 fix.
print(f"  Fix impact: new key recovers {dedup_collisions_old - dedup_collisions_new} previously-lost sells")

# Dust analysis
dust_count = sum(1 for s in large_sells if s["skip_reason"] == "dust_both_tables")
print(f"\nDust ({dust_count}) — sold_pct < 10% (profit) AND < 20% (loss):")
# Show the distribution of sold_pct on dust
dust_pcts = [s["sold_pct"] for s in large_sells if s["skip_reason"] == "dust_both_tables"]
if dust_pcts:
    print(f"  sold_pct: min={min(dust_pcts):.1%}  median={sorted(dust_pcts)[len(dust_pcts)//2]:.1%}  max={max(dust_pcts):.1%}")

# Large-dust events: check how many are >=500 sh but <10% of denizz position
# (these would correctly be ignored as hedge-noise)
huge_dust = [s for s in large_sells
             if s["skip_reason"] == "dust_both_tables" and s["size"] >= 1000]
print(f"  Very large dust (>=1000 sh but sold_pct<10%): {len(huge_dust)}")

# ------------------------------------------------------------------
# sold_pct distribution across all LARGE sells
# ------------------------------------------------------------------
print("\nsold_pct distribution across all LARGE sells (from PRIOR):")
buckets = [
    (0.00, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.30),
    (0.30, 0.50), (0.50, 0.70), (0.70, 0.90), (0.90, 1.01)
]
for lo, hi in buckets:
    n = sum(1 for s in large_sells if lo <= s["sold_pct"] < hi)
    print(f"  {lo:.0%}-{hi:.0%} : {n:4d} ({n/len(large_sells):.1%})")

# ------------------------------------------------------------------
# Peak-based vs delta-based discrepancy
# (The code COMMENT says "peak-based" but the actual implementation uses
# delta/cached which is prior-based. This test verifies that observation.)
# ------------------------------------------------------------------
print("\nPeak-based vs prior-based (sold_pct_from_peak vs sold_pct):")
peak_different = [s for s in large_sells
                  if abs(s["sold_pct"] - s["sold_pct_from_peak"]) > 0.05]
print(f"  Events with >5% discrepancy: {len(peak_different)} / {len(large_sells)}")
print("  (When denizz trimmed then topped up, peak > prior. Code uses prior-based.)")

# ------------------------------------------------------------------
# Save full dump to _analytics/data
# ------------------------------------------------------------------
out_path = os.path.join(BOT_DIR, "_analytics", "data",
                         "2026-04-17_replay_follow_sell.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "total_events": len(activity),
        "total_sells": all_sells_count,
        "large_sells_count": len(large_sells),
        "would_fire_correctly": would_fire,
        "pct_fire": pct_fire,
        "dedup_collisions_new_key": dedup_collisions_new,
        "dedup_collisions_old_key": dedup_collisions_old,
        "fix_impact_events_recovered": dedup_collisions_old - dedup_collisions_new,
        "dust_count": dust_count,
        "events": large_sells[:100],   # first 100 as sample
    }, f, indent=2, ensure_ascii=False)
print(f"\nSaved replay dump → {out_path}")

# Failure threshold: if >5% of large sells are missed (skip_reason != dust), block
missed_not_dust = [s for s in large_sells
                   if s["skip_reason"] is not None
                   and s["skip_reason"] != "dust_both_tables"]
print(f"\nMissed-not-dust: {len(missed_not_dust)} / {len(large_sells)} ({len(missed_not_dust)/len(large_sells):.1%})")
if len(missed_not_dust) > 0.05 * len(large_sells):
    print("*** BLOCKER: >5% of large sells would be missed ***")
    sys.exit(1)
else:
    print("Threshold OK — <5% of large sells missed due to non-dust reasons")
