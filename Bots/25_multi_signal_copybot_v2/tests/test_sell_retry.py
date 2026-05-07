"""Integration tests for the retry-on-fail pipeline.

Scenarios covered:
  1. Happy path — order accepted first try, no pending marker.
  2. Insufficient balance error → one retry with larger safety margin → success.
  3. Total API failure → position gets _pending_exit_retry marker.
  4. process_pending_retries actually attempts a retry and clears on success.
  5. process_pending_retries respects RETRY_WINDOW_MIN (stops after expiry).
  6. process_pending_retries respects RETRY_MAX_ATTEMPTS.

All CLOB and RPC calls are mocked — zero real network.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest


# ---------- fixtures ----------

@pytest.fixture
def tracker_with_open_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    """Persist a single-position tracker to a temp positions.json and
    monkeypatch tracker.POSITIONS_FILE so load/save use our temp file."""
    import tracker, config
    key = "0xKEY_TEST"
    fresh_tracker_data["positions"][key] = dict(open_position)

    temp_path = tmp_path / "positions.json"
    import json
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(fresh_tracker_data, f, indent=2)

    monkeypatch.setattr(config, "POSITIONS_FILE", str(temp_path))
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(temp_path), raising=False)
    return key, temp_path


# ---------- helpers ----------

def _fake_ok_order(order_id="ORDER-OK", price=0.94, size=59.50):
    return {
        "success": True,
        "orderID": order_id,
        "price": price,
        "size": size,
    }


def _fake_rejection(msg="Unknown"):
    return {"success": False, "errorMsg": msg}


# ---------- tests ----------

def test_happy_path_no_pending_marker(tracker_with_open_position, monkeypatch):
    """Normal successful sell — no _pending_exit_retry should ever appear."""
    import executor, exit_manager, tracker
    key, path = tracker_with_open_position

    # Mock on-chain balance: matches tracker (59.51 request vs 59.51 onchain)
    monkeypatch.setattr(
        "safe_sell.get_wallet_balance",
        lambda *a, **k: 59.51,
    )
    # Mock ClobClient: cancel_all noop, post_order → success
    fake_client = MagicMock()
    fake_client.post_order.return_value = _fake_ok_order()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)
    # Mock wait_for_fill_with_details → MATCHED immediately
    monkeypatch.setattr(
        executor, "wait_for_fill_with_details",
        lambda *a, **k: {
            "status": "MATCHED", "size_matched": 59.50,
            "size_original": 59.50, "price": 0.94, "filled_pct": 1.0,
        },
    )

    data = tracker.load()
    pos = data["positions"][key]
    exit_manager._execute_sell(data, key, pos, shares=59.51, price=0.94, reason="test")

    data = tracker.load()
    assert "_pending_exit_retry" not in data["positions"][key]
    # Position should have a sell recorded
    assert len(data["positions"][key]["sells"]) == 1


def test_insufficient_balance_skips_and_clears(tracker_with_open_position, monkeypatch):
    """If safe_sell says balance is below MIN_SHARES, we don't place an order,
    mark position sold (on-chain is empty) and clear any pending marker."""
    import executor, exit_manager, tracker
    key, path = tracker_with_open_position

    # on-chain is dust — below MIN_SHARES
    monkeypatch.setattr(
        "safe_sell.get_wallet_balance",
        lambda *a, **k: 0.0001,
    )
    fake_client = MagicMock()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    data = tracker.load()
    pos = data["positions"][key]
    exit_manager._execute_sell(data, key, pos, shares=59.51, price=0.94, reason="test")

    data = tracker.load()
    assert data["positions"][key]["status"] == "sold"
    assert data["positions"][key]["size_shares"] == 0
    assert "_pending_exit_retry" not in data["positions"][key]
    # post_order should NOT have been called (we detected insufficient balance
    # BEFORE reaching CLOB)
    fake_client.post_order.assert_not_called()


def test_api_failure_marks_pending(tracker_with_open_position, monkeypatch):
    """If both attempts fail at the CLOB, a _pending_exit_retry marker is saved."""
    import executor, exit_manager, tracker
    key, path = tracker_with_open_position

    monkeypatch.setattr(
        "safe_sell.get_wallet_balance",
        lambda *a, **k: 59.509092,  # on-chain realistic
    )
    # Mock ClobClient to reject both attempts
    fake_client = MagicMock()
    fake_client.post_order.return_value = _fake_rejection("simulated API failure")
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    data = tracker.load()
    pos = data["positions"][key]
    exit_manager._execute_sell(data, key, pos, shares=59.51, price=0.94, reason="test_reason")

    data = tracker.load()
    pending = data["positions"][key].get("_pending_exit_retry")
    assert pending is not None, "Expected _pending_exit_retry to be set after failure"
    assert pending["attempts"] >= 1
    assert pending["last_price"] == 0.94
    assert "test_reason" in pending["last_reason"]
    # Both attempts should have been made
    assert fake_client.post_order.call_count == 2


def test_process_pending_retries_runs_and_clears_on_success(
    tracker_with_open_position, monkeypatch
):
    """After a pending marker is set, a subsequent cycle must retry
    and clear the marker when the sell goes through."""
    import tracker, exit_manager, executor
    key, path = tracker_with_open_position

    # Put a pending marker manually
    data = tracker.load()
    data["positions"][key]["_pending_exit_retry"] = {
        "since": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
        "last_attempt": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
        "attempts": 1,
        "last_price": 0.94,
        "last_reason": "stop_loss",
        "last_error": "api_error",
    }
    tracker.save(data)

    # Mocks for the retry attempt
    monkeypatch.setattr("safe_sell.get_wallet_balance", lambda *a, **k: 59.509092)
    fake_client = MagicMock()
    fake_client.post_order.return_value = _fake_ok_order()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        executor, "wait_for_fill_with_details",
        lambda *a, **k: {
            "status": "MATCHED", "size_matched": 59.50,
            "size_original": 59.50, "price": 0.94, "filled_pct": 1.0,
        },
    )

    exit_manager.process_pending_retries()

    data = tracker.load()
    assert "_pending_exit_retry" not in data["positions"][key]
    assert len(data["positions"][key]["sells"]) == 1


def test_process_pending_retries_respects_window(tracker_with_open_position, monkeypatch):
    """When the retry window has expired, no retry is attempted."""
    import tracker, exit_manager, executor
    from config import RETRY_WINDOW_MIN
    key, path = tracker_with_open_position

    # Pending from WAY in the past — outside window
    data = tracker.load()
    data["positions"][key]["_pending_exit_retry"] = {
        "since": (datetime.now(timezone.utc) - timedelta(minutes=RETRY_WINDOW_MIN + 5)).isoformat(),
        "last_attempt": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
        "attempts": 2,
        "last_price": 0.94,
        "last_reason": "stop_loss",
        "last_error": "api_error",
    }
    tracker.save(data)

    # If retry happens, this mock would be called → test would see call_count>0
    fake_client = MagicMock()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    exit_manager.process_pending_retries()

    fake_client.post_order.assert_not_called()
    # Marker remains in place for audit — not auto-cleared on window expiry
    data = tracker.load()
    assert "_pending_exit_retry" in data["positions"][key]


def test_process_pending_retries_respects_max_attempts(
    tracker_with_open_position, monkeypatch
):
    """After RETRY_MAX_ATTEMPTS reached, no further retries happen."""
    import tracker, exit_manager, executor
    from config import RETRY_MAX_ATTEMPTS
    key, path = tracker_with_open_position

    data = tracker.load()
    data["positions"][key]["_pending_exit_retry"] = {
        "since": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "last_attempt": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "attempts": RETRY_MAX_ATTEMPTS,
        "last_price": 0.94,
        "last_reason": "stop_loss",
        "last_error": "api_error",
    }
    tracker.save(data)

    fake_client = MagicMock()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    exit_manager.process_pending_retries()
    fake_client.post_order.assert_not_called()


def test_process_pending_retries_respects_spacing(
    tracker_with_open_position, monkeypatch
):
    """Retries must not fire more often than RETRY_MIN_SPACING_SEC."""
    import tracker, exit_manager, executor
    key, path = tracker_with_open_position

    data = tracker.load()
    # Last attempt was 1 second ago — within the 60s spacing window
    data["positions"][key]["_pending_exit_retry"] = {
        "since": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "last_attempt": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "attempts": 1,
        "last_price": 0.94,
        "last_reason": "stop_loss",
        "last_error": "api_error",
    }
    tracker.save(data)

    fake_client = MagicMock()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    exit_manager.process_pending_retries()
    fake_client.post_order.assert_not_called()
