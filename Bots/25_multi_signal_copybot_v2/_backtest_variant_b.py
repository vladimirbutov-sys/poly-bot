"""Backtest comparison: variant A vs B over the cached 90-day denizz BUY history.

This is a *signal-level* backtest — for each historical denizz BUY we ask:
  "Would variant B let this signal through?"

We use denizz's executed entry price as a proxy for live best ask, since the
backtest cache doesn't contain historical orderbooks. In practice these
differ by at most a few cents (he typically takes the ask), so the
classification is faithful.

Reports:
  • Total BUY signals in 90d, by player
  • Filtered out by B: count, $ size, avg price
  • Passed by B: count, $ size, avg price
  • Distribution by 10c price buckets
  • Top markets blocked / passed

For full P&L impact, use _backtest_denizz_90d.py with the patch applied
(it'll re-fetch market data, takes ~15min). This script is for quick
classification only.
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import config

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "_analytics", "data")
TRADES_FILE = os.path.join(DATA_DIR, "denizz_trades_90d.json")

FLOOR = float(config.VARIANT_B_PRICE_FLOOR)
CEIL = float(config.VARIANT_B_PRICE_CEIL)


def load_trades() -> list[dict]:
    if not os.path.exists(TRADES_FILE):
        print(f"ERROR: cache file not found: {TRADES_FILE}")
        print("Run _backtest_denizz_90d.py once to populate the cache.")
        sys.exit(1)
    with open(TRADES_FILE, encoding="utf-8") as f:
        return json.load(f)


def in_band(price: float) -> bool:
    return FLOOR <= price <= CEIL


def bucketize(price: float) -> str:
    """Return a 10c bucket label like '0.40-0.50'."""
    edges = [0.0, 0.10, 0.20, 0.30, 0.40, 0.45, 0.50, 0.60, 0.70,
             0.80, 0.90, 0.95, 0.99, 1.01]
    for lo, hi in zip(edges, edges[1:]):
        if lo <= price < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "?"


def main() -> int:
    trades = load_trades()
    print(f"Loaded {len(trades)} cached denizz trades (90d window)")
    print(f"Variant B band: [{FLOOR:.2f}, {CEIL:.2f}]\n")

    buys = [t for t in trades if (t.get("side") or "").upper() == "BUY"]
    sells = [t for t in trades if (t.get("side") or "").upper() == "SELL"]
    print(f"BUY events:  {len(buys)}")
    print(f"SELL events: {len(sells)} (not affected by variant filter)\n")

    blocked = []
    passed = []
    for t in buys:
        try:
            price = float(t.get("price") or 0)
            size = float(t.get("size") or 0)
        except (ValueError, TypeError):
            continue
        if price <= 0 or size <= 0:
            continue
        usd = size * price
        rec = {
            "title": t.get("title", "")[:60] or "<unknown>",
            "price": price,
            "usd": usd,
            "ts": int(t.get("timestamp") or 0),
        }
        if in_band(price):
            passed.append(rec)
        else:
            blocked.append(rec)

    n_buy = len(blocked) + len(passed)
    if n_buy == 0:
        print("No valid BUY events to classify.")
        return 0

    blocked_usd = sum(r["usd"] for r in blocked)
    passed_usd = sum(r["usd"] for r in passed)
    total_usd = blocked_usd + passed_usd

    pct_block_n = 100.0 * len(blocked) / n_buy
    pct_pass_n = 100.0 * len(passed) / n_buy
    pct_block_usd = 100.0 * blocked_usd / total_usd if total_usd > 0 else 0.0
    pct_pass_usd = 100.0 * passed_usd / total_usd if total_usd > 0 else 0.0

    print("=" * 70)
    print("VARIANT B IMPACT (signal-level, 90d)")
    print("=" * 70)
    fmt = "  {:<10} {:>8} {:>10} {:>14} {:>10}"
    print(fmt.format("group", "count", "% count", "USD total", "% USD"))
    print(fmt.format("-" * 10, "-" * 8, "-" * 10, "-" * 14, "-" * 10))
    print(fmt.format(
        "blocked", len(blocked), f"{pct_block_n:.1f}%",
        f"${blocked_usd:,.0f}", f"{pct_block_usd:.1f}%"))
    print(fmt.format(
        "passed", len(passed), f"{pct_pass_n:.1f}%",
        f"${passed_usd:,.0f}", f"{pct_pass_usd:.1f}%"))
    print(fmt.format(
        "TOTAL", n_buy, "100.0%",
        f"${total_usd:,.0f}", "100.0%"))
    print()

    if blocked:
        avg_block_price = sum(r["price"] for r in blocked) / len(blocked)
        avg_block_size = blocked_usd / len(blocked)
        print(f"  blocked avg price: ${avg_block_price:.4f}  "
              f"avg size: ${avg_block_size:,.0f}")
    if passed:
        avg_pass_price = sum(r["price"] for r in passed) / len(passed)
        avg_pass_size = passed_usd / len(passed)
        print(f"  passed  avg price: ${avg_pass_price:.4f}  "
              f"avg size: ${avg_pass_size:,.0f}")
    print()

    # ---- price-bucket distribution ----
    print("=" * 70)
    print("BUY EVENT DISTRIBUTION BY PRICE BUCKET")
    print("=" * 70)
    buckets: dict[str, dict] = defaultdict(lambda: {"n": 0, "usd": 0.0})
    for r in blocked + passed:
        b = bucketize(r["price"])
        buckets[b]["n"] += 1
        buckets[b]["usd"] += r["usd"]

    fmt2 = "  {:<14} {:>8} {:>14}  {}"
    print(fmt2.format("bucket", "count", "USD total", "B verdict"))
    print(fmt2.format("-" * 14, "-" * 8, "-" * 14, "-" * 10))
    for label in sorted(buckets.keys()):
        n = buckets[label]["n"]
        usd = buckets[label]["usd"]
        # bucket lo
        lo = float(label.split("-")[0])
        hi_str = label.split("-")[1]
        hi = float(hi_str)
        # bucket fully inside band?
        if lo >= FLOOR and hi <= CEIL + 0.0001:
            verdict = "PASS"
        elif hi <= FLOOR or lo > CEIL:
            verdict = "BLOCK"
        else:
            verdict = "MIXED"
        print(fmt2.format(label, n, f"${usd:,.0f}", verdict))
    print()

    # ---- top 10 blocked markets ----
    print("=" * 70)
    print("TOP 10 BLOCKED MARKETS BY $ SIZE (variant B would skip these)")
    print("=" * 70)
    by_market_blocked: dict[str, dict] = defaultdict(lambda: {"n": 0, "usd": 0.0, "prices": []})
    for r in blocked:
        m = by_market_blocked[r["title"]]
        m["n"] += 1
        m["usd"] += r["usd"]
        m["prices"].append(r["price"])
    top_blocked = sorted(by_market_blocked.items(), key=lambda kv: -kv[1]["usd"])[:10]
    for title, info in top_blocked:
        avg_p = sum(info["prices"]) / len(info["prices"])
        print(f"  ${info['usd']:>9,.0f}  n={info['n']:>3}  avg=${avg_p:.3f}  | {title}")
    print()

    print("=" * 70)
    print("TOP 10 PASSED MARKETS BY $ SIZE (variant B would still take)")
    print("=" * 70)
    by_market_passed: dict[str, dict] = defaultdict(lambda: {"n": 0, "usd": 0.0, "prices": []})
    for r in passed:
        m = by_market_passed[r["title"]]
        m["n"] += 1
        m["usd"] += r["usd"]
        m["prices"].append(r["price"])
    top_passed = sorted(by_market_passed.items(), key=lambda kv: -kv[1]["usd"])[:10]
    for title, info in top_passed:
        avg_p = sum(info["prices"]) / len(info["prices"])
        print(f"  ${info['usd']:>9,.0f}  n={info['n']:>3}  avg=${avg_p:.3f}  | {title}")
    print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Variant B drops {len(blocked)}/{n_buy} = {pct_block_n:.1f}% of BUY signals")
    print(f"  Variant B drops ${blocked_usd:,.0f} of ${total_usd:,.0f} = {pct_block_usd:.1f}% of $ volume")
    print(f"  Variant B keeps {len(passed)} signals avg ${avg_pass_size:,.0f} each, "
          f"avg price ${avg_pass_price:.3f}" if passed else "")
    print()
    print("  NOTE: This is signal classification only. To assess actual P&L impact,")
    print("        full simulation is required. See _backtest_denizz_90d.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
