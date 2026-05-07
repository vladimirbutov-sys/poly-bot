"""Tests for the "manual positions follow any active player" patch.

Covers the behavioral change in exit_manager.handle_player_sell where
positions with signal_player='manual' are allowed to follow denizz's
(or any configured active player's) sell signals — while cross-player
protection between REAL players stays in place.
"""
import json
from unittest.mock import MagicMock
import pytest


# ---------- shared fixture ----------

@pytest.fixture
def tracker_with_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    """Factory fixture: returns a helper that installs a position with given
    signal_player and token_id into a temp positions.json."""
    import tracker, config

    def _install(signal_player: str, key: str = "0xKEY", cid: str = "0xCID",
                 token_id: str = "99", shares: float = 50.0):
        pos = dict(open_position)
        pos["signal_player"] = signal_player
        pos["condition_id"] = cid
        pos["token_id"] = token_id
        pos["size_shares"] = shares
        fresh_tracker_data["positions"][key] = pos

        temp_path = tmp_path / "positions.json"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(fresh_tracker_data, f, indent=2)
        monkeypatch.setattr(config, "POSITIONS_FILE", str(temp_path))
        monkeypatch.setattr(tracker, "POSITIONS_FILE", str(temp_path), raising=False)
        return key, cid, token_id

    return _install


def _mock_full_handle_player_sell_env(monkeypatch, player_name: str,
                                       cached_size: float = 1000.0,
                                       current_size: float = 0.0):
    """Set up all the external dependencies handle_player_sell needs.

    After this helper runs, handle_player_sell will reach the signal_player
    check (our patched block) with a known sold_pct_player and a valid match.
    Returns a MagicMock standing in for exit_manager._execute_sell.
    """
    import exit_manager, filters, telegram_notify as tg
    # Silence Telegram during tests
    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    # RPC: player's current on-chain balance
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda wallet, token: current_size)
    # Cache: prime it with the "before" size so sold_pct > 0
    monkeypatch.setattr(exit_manager, "_cache_get",
                        lambda player, cid, token: cached_size)
    monkeypatch.setattr(exit_manager, "_cache_set",
                        lambda *a, **k: None)
    # Clear dedup window so test calls never get deduped
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
    # Orderbook prices
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda token: [0.5, 0.49])
    # Player cost basis (for profit/loss determination)
    monkeypatch.setattr(filters, "get_player_cost_basis",
                        lambda cid, wallet, token: 0.4)
    # Spy on _execute_sell
    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)
    return spy


# ---------- 5 tests from the plan ----------

def test_manual_position_follows_denizz_sell(
    tracker_with_position, monkeypatch, capsys
):
    """signal_player='manual' + denizz selling → _execute_sell IS called,
    and log contains 'manual position following denizz'."""
    import exit_manager
    key, cid, token_id = tracker_with_position(signal_player="manual")

    spy = _mock_full_handle_player_sell_env(
        monkeypatch, player_name="denizz",
        cached_size=1000.0, current_size=0.0,   # denizz sold 100%
    )

    event = {
        "condition_id": cid, "token_id": token_id, "title": "Test market",
        "source": "snapshot", "sell_price": 0.5,
    }
    exit_manager.handle_player_sell("denizz", event)

    captured = capsys.readouterr().out
    assert "manual position following denizz" in captured
    assert spy.called, "_execute_sell should have been invoked for manual position"


def test_denizz_position_still_follows_denizz(
    tracker_with_position, monkeypatch, capsys
):
    """Regression: normal denizz-owned position still behaves as before."""
    import exit_manager
    key, cid, token_id = tracker_with_position(signal_player="denizz")

    spy = _mock_full_handle_player_sell_env(
        monkeypatch, player_name="denizz",
        cached_size=1000.0, current_size=0.0,
    )

    event = {
        "condition_id": cid, "token_id": token_id, "title": "Test market",
        "source": "snapshot", "sell_price": 0.5,
    }
    exit_manager.handle_player_sell("denizz", event)

    captured = capsys.readouterr().out
    # No 'manual position following' chatter for a denizz-origin position
    assert "manual position following" not in captured
    # No SKIP either
    assert "SKIP: denizz sold but position was opened by" not in captured
    assert spy.called


def test_manual_position_ignores_inactive_player(
    tracker_with_position, monkeypatch, capsys
):
    """If player_name is NOT in config.PLAYERS, handle_player_sell returns
    early (line 542-544 — wallet empty). _execute_sell must NOT be called
    even though our position is 'manual'."""
    import exit_manager
    key, cid, token_id = tracker_with_position(signal_player="manual")

    # No RPC patch needed — we expect early return BEFORE RPC.
    # But patch _execute_sell anyway so we can assert it wasn't called.
    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})

    event = {
        "condition_id": cid, "token_id": token_id, "title": "Test market",
        "source": "snapshot", "sell_price": 0.5,
    }
    # "car" is NOT in PLAYERS (only denizz is active)
    exit_manager.handle_player_sell("car", event)

    spy.assert_not_called()


def test_manual_position_tiered_sell_respected(
    tracker_with_position, monkeypatch, capsys
):
    """50% denizz sell → our manual position gets the 50% tier.

    FOLLOW_SELL_TIERS: 30-60% → 50%. So on 100 sh we expect sell_shares = 50.
    We check this via the captured reason / sell_shares argument to _execute_sell.
    """
    import exit_manager
    key, cid, token_id = tracker_with_position(
        signal_player="manual", shares=100.0,
    )

    spy = _mock_full_handle_player_sell_env(
        monkeypatch, player_name="denizz",
        cached_size=1000.0, current_size=500.0,  # denizz sold 50%
    )

    event = {
        "condition_id": cid, "token_id": token_id, "title": "Test market",
        "source": "snapshot", "sell_price": 0.5,
    }
    # Need higher entry so we are NOT in profit — so the LOSS path applies,
    # which uses FOLLOW_SELL_LOSS_THRESHOLD. For a cleaner "just tiered" test
    # we force PROFIT path by mocking orderbook price above entry.
    import filters
    monkeypatch.setattr(filters, "get_orderbook_prices", lambda token: [0.95, 0.94])

    exit_manager.handle_player_sell("denizz", event)

    # Inspect the positional args of the first call to _execute_sell
    assert spy.call_count >= 1
    args, kwargs = spy.call_args
    # _execute_sell(data, key, pos, shares, price, reason)
    # shares is positional at index 3 (or kw 'shares')
    shares_arg = args[3] if len(args) > 3 else kwargs.get("shares")
    reason_arg = args[5] if len(args) > 5 else kwargs.get("reason")
    # At 50% sold, 100 shares × 0.5 tier = 50.0 (allow small float tolerance)
    assert 45.0 <= shares_arg <= 55.0, (
        f"Expected ~50 shares follow (50% tier), got {shares_arg}"
    )
    # Reason should mention the player name
    assert "denizz" in str(reason_arg).lower()


def test_non_manual_non_denizz_still_blocked(
    tracker_with_position, monkeypatch, capsys
):
    """If a position was opened by 'car' (hypothetical) and 'denizz' sells,
    the cross-player protection must still SKIP. No regression in the
    original safety check."""
    import exit_manager
    # Install a position flagged as opened by a different player
    key, cid, token_id = tracker_with_position(signal_player="car")

    spy = _mock_full_handle_player_sell_env(
        monkeypatch, player_name="denizz",
        cached_size=1000.0, current_size=0.0,
    )

    event = {
        "condition_id": cid, "token_id": token_id, "title": "Test market",
        "source": "snapshot", "sell_price": 0.5,
    }
    exit_manager.handle_player_sell("denizz", event)

    captured = capsys.readouterr().out
    assert "SKIP: denizz sold but position was opened by car" in captured
    spy.assert_not_called()
