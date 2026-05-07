"""Audit bot.log for the last 7 days: what % of denizz SELL events resulted
in an actual follow-sell (or a legitimate SKIP)?

Parses bot.log, grouping lines by approximate event boundaries. For each
[MONITOR:denizz] SELL: ... line we look at the next ~20 log lines and
classify the outcome:

  - follow_sell_executed  : we reached "Following denizz: N sh" + "SELL order placed"
  - skip_duplicate        : deduped (60s window)
  - skip_phantom          : cached==onchain or INCREASED
  - skip_cross_player     : SKIP: denizz sold but position opened by ...
  - skip_dust             : SKIP dust sell (tier 0)
  - skip_no_position      : no matched position in tracker (silent)
  - skip_price_gap        : our price X% worse than denizz
  - skip_unknown          : no follow-up log line within N seconds

Then compute response rate = (follow_sell_executed) / (total - skip_no_position)
because "no position" is correct behavior (we don't hold it).

Save a per-market breakdown.
"""
import io
import os
import re
import sys
import json
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BOT_DIR, "bot.log")

# Timestamp format: 2026-04-17 18:05:37
TS_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
SELL_DETECT_RE = re.compile(r'\[MONITOR:denizz\] SELL: (.+?) @ ([\d.]+)')

cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)

def parse_ts(line):
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None

# Load log
print(f"Reading {LOG_PATH} ...")
with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
print(f"Total lines: {len(lines):,}")

# Find denizz SELL detections in last 7 days
events = []
for i, line in enumerate(lines):
    if "[MONITOR:denizz] SELL:" not in line:
        continue
    ts = parse_ts(line)
    if ts is None or ts < cutoff_7d:
        continue
    m = SELL_DETECT_RE.search(line)
    if not m:
        continue
    market_and_outcome = m.group(1).strip()
    price = float(m.group(2))
    events.append({
        "line_idx": i,
        "ts": ts,
        "market": market_and_outcome,
        "price": price,
    })

print(f"Denizz SELL detections in last 7 days: {len(events)}")

# For each event, look at the next ~40 lines or until next [MONITOR:...] SELL/BUY
def classify_event(ev):
    start = ev["line_idx"]
    end = min(start + 40, len(lines))
    window = [l.rstrip() for l in lines[start:end]]

    market = ev["market"]
    # Shortened key used in [EXIT] log lines (first 50 chars of title)
    # and in "[MAIN:denizz] SELL detected: <title>"
    market_prefix_50 = market[:50]   # approximate

    outcome = "skip_unknown"
    details = []
    for l in window[1:]:  # skip the SELL detection line itself
        if "[MONITOR:" in l and ("SELL:" in l or "BUY:" in l):
            # New event started — stop scanning
            break
        if "[EXIT] SKIP duplicate sell event" in l:
            outcome = "skip_duplicate"
            details.append(l)
            break
        if "[EXIT] on-chain truth: denizz" in l:
            details.append(l)
            # Continue: we need to see whether a "Following denizz" or SKIP follows
            continue
        if "[EXIT] PHANTOM" in l:
            outcome = "skip_phantom"
            details.append(l)
            break
        if "[EXIT] RPC FAILED" in l:
            outcome = "skip_rpc_failure"
            details.append(l)
            break
        if "[EXIT] SKIP: missing wallet" in l:
            outcome = "skip_missing_wallet"
            break
        if "[EXIT] SKIP:" in l and ("sold but position was opened by" in l):
            outcome = "skip_cross_player"
            details.append(l)
            break
        if "[EXIT] SKIP denizz dust sell" in l:
            outcome = "skip_dust_tier"
            details.append(l)
            break
        if "[EXIT] SKIP:" in l and "price" in l and "worse than denizz" in l:
            outcome = "skip_price_gap"
            details.append(l)
            break
        if "[EXIT] Following denizz:" in l:
            outcome = "follow_attempted"
            details.append(l)
            # Check further lines for actual order placement
            continue
        if "[EXIT] SELL order placed:" in l:
            outcome = "follow_sell_executed"
            details.append(l)
            break
        if "[EXIT] Sell order failed" in l:
            outcome = "follow_sell_failed"
            details.append(l)
            break
        if "[EXIT] onchain balance too small" in l:
            outcome = "follow_skip_onchain_empty"
            details.append(l)
            break
        if "[EXIT] SOLD:" in l:
            outcome = "follow_sell_executed"
            details.append(l)
            break

    # If we saw "on-chain truth" but nothing followed, that's one of 3 silent
    # returns: matched_pos is None / our_shares < 0.5 / orderbook fetch failed.
    # All 3 are benign; classify as "silent_after_onchain_ok".
    if outcome == "skip_unknown":
        if any("on-chain truth: denizz" in d for d in details):
            outcome = "silent_after_onchain_ok"

    return outcome, details


classifications = Counter()
details_by_outcome = defaultdict(list)
per_market = defaultdict(Counter)

for ev in events:
    outcome, dets = classify_event(ev)
    classifications[outcome] += 1
    details_by_outcome[outcome].append({
        "ts": ev["ts"].isoformat(),
        "market": ev["market"],
        "price": ev["price"],
        "dets": dets[:2],
    })
    # Simplified market name (before " Yes"/" No")
    m = ev["market"].rsplit(" ", 1)[0] if ev["market"].endswith((" Yes", " No")) else ev["market"]
    per_market[m[:45]][outcome] += 1

print("\n" + "=" * 70)
print("BOT.LOG AUDIT — denizz SELL events in last 7 days")
print("=" * 70)
print(f"\nTotal events: {len(events)}")
print("\nClassification:")
for cls, n in classifications.most_common():
    print(f"  {cls:<32} : {n:5d}  ({n/len(events):.1%})")

# Response rate
executed = classifications.get("follow_sell_executed", 0)
failed = classifications.get("follow_sell_failed", 0)
skip_no_pos = classifications.get("skip_no_position_match", 0)
skip_dup = classifications.get("skip_duplicate", 0)
skip_dust = classifications.get("skip_dust_tier", 0)
skip_phantom = classifications.get("skip_phantom", 0)
skip_unknown = classifications.get("skip_unknown", 0)
skip_onchain_empty = classifications.get("follow_skip_onchain_empty", 0)

total = len(events)
relevant = total - skip_no_pos - skip_phantom - skip_dup
rate = executed / relevant * 100 if relevant else 0
print(f"\nActionable events (excluded: no-position, dedup, phantom): {relevant}")
print(f"  → Executed: {executed} ({rate:.1f}%)")
print(f"  → Failed / skipped due to tiered rules: {relevant - executed}")

# Unknown events deserve investigation
print(f"\n'skip_unknown' events ({skip_unknown}): lines not matched by any heuristic")
print("Sample of 10:")
for sample in details_by_outcome["skip_unknown"][:10]:
    print(f"  [{sample['ts']}] {sample['market'][:55]}")
    for d in sample["dets"][:2]:
        print(f"    > {d[:130]}")

# Per-market breakdown for most-active markets
print("\nTop 10 markets by denizz SELL count:")
market_totals = sorted(per_market.items(),
                       key=lambda kv: -sum(kv[1].values()))[:10]
for market, cls in market_totals:
    total_m = sum(cls.values())
    exec_m = cls.get("follow_sell_executed", 0)
    print(f"\n  {market[:60]} — {total_m} events")
    for c, n in cls.most_common():
        print(f"      {c:<32} : {n}")

# Save full audit dump
out = os.path.join(BOT_DIR, "_analytics", "data", "2026-04-17_bot_log_audit_sells.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({
        "total_events": total,
        "classifications": dict(classifications),
        "response_rate_on_actionable": rate,
        "per_market": {m: dict(c) for m, c in per_market.items()},
        "unknown_samples": [
            {"ts": s["ts"], "market": s["market"], "dets": s["dets"]}
            for s in details_by_outcome["skip_unknown"][:30]
        ],
    }, f, indent=2, ensure_ascii=False)
print(f"\nSaved → {out}")
