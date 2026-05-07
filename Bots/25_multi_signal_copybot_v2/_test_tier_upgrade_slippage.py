"""Tier-upgrade slippage check tests.

Validates that the new slippage gate in main.py handle_buy's tier-upgrade
branch correctly blocks purchases where our best_ask is too far above
the player's triggering buy price.

10+ scenarios covering all MAX_SLIPPAGE_TIERS price bands + fail-safe.

Usage: py -3.12 -u -X utf8 _test_tier_upgrade_slippage.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import filters
from config import MAX_SLIPPAGE_TIERS

# ---------------------------------------------------------------
# We test the slippage decision in isolation — the exact check that
# lives in main.py tier-upgrade block. No mocking of threading/tracker —
# just the pure slippage-gate logic.
# ---------------------------------------------------------------


def evaluate_slippage(denizz_price: float, our_ask: float | None) -> str:
    """Pure port of the slippage block in main.py tier-upgrade.
    Returns 'BLOCK' | 'PASS' | 'PASS_FAILSAFE'."""
    if our_ask is None:
        # Fail-safe: skip slippage check (mirrors check_signal behavior)
        return "PASS_FAILSAFE"
    slippage = our_ask - denizz_price
    max_slip = filters.get_max_slippage(denizz_price)
    # Match check_signal: tolerance 0.0005 for float precision
    if slippage > max_slip + 0.0005:
        return "BLOCK"
    return "PASS"


# ---------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------
passed = 0
failed = 0
total = 0


def check(tid, label, denizz_px, our_ask, expected):
    global passed, failed, total
    total += 1
    actual = evaluate_slippage(denizz_px, our_ask)
    ok = actual == expected
    tag = "PASS" if ok else "FAIL"
    slip_str = "N/A" if our_ask is None else f"{our_ask - denizz_px:+.3f}"
    max_str = "" if our_ask is None else f"max={filters.get_max_slippage(denizz_px):.3f}"
    print(f"  {tag} {tid}: {label}")
    print(f"       denizz={denizz_px}  our_ask={our_ask}  slip={slip_str}  {max_str}")
    print(f"       expected={expected}  got={actual}")
    if ok:
        passed += 1
    else:
        failed += 1


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------
print("=" * 70)
print("TIER-UPGRADE SLIPPAGE CHECK — 12 scenarios")
print("=" * 70)

# Print MAX_SLIPPAGE_TIERS for reference
print("\nMAX_SLIPPAGE_TIERS (V2 config):")
for lo, hi, slip in MAX_SLIPPAGE_TIERS:
    print(f"  [{lo:.2f} - {hi:.2f}) → max slip {slip:.4f}")

print("\n--- Main cases ---")

# T1: Real-world bug repro — Trump uranium (should now BLOCK)
# denizz @ 0.165, our ask 0.222, slippage 5.7c, max for 0.10-0.20 band = 3c
check("T1", "Trump uranium Apr14 (the bug): 5.7c slippage",
      0.165, 0.222, "BLOCK")

# T2: First buy of same market (was 2c — correctly passed)
check("T2", "Trump uranium first fill: 2c slippage (OK)",
      0.220, 0.240, "PASS")

# T3: Dead-middle price tier 0.20-0.82, small slippage
check("T3", "Mid price 0.50 → ask 0.52 (2c)",
      0.50, 0.52, "PASS")

# T4: Mid price, exactly at limit
# Band 0.20-0.82 max_slip = 0.03
check("T4", "Mid price 0.50 → ask 0.53 (3c = exactly at limit)",
      0.50, 0.53, "PASS")

# T5: Mid price, just above limit
check("T5", "Mid price 0.50 → ask 0.531 (3.1c just over limit)",
      0.50, 0.531, "BLOCK")

# T6: Low price band 0.00-0.10, tight limit 2c
check("T6", "Cheap 0.05 → ask 0.08 (3c) — should BLOCK (max 2c)",
      0.05, 0.08, "BLOCK")

# T7: Low price band, acceptable 1c
check("T7", "Cheap 0.05 → ask 0.06 (1c)",
      0.05, 0.06, "PASS")

# T8: High price band 0.88-0.92, tight 1.5c
check("T8", "High 0.90 → ask 0.92 (2c) — should BLOCK (max 1.5c)",
      0.90, 0.92, "BLOCK")

# T9: High price, within 1.5c
check("T9", "High 0.90 → ask 0.911 (1.1c)",
      0.90, 0.911, "PASS")

# T10: Very high price 0.97-0.98, super tight 0.35c
check("T10", "V.high 0.975 → ask 0.980 (0.5c) — should BLOCK (max 0.35c)",
      0.975, 0.980, "BLOCK")

# T11: ask BELOW denizz (better fill than him) — always pass
check("T11", "Better fill: denizz 0.50, ask 0.48 (negative slippage)",
      0.50, 0.48, "PASS")

# T12: Same price (0 slippage)
check("T12", "Zero slippage: denizz 0.30, ask 0.30",
      0.30, 0.30, "PASS")

# T13: Orderbook unavailable (RPC error / CLOB down)
# Must be PASS_FAILSAFE (symmetric with check_signal behavior)
check("T13", "Orderbook unavailable → PASS_FAILSAFE",
      0.50, None, "PASS_FAILSAFE")

# T14: Boundary between bands — price at 0.82 (moves from 3c to 2c limit)
# 0.82-0.88 band max_slip = 2c. Our denizz price 0.82 itself falls in 0.82-0.88.
check("T14", "Boundary 0.82 → ask 0.83 (1c, max 2c in 0.82-0.88)",
      0.82, 0.83, "PASS")

# T15: Boundary price with slippage over the tighter limit
check("T15", "Boundary 0.82 → ask 0.845 (2.5c over max 2c)",
      0.82, 0.845, "BLOCK")

# ---------------------------------------------------------------
# Report
# ---------------------------------------------------------------
print(f"\n{'=' * 70}")
print(f"RESULTS: {passed}/{total} PASS, {failed} FAIL")
print(f"{'=' * 70}")

if failed:
    sys.exit(1)
print("ALL TESTS PASSED ✓")
sys.exit(0)
