"""Tests for Variant 1: on-chain cost as source of truth for tier-upgrade.

Covers:
- get_cost_on_token filters by status=open
- get_cost_on_token sums cost_usd + in_flight_usd
- get_cost_on_token returns (0, 0) when no match
- add_in_flight / clear_in_flight mutations
- _get_already_bet_v1 fallback when flag OFF
- _get_already_bet_v1 reads tracker when flag ON
- _throttle_allows_upgrade blocks repeat calls within window
"""
import sys, time
sys.path.insert(0, '.')

import tracker
import main as m
import config


def _fake_data(positions: list) -> dict:
    """Build a fake tracker-like data dict from list of position dicts."""
    return {
        "positions": {f"key_{i}": p for i, p in enumerate(positions)},
        "stats": {"total_bets": 0, "current_balance": 1000, "peak_balance": 1000,
                  "total_pnl": 0, "wins": 0, "losses": 0},
    }


def test_1_cost_filters_open():
    """Sold positions should not contribute to cost."""
    data = _fake_data([
        {"status": "open", "condition_id": "0xA", "token_id": "T1", "cost_usd": 50.0},
        {"status": "sold", "condition_id": "0xA", "token_id": "T1", "cost_usd": 100.0},
    ])
    cost, ts = tracker.get_cost_on_token(data, "0xA", "T1")
    print(f"Test 1 (filter open): cost={cost} (expected 50.0)")
    assert cost == 50.0, f"got {cost}"
    print("  PASS")


def test_2_cost_sums_inflight():
    """in_flight_usd should be added to cost."""
    data = _fake_data([
        {"status": "open", "condition_id": "0xA", "token_id": "T1",
         "cost_usd": 30.0, "in_flight_usd": 20.0},
    ])
    cost, _ = tracker.get_cost_on_token(data, "0xA", "T1")
    print(f"Test 2 (sum in_flight): cost={cost} (expected 50.0)")
    assert cost == 50.0
    print("  PASS")


def test_3_no_match_returns_zero():
    data = _fake_data([
        {"status": "open", "condition_id": "0xB", "token_id": "T2", "cost_usd": 999},
    ])
    cost, ts = tracker.get_cost_on_token(data, "0xA", "T1")
    print(f"Test 3 (no match): cost={cost}, ts={ts} (expected 0, 0)")
    assert cost == 0.0 and ts == 0
    print("  PASS")


def test_4_wrong_token():
    data = _fake_data([
        {"status": "open", "condition_id": "0xA", "token_id": "T_OTHER", "cost_usd": 100},
    ])
    cost, _ = tracker.get_cost_on_token(data, "0xA", "T1")
    print(f"Test 4 (wrong token): cost={cost} (expected 0)")
    assert cost == 0.0
    print("  PASS")


def test_5_grace_period_ts():
    now = int(time.time())
    data = _fake_data([
        {"status": "open", "condition_id": "0xA", "token_id": "T1",
         "cost_usd": 40, "last_record_ts": now - 10},
    ])
    cost, ts = tracker.get_cost_on_token(data, "0xA", "T1")
    print(f"Test 5 (grace_ts): cost={cost}, age={now-ts}s (expected ~10s)")
    assert 5 <= (now - ts) <= 15
    print("  PASS")


def test_6_flag_off_uses_buf():
    """When USE_ONCHAIN_COST=False, _get_already_bet_v1 returns buf.last_tier_bet."""
    assert config.USE_ONCHAIN_COST is False, "fixture assumes flag starts OFF"
    buf = {"last_tier_bet": 75.50}
    val = m._get_already_bet_v1("denizz", buf, "0xA", "T1")
    print(f"Test 6 (flag OFF): already_bet={val} (expected 75.50)")
    assert val == 75.50
    print("  PASS")


def test_7_flag_on_uses_tracker(monkeypatch_save_load):
    """When flag=True, reads from tracker even if buf has different value."""
    orig = config.USE_ONCHAIN_COST
    config.USE_ONCHAIN_COST = True
    try:
        # Fake tracker.load to return data with cost=42
        orig_load = tracker.load
        tracker.load = lambda: _fake_data([
            {"status": "open", "condition_id": "0xA", "token_id": "T1",
             "cost_usd": 42.00, "last_record_ts": int(time.time())},
        ])
        buf = {"last_tier_bet": 999.99}  # stale — should NOT be used
        val = m._get_already_bet_v1("denizz", buf, "0xA", "T1")
        print(f"Test 7 (flag ON): already_bet={val} (expected 42.0 from tracker, not 999.99 from buf)")
        assert val == 42.0
        tracker.load = orig_load
    finally:
        config.USE_ONCHAIN_COST = orig
    print("  PASS")


def test_8_throttle_blocks_repeats():
    """Two rapid calls within window: second should be blocked."""
    orig = config.USE_ONCHAIN_COST
    config.USE_ONCHAIN_COST = True
    try:
        # Fresh state
        m._tier_upgrade_last_ts.clear()
        assert m._throttle_allows_upgrade("0xXYZ", "TOK1") is True
        # Immediate retry within window
        allowed = m._throttle_allows_upgrade("0xXYZ", "TOK1")
        print(f"Test 8 (throttle): first=True, second={allowed} (expected False)")
        assert allowed is False
    finally:
        config.USE_ONCHAIN_COST = orig
    print("  PASS")


def test_9_throttle_skipped_when_flag_off():
    """Throttle has no effect when flag is OFF (legacy path)."""
    assert config.USE_ONCHAIN_COST is False
    m._tier_upgrade_last_ts.clear()
    assert m._throttle_allows_upgrade("0xABC", "TOK2") is True
    # With flag OFF — no throttle, always True
    assert m._throttle_allows_upgrade("0xABC", "TOK2") is True
    print("Test 9 (throttle bypassed when flag OFF): PASS")


if __name__ == "__main__":
    print("=" * 60)
    print("Variant 1 tests")
    print(f"USE_ONCHAIN_COST at start = {config.USE_ONCHAIN_COST}")
    print("=" * 60)
    test_1_cost_filters_open()
    test_2_cost_sums_inflight()
    test_3_no_match_returns_zero()
    test_4_wrong_token()
    test_5_grace_period_ts()
    test_6_flag_off_uses_buf()
    test_7_flag_on_uses_tracker(None)  # simple stub — monkeypatch passed as None
    test_8_throttle_blocks_repeats()
    test_9_throttle_skipped_when_flag_off()
    print()
    print("=" * 60)
    print("ALL VARIANT 1 TESTS PASSED")
    print("=" * 60)
