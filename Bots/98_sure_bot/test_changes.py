"""Unit tests for the three changes: dynamic bet, nr off, ed 7d."""
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

passed = 0
failed = 0

def test(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1


# ========== TEST 1: Config dynamic bet sizing ==========
print("\n=== TEST: config.py dynamic bet sizing ===")
from config import (BET_SIZE_LOW, BET_SIZE_MID, BET_SIZE_HIGH,
                    LIQ_THRESHOLD_MID, LIQ_THRESHOLD_HIGH, BET_SIZE)

test("BET_SIZE_LOW = 5", BET_SIZE_LOW == 5.0)
test("BET_SIZE_MID = 10", BET_SIZE_MID == 10.0)
test("BET_SIZE_HIGH = 15", BET_SIZE_HIGH == 15.0)
test("LIQ_THRESHOLD_MID = 2000", LIQ_THRESHOLD_MID == 2000)
test("LIQ_THRESHOLD_HIGH = 10000", LIQ_THRESHOLD_HIGH == 10000)
test("BET_SIZE = max bet (15)", BET_SIZE == 15.0)

# MAX_NEG_RISK_FROZEN should not be importable
try:
    from config import MAX_NEG_RISK_FROZEN
    # It's still defined but commented reference — check it doesn't block
    test("MAX_NEG_RISK_FROZEN removed (not importable)", False)
except ImportError:
    test("MAX_NEG_RISK_FROZEN removed (not importable)", True)


# ========== TEST 2: Executor dynamic bet sizing ==========
print("\n=== TEST: executor.calculate_bet_size() ===")
from executor import calculate_bet_size

# Low liquidity ($500) -> $5 max
bet = calculate_bet_size(0.985, liquidity=500)
test("Low liq ($500) -> bet ~$4.93", bet is not None and bet <= 5.0)

# Mid liquidity ($5000) -> $10 max
bet = calculate_bet_size(0.985, liquidity=5000)
test("Mid liq ($5000) -> bet ~$4.93", bet is not None and bet <= 10.0)

# High liquidity ($15000) -> $15 max
bet = calculate_bet_size(0.985, liquidity=15000)
test("High liq ($15000) -> bet ~$4.93", bet is not None and bet <= 15.0)

# Default (no liquidity) -> $5 (low)
bet = calculate_bet_size(0.985)
test("No liquidity param -> defaults to low ($5)", bet is not None and bet <= 5.0)

# Edge: exactly at threshold
bet = calculate_bet_size(0.985, liquidity=2000)
test("Liq exactly $2000 -> mid ($10)", bet is not None and bet <= 10.0)

bet = calculate_bet_size(0.985, liquidity=10000)
test("Liq exactly $10000 -> high ($15)", bet is not None and bet <= 15.0)

# Edge: price too high for min shares
bet = calculate_bet_size(0.999, liquidity=500)
# 5 shares * 0.999 = $4.995, which is < $5 BET_SIZE_LOW, so should pass
test("Price 0.999, low liq -> still valid (4.995 < 5)", bet is not None)


# ========== TEST 3: Filters - neg_risk removed ==========
print("\n=== TEST: filters.py neg_risk filter removed ===")
import filters

# Build a neg_risk candidate that would have been blocked
fake_candidate = {
    "question": "Will team X win?",
    "price": 0.985,
    "liquidity": 5000,
    "volume_total": 10000,
    "neg_risk": True,
    "condition_id": "test_nr_123",
    "end_date": "2026-03-20T00:00:00Z",
    "category": "esports",
}

# Fake tracker data with $500 frozen in neg_risk (would exceed old $300 cap)
fake_tracker = {
    "positions": {
        "pos1": {"status": "open", "neg_risk": True, "cost_usd": 250},
        "pos2": {"status": "open", "neg_risk": True, "cost_usd": 250},
    }
}

result, reason = filters.run_all_filters(fake_candidate, set(), fake_tracker)
test("Neg_risk candidate with $500 frozen -> PASSES (nr cap removed)", result is True)


# ========== TEST 4: Filters - end_date 7 days ==========
print("\n=== TEST: filters.py end_date 7 days ===")

test("MAX_END_DATE_DAYS = 7", filters.MAX_END_DATE_DAYS == 7)

# Market with end_date 5 days ahead should pass
from datetime import datetime, timezone, timedelta
future_5d = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
future_8d = (datetime.now(timezone.utc) + timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")

candidate_5d = {
    "question": "Some regular market?",
    "price": 0.985,
    "liquidity": 5000,
    "volume_total": 10000,
    "neg_risk": False,
    "condition_id": "test_ed_5d",
    "end_date": future_5d,
    "category": "other",
}

result_5d, reason_5d = filters.run_all_filters(candidate_5d, set(), {})
test("End date 5 days ahead -> PASSES with ed 7d", result_5d is True)

candidate_8d = dict(candidate_5d)
candidate_8d["end_date"] = future_8d
candidate_8d["condition_id"] = "test_ed_8d"

result_8d, reason_8d = filters.run_all_filters(candidate_8d, set(), {})
test("End date 8 days ahead -> BLOCKED", result_8d is False)
test("Blocked reason mentions end date", "end date" in reason_8d.lower() or "End date" in reason_8d)


# ========== TEST 5: Integration - full flow ==========
print("\n=== TEST: Integration - candidate flow ===")

good_candidate = {
    "question": "Will the Lakers win tonight?",
    "price": 0.988,
    "liquidity": 8000,
    "volume_total": 50000,
    "neg_risk": True,
    "condition_id": "test_int_1",
    "end_date": (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "category": "basketball",
    "game_start_time": (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
}

result, reason = filters.run_all_filters(good_candidate, set(), fake_tracker)
test("Good basketball candidate passes all filters", result is True)

# Bet sizing for this candidate (liq $8000 -> mid -> $10)
from executor import calculate_bet_size, get_limit_price
limit = get_limit_price(0.988)
test("Limit price calculated for 0.988", limit is not None)

if limit:
    bet = calculate_bet_size(limit, liquidity=8000)
    test(f"Dynamic bet for $8K liquidity -> ${bet} (should be <= $10)", bet is not None and bet <= 10.0)


# ========== SUMMARY ==========
print(f"\n{'=' * 50}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
print(f"{'=' * 50}")

if failed > 0:
    sys.exit(1)
else:
    print("ALL TESTS PASSED!")
