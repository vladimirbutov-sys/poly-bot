"""Shared pytest fixtures and path setup for bot tests.

Avoids real network / blockchain calls. Every test that touches
executor/exit_manager/safe_sell must use the mocks provided here.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock

# Make the bot package importable when tests run from tests/ directory
BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


@pytest.fixture
def fresh_tracker_data():
    """An in-memory positions.json-shaped dict for tests.

    Mirrors tracker._default_data() — must stay in sync if that changes.
    """
    return {
        "positions": {},
        "stats": {
            "total_bets": 0, "wins": 0, "losses": 0, "sells": 0,
            "total_pnl": 0.0,
            "peak_balance": 2700.0, "current_balance": 2700.0,
        },
    }


@pytest.fixture
def open_position():
    """A single open position, tracker shape."""
    return {
        "condition_id": "0xCID",
        "token_id": "99",
        "title": "Test market",
        "outcome": "No",
        "event_slug": "test",
        "entry_price": 0.70,
        "avg_entry": 0.70,
        "size_shares": 59.51,   # tracker value (2-decimal)
        "cost_usd": 41.65,
        "tier": "B",
        "signal_player": "denizz",
        "parts_filled": 1,
        "parts_planned": 1,
        "order_ids": [],
        "timestamp": "2026-04-15T11:00:00+00:00",
        "status": "open",
        "sells": [],
        "final_pnl": 0,
    }


@pytest.fixture(autouse=True)
def _reset_on_close_callbacks():
    """Ensure each test starts with a clean tracker callback registry.

    Without this, a callback registered by one test (e.g. main._on_position_closed
    imported during integration tests) leaks into subsequent tests and can mutate
    their module-level state.
    """
    import tracker as _tracker
    saved = list(_tracker._on_close_callbacks)
    _tracker._on_close_callbacks.clear()
    yield
    _tracker._on_close_callbacks.clear()
    _tracker._on_close_callbacks.extend(saved)


@pytest.fixture(autouse=True)
def _reset_tier_upgrade_throttle():
    """Variant 1 throttle is module-level; reset between tests so one test's
    upgrade call does not block another's on the same (cid, token)."""
    try:
        import main as _main
        _main._tier_upgrade_last_ts.clear()
    except Exception:
        pass
    yield


@pytest.fixture
def mock_clob_client(monkeypatch):
    """Replace executor._get_client with a MagicMock that returns
    a pre-configured mock client. Tests configure .post_order.return_value."""
    import executor
    fake = MagicMock()
    monkeypatch.setattr(executor, "_get_client", lambda: fake)
    return fake
