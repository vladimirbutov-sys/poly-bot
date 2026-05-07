"""Tests for tracker.sync_with_onchain disappear-guard.

Two layers of protection against transient API failures falsely closing
positions:
  1. API-failure detection — if data-api returns 0 positions while tracker
     has multiple open, abort sync (don't close anything).
  2. Per-position confirmation counter — require N consecutive zero readings
     before actually closing a position.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

import tracker


# ---------- helpers ----------

def _make_position(cid, token, shares=100.0, signal_player="denizz", title="Test"):
    return {
        "condition_id": cid,
        "token_id": token,
        "title": title,
        "outcome": "Yes",
        "event_slug": "test",
        "entry_price": 0.50,
        "avg_entry": 0.50,
        "size_shares": shares,
        "cost_usd": shares * 0.50,
        "tier": "B",
        "signal_player": signal_player,
        "parts_filled": 1,
        "parts_planned": 1,
        "order_ids": [],
        "timestamp": "2026-04-17T10:00:00+00:00",
        "status": "open",
        "sells": [],
        "final_pnl": 0,
    }


def _make_data(positions):
    """positions: list of (key, pos_dict) tuples"""
    return {
        "positions": {k: p for k, p in positions},
        "stats": {
            "total_bets": 0, "wins": 0, "losses": 0, "sells": 0,
            "total_pnl": 0.0, "peak_balance": 2700, "current_balance": 2700,
        },
    }


def _mock_api_response(api_positions, status=200):
    """api_positions: list of dicts with conditionId/asset/size, OR None for HTTP error."""
    def _get(url, params=None, timeout=None):
        m = MagicMock()
        m.status_code = status
        if api_positions is None:
            m.json.return_value = []
            m.status_code = 500
            return m
        # paginated; we always return all in one batch (<500)
        m.json.return_value = api_positions
        return m
    return _get


# ---------- Layer 1: API failure detection ----------

def test_api_returns_empty_with_multiple_open_positions_aborts(monkeypatch, tmp_path):
    """If API returns 0 positions but tracker has 3+ open → skip closure."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 200.0)),
        ("k3", _make_position("0xCID3", "T3", 300.0)),
    ])

    monkeypatch.setattr("requests.get", _mock_api_response([]))
    result = tracker.sync_with_onchain(data)

    assert result.get("skipped_reason") == "api_likely_failed"
    assert result["closed"] == 0
    # All positions still open, no _disappear_confirmations counter set
    for k, p in data["positions"].items():
        assert p["status"] == "open"
        assert "_disappear_confirmations" not in p


def test_api_http_error_aborts(monkeypatch, tmp_path):
    """If API returns HTTP 500 → fetch_succeeded stays False → skip closure."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 200.0)),
    ])

    monkeypatch.setattr("requests.get", _mock_api_response(None, status=500))
    result = tracker.sync_with_onchain(data)

    assert result.get("skipped_reason") == "api_likely_failed"
    assert result["closed"] == 0
    for k, p in data["positions"].items():
        assert p["status"] == "open"


def test_api_throws_exception_returns_error(monkeypatch, tmp_path):
    """If requests raises → return {error}."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([("k1", _make_position("0xCID1", "T1", 100.0))])

    def _boom(*args, **kwargs):
        raise ConnectionError("network down")
    monkeypatch.setattr("requests.get", _boom)

    result = tracker.sync_with_onchain(data)
    assert "error" in result
    # Position untouched
    assert data["positions"]["k1"]["status"] == "open"


def test_single_open_position_with_empty_api_does_NOT_abort(monkeypatch, tmp_path):
    """Edge: only 1 open position; API returns empty.

    Layer 1 condition is `len(onchain) == 0 and open_count > 1`.
    With 1 open, Layer 1 does NOT abort — Layer 2 (confirmation counter)
    is the only guard. This is intentional: a single position legitimately
    going to zero is plausible (manual close, single-market portfolio).
    """
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([("k1", _make_position("0xCID1", "T1", 100.0))])

    monkeypatch.setattr("requests.get", _mock_api_response([]))
    result = tracker.sync_with_onchain(data)

    # Layer 1 did NOT trigger → goes through to per-position loop → counter increments
    assert "skipped_reason" not in result
    assert data["positions"]["k1"]["_disappear_confirmations"] == 1
    assert data["positions"]["k1"]["status"] == "open"  # NOT closed yet


# ---------- Layer 2: per-position confirmation counter ----------

def test_disappear_first_call_does_not_close(monkeypatch, tmp_path):
    """Position present in tracker, missing from API on 1st call → counter=1, no close."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 50.0)),  # this one stays
    ])

    api_data = [{"conditionId": "0xCID2", "asset": "T2", "size": 50.0}]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    result = tracker.sync_with_onchain(data)
    assert result["closed"] == 0
    assert data["positions"]["k1"]["status"] == "open"
    assert data["positions"]["k1"]["_disappear_confirmations"] == 1
    # The healthy one should not have a counter
    assert "_disappear_confirmations" not in data["positions"]["k2"]


def test_disappear_three_consecutive_closes(monkeypatch, tmp_path):
    """After N consecutive disappear readings, position is closed."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 50.0)),
    ])
    # API always returns only k2
    api_data = [{"conditionId": "0xCID2", "asset": "T2", "size": 50.0}]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    # Call 1: counter=1
    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["status"] == "open"
    assert data["positions"]["k1"]["_disappear_confirmations"] == 1

    # Call 2: counter=2
    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["status"] == "open"
    assert data["positions"]["k1"]["_disappear_confirmations"] == 2

    # Call 3: counter reaches threshold → close
    result = tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["status"] == "sold"
    assert data["positions"]["k1"]["size_shares"] == 0
    assert "_disappear_confirmations" not in data["positions"]["k1"]
    # k2 untouched
    assert data["positions"]["k2"]["status"] == "open"
    assert result["closed"] == 1
    # Sell record was added
    sells = data["positions"]["k1"]["sells"]
    assert len(sells) == 1
    assert sells[0]["reason"] == "onchain_sync_disappeared"


def test_disappear_then_recovery_resets_counter(monkeypatch, tmp_path):
    """If position re-appears in API after partial disappear, counter resets."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 50.0)),
    ])

    # Cycle 1: k1 missing
    api_only_k2 = [{"conditionId": "0xCID2", "asset": "T2", "size": 50.0}]
    monkeypatch.setattr("requests.get", _mock_api_response(api_only_k2))
    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["_disappear_confirmations"] == 1

    # Cycle 2: k1 missing again
    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["_disappear_confirmations"] == 2

    # Cycle 3: k1 RE-APPEARS with full balance — counter resets
    api_full = [
        {"conditionId": "0xCID1", "asset": "T1", "size": 100.0},
        {"conditionId": "0xCID2", "asset": "T2", "size": 50.0},
    ]
    monkeypatch.setattr("requests.get", _mock_api_response(api_full))
    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["status"] == "open"
    assert data["positions"]["k1"]["_disappear_confirmations"] == 0

    # Cycle 4: k1 missing AGAIN → counter starts back at 1, NOT 3
    monkeypatch.setattr("requests.get", _mock_api_response(api_only_k2))
    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["status"] == "open"
    assert data["positions"]["k1"]["_disappear_confirmations"] == 1


def test_layer1_skip_does_not_increment_counter(monkeypatch, tmp_path):
    """When Layer 1 aborts, Layer 2 counters MUST NOT increment.

    Otherwise multiple API failures would falsely accumulate.
    """
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 50.0)),
        ("k3", _make_position("0xCID3", "T3", 25.0)),
    ])

    monkeypatch.setattr("requests.get", _mock_api_response([]))
    # Run 5 times — none should close, none should accumulate counters
    for _ in range(5):
        tracker.sync_with_onchain(data)
    for k in ("k1", "k2", "k3"):
        assert data["positions"][k]["status"] == "open"
        assert "_disappear_confirmations" not in data["positions"][k] or \
               data["positions"][k]["_disappear_confirmations"] == 0


def test_partial_disappear_only_affected_position_increments(monkeypatch, tmp_path):
    """If API returns 4 positions and only 1 of our 5 is missing,
    only the missing one gets a confirmation; others untouched."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 50.0)),
        ("k3", _make_position("0xCID3", "T3", 25.0)),
        ("k4", _make_position("0xCID4", "T4", 10.0)),
        ("k5", _make_position("0xCID5", "T5", 200.0)),
    ])
    api_data = [
        {"conditionId": "0xCID1", "asset": "T1", "size": 100.0},
        {"conditionId": "0xCID2", "asset": "T2", "size": 50.0},
        # k3 missing
        {"conditionId": "0xCID4", "asset": "T4", "size": 10.0},
        {"conditionId": "0xCID5", "asset": "T5", "size": 200.0},
    ]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    tracker.sync_with_onchain(data)
    for k in ("k1", "k2", "k4", "k5"):
        assert "_disappear_confirmations" not in data["positions"][k]
    assert data["positions"]["k3"]["_disappear_confirmations"] == 1
    assert data["positions"]["k3"]["status"] == "open"


def test_healthy_sync_preserves_clean_state(monkeypatch, tmp_path):
    """Normal sync (all positions match) should not introduce any counters."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([
        ("k1", _make_position("0xCID1", "T1", 100.0)),
        ("k2", _make_position("0xCID2", "T2", 50.0)),
    ])
    api_data = [
        {"conditionId": "0xCID1", "asset": "T1", "size": 100.0},
        {"conditionId": "0xCID2", "asset": "T2", "size": 50.0},
    ]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    result = tracker.sync_with_onchain(data)
    assert result["closed"] == 0
    assert "_disappear_confirmations" not in data["positions"]["k1"]
    assert "_disappear_confirmations" not in data["positions"]["k2"]


def test_sync_up_does_not_set_disappear_counter(monkeypatch, tmp_path):
    """If on-chain has MORE shares than tracker (sync up case), no disappear counter."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([("k1", _make_position("0xCID1", "T1", 50.0))])
    # API returns 100 shares (we have 50 in tracker)
    api_data = [{"conditionId": "0xCID1", "asset": "T1", "size": 100.0}]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    tracker.sync_with_onchain(data)
    # Position synced UP, not closed
    assert data["positions"]["k1"]["status"] == "open"
    assert data["positions"]["k1"]["size_shares"] == 100.0
    assert "_disappear_confirmations" not in data["positions"]["k1"]


def test_existing_counter_from_disk_persists_and_increments(monkeypatch, tmp_path):
    """If tracker is loaded from disk with _disappear_confirmations=2 already,
    the next disappear bumps it to 3 and closes (not restart from 0)."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    pos_with_counter = _make_position("0xCID1", "T1", 100.0)
    pos_with_counter["_disappear_confirmations"] = 2  # left over from prior runs
    data = _make_data([
        ("k1", pos_with_counter),
        ("k2", _make_position("0xCID2", "T2", 50.0)),
    ])
    # k1 still missing
    api_data = [{"conditionId": "0xCID2", "asset": "T2", "size": 50.0}]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    tracker.sync_with_onchain(data)
    assert data["positions"]["k1"]["status"] == "sold"  # 2+1=3 → close
    assert "_disappear_confirmations" not in data["positions"]["k1"]


def test_reverse_scan_unaffected_by_guard(monkeypatch, tmp_path):
    """The reverse-scan portion (adopt new on-chain positions) is independent
    of the disappear guard. Even if Layer 1 aborts, this is moot because
    Layer 1 returns early — but if Layer 1 passes, reverse scan still works."""
    monkeypatch.setattr(tracker, "POSITIONS_FILE", str(tmp_path / "p.json"))
    data = _make_data([("k1", _make_position("0xCID1", "T1", 100.0))])

    # API returns k1 + a new position we don't track (adopt)
    api_data = [
        {"conditionId": "0xCID1", "asset": "T1", "size": 100.0},
        {"conditionId": "0xCIDNEW", "asset": "TNEW", "size": 200.0,
         "title": "New market", "outcome": "Yes", "eventSlug": "new", "avgPrice": 0.30},
    ]
    monkeypatch.setattr("requests.get", _mock_api_response(api_data))

    result = tracker.sync_with_onchain(data)
    # k1 healthy, no counter
    assert "_disappear_confirmations" not in data["positions"]["k1"]
    # New position adopted
    new_keys = [k for k in data["positions"] if k.startswith("0xsync_")]
    assert len(new_keys) == 1
    assert data["positions"][new_keys[0]]["title"] == "New market"
