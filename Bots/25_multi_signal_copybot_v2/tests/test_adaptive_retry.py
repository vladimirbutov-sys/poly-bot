"""Regression tests for 2026-04-22 adaptive-retry fix.

Before: single retry at price × 0.98 (stale original), failed when bid collapsed.
After: 3-step adaptive ladder reading FRESH bid each retry.

Reference incident: US x Iran Peace Apr 30 YES, 22.04 01:19
  Original order $0.22 → TIMEOUT (bid already $0.15)
  Old retry $0.216 → TIMEOUT (bid $0.14), bot gave up — 139 sh stuck.
"""
import pytest
import exit_manager


def _fill(status, matched=0, original=100):
    return {"status": status, "size_matched": matched, "size_original": original}


def _pos(token_id="tok", title="Test"):
    return {
        "token_id": token_id, "title": title,
        "status": "open", "size_shares": 100.0,
        "cost_usd": 50.0, "avg_entry": 0.5,
    }


def _data_with_pos(key="k", pos=None):
    pos = pos or _pos()
    return {"positions": {key: pos}, "stats": {}}


@pytest.fixture
def env(monkeypatch):
    """Mock everything except the retry loop itself."""
    import filters, tracker, executor, telegram_notify as tg
    import limit_tracker as _lt

    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    monkeypatch.setattr(_lt, "log_exit", lambda *a, **k: None)
    monkeypatch.setattr(tracker, "record_sell",
                        lambda data, key, shares, price, rev, reason: None)
    monkeypatch.setattr(exit_manager, "_clear_pending_retry", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_mark_pending_retry",
                        lambda *a, **k: None)

    # Bypass cancel-all
    client = type("C", (), {
        "get_orders": lambda self: [],
        "cancel": lambda self, oid: None,
    })()
    monkeypatch.setattr(executor, "_get_client", lambda: client)

    # tracker.load returns data with an open position
    monkeypatch.setattr(tracker, "load", lambda: _data_with_pos())

    return monkeypatch


def test_retry_reads_fresh_bid(env):
    """Initial $0.22 TIMEOUT. bid now $0.14. Retry must submit at
    0.14 × 0.98 = 0.1372, not 0.22 × 0.98 = 0.216."""
    import filters
    env.setattr(filters, "get_orderbook_prices", lambda tok: (0.14, 0.15))

    calls = []
    def fake_sell(tok, price, shares):
        calls.append(price)
        return {"order_id": f"0x{len(calls)}"}
    env.setattr(exit_manager.executor, "place_limit_sell", fake_sell)

    # initial TIMEOUT, retry 1 MATCHED
    fills = iter([_fill("TIMEOUT"), _fill("MATCHED", matched=100)])
    env.setattr(exit_manager.executor, "wait_for_fill_with_details",
                lambda oid, timeout=300: next(fills))

    exit_manager._execute_sell_impl({}, "k", _pos(), 100.0, 0.22, "follow")

    assert len(calls) == 2, f"expected 2 calls, got {len(calls)}: {calls}"
    assert calls[0] == 0.22
    assert abs(calls[1] - 0.1372) < 0.0001, \
        f"retry must use FRESH bid × 0.98, got {calls[1]}"


def test_retry_ladder_walks_deeper(env):
    """All retries TIMEOUT → ladder walks 0.98, 0.95, 0.90."""
    import filters
    env.setattr(filters, "get_orderbook_prices", lambda tok: (0.20, 0.21))

    calls = []
    def fake_sell(tok, price, shares):
        calls.append(price)
        return {"order_id": f"0x{len(calls)}"}
    env.setattr(exit_manager.executor, "place_limit_sell", fake_sell)

    fills = iter([_fill("TIMEOUT")] * 10)
    env.setattr(exit_manager.executor, "wait_for_fill_with_details",
                lambda oid, timeout=300: next(fills))

    exit_manager._execute_sell_impl({}, "k", _pos(), 100.0, 0.25, "follow")

    # initial + 3 retries = 4 calls
    assert len(calls) == 4, f"expected 4 calls, got {len(calls)}: {calls}"
    assert calls[0] == 0.25
    assert abs(calls[1] - 0.196) < 0.0001, f"r1 should be 0.20×0.98=0.196, got {calls[1]}"
    assert abs(calls[2] - 0.190) < 0.0001, f"r2 should be 0.20×0.95=0.190, got {calls[2]}"
    assert abs(calls[3] - 0.180) < 0.0001, f"r3 should be 0.20×0.90=0.180, got {calls[3]}"


def test_retry_first_attempt_succeeds(env):
    """Retry 1 MATCHED → no more retries."""
    import filters
    env.setattr(filters, "get_orderbook_prices", lambda tok: (0.20, 0.21))

    calls = []
    def fake_sell(tok, price, shares):
        calls.append(price)
        return {"order_id": f"0x{len(calls)}"}
    env.setattr(exit_manager.executor, "place_limit_sell", fake_sell)

    fills = iter([_fill("TIMEOUT"), _fill("MATCHED", matched=100)])
    env.setattr(exit_manager.executor, "wait_for_fill_with_details",
                lambda oid, timeout=300: next(fills))

    exit_manager._execute_sell_impl({}, "k", _pos(), 100.0, 0.25, "follow")

    assert len(calls) == 2, f"expected initial + 1 retry, got {len(calls)}"


def test_fallback_to_original_price_when_no_bid(env):
    """If orderbook has no bid, fallback to original × factor."""
    import filters
    env.setattr(filters, "get_orderbook_prices", lambda tok: (0.0, 0.0))

    calls = []
    def fake_sell(tok, price, shares):
        calls.append(price)
        return {"order_id": f"0x{len(calls)}"}
    env.setattr(exit_manager.executor, "place_limit_sell", fake_sell)

    fills = iter([_fill("TIMEOUT")] * 10)
    env.setattr(exit_manager.executor, "wait_for_fill_with_details",
                lambda oid, timeout=300: next(fills))

    exit_manager._execute_sell_impl({}, "k", _pos(), 100.0, 0.50, "follow")

    # Fallback: original 0.50 × {0.98, 0.95, 0.90}
    assert abs(calls[1] - 0.490) < 0.0001
    assert abs(calls[2] - 0.475) < 0.0001
    assert abs(calls[3] - 0.450) < 0.0001


def test_retry_partial_tracks_remaining(env):
    """Retry 1 PARTIAL 40/100 → retry 2 submits remaining 60."""
    import filters
    env.setattr(filters, "get_orderbook_prices", lambda tok: (0.20, 0.21))

    calls = []
    def fake_sell(tok, price, shares):
        calls.append((price, shares))
        return {"order_id": f"0x{len(calls)}"}
    env.setattr(exit_manager.executor, "place_limit_sell", fake_sell)

    fills = iter([
        _fill("TIMEOUT"),
        _fill("PARTIAL", matched=40, original=100),
        _fill("MATCHED", matched=60, original=60),
    ])
    env.setattr(exit_manager.executor, "wait_for_fill_with_details",
                lambda oid, timeout=300: next(fills))

    exit_manager._execute_sell_impl({}, "k", _pos(), 100.0, 0.25, "follow")

    # Initial asks 100, retry 1 asks 100, retry 2 asks 60
    assert calls[0][1] == 100.0
    assert calls[1][1] == 100.0
    assert abs(calls[2][1] - 60.0) < 0.01, \
        f"retry 2 should ask remaining 60, got {calls[2][1]}"
