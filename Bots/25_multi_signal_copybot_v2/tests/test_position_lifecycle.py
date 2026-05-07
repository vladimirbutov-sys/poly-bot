"""Unit tests for the position-closed lifecycle callback (Variant B).

These tests verify that every full-close transition point in tracker fires
the registered on-close callbacks, while partial closes do NOT. They also
verify the main.py cleanup handler actually removes stale _signaled_keys /
_buy_buffers entries and persists the result.

No real network, RPC or disk IO — tracker.save is monkeypatched.
"""
import copy
from unittest.mock import MagicMock

import pytest

import tracker


# ---------- helpers ----------

def _make_data(pos_overrides=None):
    """Build a minimal tracker-shaped data dict with one open position."""
    pos = {
        "condition_id": "0xCID_LC",
        "token_id": "7777",
        "title": "Lifecycle test market",
        "outcome": "Yes",
        "event_slug": "lc-test",
        "entry_price": 0.50,
        "avg_entry": 0.50,
        "size_shares": 100.0,
        "cost_usd": 50.0,
        "tier": "B",
        "signal_player": "denizz",
        "parts_filled": 1,
        "parts_planned": 1,
        "order_ids": ["pos1"],
        "timestamp": "2026-04-15T11:00:00+00:00",
        "status": "open",
        "sells": [],
        "final_pnl": 0,
    }
    if pos_overrides:
        pos.update(pos_overrides)
    return {
        "positions": {"pos1": pos},
        "stats": {
            "total_bets": 1, "wins": 0, "losses": 0, "sells": 0,
            "total_pnl": 0.0,
            "peak_balance": 2700.0, "current_balance": 2700.0,
        },
    }


@pytest.fixture
def silent_save(monkeypatch):
    """Prevent real positions.json writes from record_sell/resolve_position."""
    monkeypatch.setattr(tracker, "save", lambda data: None)


# ---------- 1. record_sell fires callback on full close ----------

def test_full_close_via_record_sell_fires_callback(silent_save):
    data = _make_data()
    calls = []
    tracker.register_on_close(
        lambda cid, tok, sp, reason: calls.append((cid, tok, sp, reason))
    )

    # Sell ALL 100 shares -> size_shares goes to 0 -> full close
    tracker.record_sell(data, "pos1", 100.0, 0.60, 60.0, "auto_exit")

    assert data["positions"]["pos1"]["status"] == "sold"
    assert len(calls) == 1
    cid, tok, sp, reason = calls[0]
    assert cid == "0xCID_LC"
    assert tok == "7777"
    assert sp == "denizz"
    assert "auto_exit" in reason


# ---------- 2. partial close does NOT fire callback ----------

def test_partial_close_does_NOT_fire_callback(silent_save):
    data = _make_data()
    calls = []
    tracker.register_on_close(
        lambda cid, tok, sp, reason: calls.append((cid, tok, sp, reason))
    )

    # Sell only 20 of 100 -> 80 remaining -> NOT a full close
    tracker.record_sell(data, "pos1", 20.0, 0.55, 11.0, "partial_exit")

    assert data["positions"]["pos1"]["status"] == "open"
    assert data["positions"]["pos1"]["size_shares"] == pytest.approx(80.0)
    assert calls == [], f"Callback fired on partial close: {calls}"


# ---------- 3/4. main handler clears _signaled_keys + _buy_buffers ----------

def _setup_main_with_seeded_state(monkeypatch):
    """Import main, wire it for callback tests, return (main, buf_key)."""
    import main
    # Reset module-level state to a predictable shape.
    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}
    buf_key = "0xCID_LC_7777"
    main._signaled_keys["denizz"].add(buf_key)
    main._buy_buffers["denizz"][buf_key] = {
        "buys": [[1.0, 100.0]],
        "total_usd": 100.0,
        "notified": True,
        "first_price": 0.50,
        "last_tier_bet": 50.0,
    }
    # Block actual disk writes during these tests.
    monkeypatch.setattr(main, "_save_buffers", lambda: None)
    # Register the real handler.
    tracker.register_on_close(main._on_position_closed)
    return main, buf_key


def test_callback_clears_signaled_keys(monkeypatch, silent_save):
    main, buf_key = _setup_main_with_seeded_state(monkeypatch)
    assert buf_key in main._signaled_keys["denizz"]

    data = _make_data()
    tracker.record_sell(data, "pos1", 100.0, 0.60, 60.0, "auto_exit")

    assert buf_key not in main._signaled_keys["denizz"]


def test_callback_clears_signal_buffers(monkeypatch, silent_save):
    main, buf_key = _setup_main_with_seeded_state(monkeypatch)
    assert buf_key in main._buy_buffers["denizz"]

    data = _make_data()
    tracker.record_sell(data, "pos1", 100.0, 0.60, 60.0, "auto_exit")

    assert buf_key not in main._buy_buffers["denizz"]


# ---------- 5. handler calls _save_buffers ----------

def test_callback_persists_to_disk(monkeypatch, silent_save):
    import main
    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}
    buf_key = "0xCID_LC_7777"
    main._signaled_keys["denizz"].add(buf_key)

    save_spy = MagicMock()
    monkeypatch.setattr(main, "_save_buffers", save_spy)
    tracker.register_on_close(main._on_position_closed)

    data = _make_data()
    tracker.record_sell(data, "pos1", 100.0, 0.60, 60.0, "auto_exit")

    save_spy.assert_called_once()


# ---------- 6/7. resolve_position fires for won/lost ----------

def test_resolve_position_won_fires_callback(silent_save):
    data = _make_data()
    calls = []
    tracker.register_on_close(
        lambda cid, tok, sp, reason: calls.append((cid, tok, sp, reason))
    )

    tracker.resolve_position(data, "pos1", won=True)

    assert data["positions"]["pos1"]["status"] == "won"
    assert len(calls) == 1
    assert calls[0][3] == "resolved_won"


def test_resolve_position_lost_fires_callback(silent_save):
    data = _make_data()
    calls = []
    tracker.register_on_close(
        lambda cid, tok, sp, reason: calls.append((cid, tok, sp, reason))
    )

    tracker.resolve_position(data, "pos1", won=False)

    assert data["positions"]["pos1"]["status"] == "lost"
    assert len(calls) == 1
    assert calls[0][3] == "resolved_lost"


# ---------- 8. sync_with_onchain disappeared fires callback ----------

def test_sync_onchain_disappeared_fires_callback(monkeypatch):
    """When sync_with_onchain sees shares == 0 on-chain for a position that
    the tracker still marks open, it closes the tracker row. Our lifecycle
    hook must fire with reason='onchain_sync_disappeared'."""
    data = _make_data()

    # Fake the requests.get used by sync_with_onchain to return "no on-chain
    # position" -> sync will see onchain_shares = 0 and close the tracker row.
    import requests as _req

    class _FakeResp:
        status_code = 200
        def json(self):
            return []  # wallet holds nothing on-chain

    def fake_get(*a, **k):
        return _FakeResp()

    monkeypatch.setattr(_req, "get", fake_get)
    monkeypatch.setattr(tracker, "save", lambda d: None)

    calls = []
    tracker.register_on_close(
        lambda cid, tok, sp, reason: calls.append((cid, tok, sp, reason))
    )

    # Disappear-guard (added 2026-04-17): require N consecutive zero readings
    # before actually closing. With single open position, Layer 1 doesn't abort,
    # so confirmation counter accumulates and closes on N-th call.
    n_required = tracker.DISAPPEAR_CONFIRMATIONS_REQUIRED
    res = None
    for _ in range(n_required):
        res = tracker.sync_with_onchain(data)

    assert res["closed"] >= 1
    assert data["positions"]["pos1"]["status"] == "sold"
    assert any(r[3] == "onchain_sync_disappeared" for r in calls), (
        f"Expected onchain_sync_disappeared fire; got {calls}"
    )


# ---------- 9. idempotency: calling cleanup twice is safe ----------

def test_callback_idempotent_on_already_cleared_state(monkeypatch):
    """Invoking _on_position_closed twice on the same buf_key must not raise
    and must leave state consistent."""
    import main
    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}
    monkeypatch.setattr(main, "_save_buffers", lambda: None)

    # First call: state is already empty -> no-op, no exception.
    main._on_position_closed("0xABC", "1", "denizz", "test")
    # Second call: same args -> still no exception.
    main._on_position_closed("0xABC", "1", "denizz", "test")

    # Unknown player -> guarded, no exception.
    main._on_position_closed("0xABC", "1", "unknown", "test")
    # Empty player -> early return.
    main._on_position_closed("0xABC", "1", "", "test")
