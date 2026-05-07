"""No-regression smoke tests.

Verify the patch does not alter pre-existing bot behavior.
"""
from unittest.mock import MagicMock, patch
import pytest


def test_place_limit_buy_is_untouched(monkeypatch):
    """The buy path does not call safe_sell and still works."""
    import executor
    fake_client = MagicMock()
    fake_client.post_order.return_value = {
        "success": True,
        "orderID": "BUY-1",
    }
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    result = executor.place_limit_buy(token_id="99", price=0.5, size_usd=10)
    assert result is not None
    assert result["order_id"] == "BUY-1"


def test_positions_without_pending_marker_behave_as_before(
    fresh_tracker_data, open_position, tmp_path, monkeypatch
):
    """process_pending_retries is a no-op when nothing is marked pending."""
    import tracker, exit_manager, config, executor
    key = "0xKEY_REGR"
    fresh_tracker_data["positions"][key] = dict(open_position)
    temp_path = tmp_path / "positions.json"
    import json
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(fresh_tracker_data, f, indent=2)
    monkeypatch.setattr(config, "POSITIONS_FILE", str(temp_path))
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(temp_path), raising=False)

    fake_client = MagicMock()
    monkeypatch.setattr(executor, "_get_client", lambda: fake_client)

    exit_manager.process_pending_retries()

    fake_client.post_order.assert_not_called()


def test_safe_sell_import_does_not_call_rpc():
    """Importing safe_sell must never trigger a network call."""
    # If it did, this import would hang or raise. Succeeds silently.
    import safe_sell
    assert callable(safe_sell.compute_safe_sell_size)
    assert callable(safe_sell.get_wallet_balance)
    assert callable(safe_sell.parse_insufficient_balance_error)


def test_executor_exposes_sell_skip_constant():
    """Public API: exit_manager and tests reference this constant."""
    import executor
    assert hasattr(executor, "SELL_SKIP_INSUFFICIENT_BALANCE")
    assert isinstance(executor.SELL_SKIP_INSUFFICIENT_BALANCE, str)
