"""Tests for STOP_LOSS_ENABLED global kill-switch (2026-04-18).

When STOP_LOSS_ENABLED=False, the entire stop-loss block in check_exits is
skipped — bot will not auto-sell on price drops. Other exits (target
take-profit at 99.5c, follow-sell, redemption) are unaffected.
"""
import json
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def install_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    import tracker, config

    def _install(key="0xKEYSL", cid="0xCIDSL", token_id="44",
                 shares=100.0, avg_entry=0.50, custom_stop=None,
                 disable_sl=False):
        pos = dict(open_position)
        pos["condition_id"] = cid
        pos["token_id"] = token_id
        pos["size_shares"] = shares
        pos["avg_entry"] = avg_entry
        pos["entry_price"] = avg_entry
        if custom_stop is not None:
            pos["custom_stop_loss_price"] = custom_stop
        if disable_sl:
            pos["disable_stop_loss"] = True
        fresh_tracker_data["positions"][key] = pos

        path = tmp_path / "positions.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fresh_tracker_data, f, indent=2)
        monkeypatch.setattr(config, "POSITIONS_FILE", str(path))
        monkeypatch.setattr(tracker, "POSITIONS_FILE", str(path), raising=False)
        return key, cid, token_id

    return _install


def _setup_mocks(monkeypatch, *, current_bid):
    """Mock externals for check_exits."""
    import exit_manager, filters, tracker, telegram_notify as tg
    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    monkeypatch.setattr(tg, "error", lambda *a, **k: None)
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda token: [current_bid, current_bid + 0.01])
    monkeypatch.setattr(tracker, "consolidate_duplicates", lambda data: 0)
    # Mute unrelated periodic calls
    monkeypatch.setattr(exit_manager, "process_pending_retries",
                        lambda data: None)
    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)
    return spy


# ---------- 1. KILL SWITCH OFF — default behavior preserved ----------

def test_stop_loss_enabled_true_triggers_at_threshold(install_position, monkeypatch):
    """STOP_LOSS_ENABLED=True + bid drop > 80% → fires (existing behavior)."""
    import config
    monkeypatch.setattr(config, "STOP_LOSS_ENABLED", True)
    key, cid, tok = install_position(shares=100.0, avg_entry=0.50)
    spy = _setup_mocks(monkeypatch, current_bid=0.05)   # 90% drop > 80%

    import exit_manager
    exit_manager.check_exits()

    assert spy.call_count == 1, "stop-loss should fire when ENABLED=True and threshold crossed"


# ---------- 2. KILL SWITCH ON — stop-loss disabled ----------

def test_stop_loss_enabled_false_blocks_all_stops(install_position, monkeypatch):
    """STOP_LOSS_ENABLED=False → no stop-loss even on extreme drops."""
    import config
    monkeypatch.setattr(config, "STOP_LOSS_ENABLED", False)
    key, cid, tok = install_position(shares=100.0, avg_entry=0.50)
    spy = _setup_mocks(monkeypatch, current_bid=0.01)   # 98% drop

    import exit_manager
    exit_manager.check_exits()

    assert spy.call_count == 0, "stop-loss must NOT fire when global flag is False"


def test_stop_loss_disabled_blocks_custom_stops_too(install_position, monkeypatch):
    """When global flag False, even per-position custom_stop_loss_price is ignored."""
    import config
    monkeypatch.setattr(config, "STOP_LOSS_ENABLED", False)
    key, cid, tok = install_position(shares=100.0, avg_entry=0.50,
                                     custom_stop=0.30)   # would normally trigger if bid <= 0.30
    spy = _setup_mocks(monkeypatch, current_bid=0.10)   # well below custom stop

    import exit_manager
    exit_manager.check_exits()

    assert spy.call_count == 0, "custom_stop_loss must also be skipped when global flag False"


# ---------- 3. Target take-profit STILL works ----------

def test_target_takeprofit_still_fires_when_stop_loss_disabled(install_position, monkeypatch):
    """EXIT_SELL_AT_PRICE (99.5c target) is INDEPENDENT of stop-loss flag — still fires."""
    import config
    monkeypatch.setattr(config, "STOP_LOSS_ENABLED", False)
    monkeypatch.setattr(config, "EXIT_SELL_AT_PRICE", 0.995)
    key, cid, tok = install_position(shares=100.0, avg_entry=0.30)
    spy = _setup_mocks(monkeypatch, current_bid=0.998)   # bid >= 0.995 + > entry

    import exit_manager
    # Need to import config-loaded EXIT_SELL_AT_PRICE
    monkeypatch.setattr(exit_manager, "EXIT_SELL_AT_PRICE", 0.995)
    exit_manager.check_exits()

    assert spy.call_count == 1, "target take-profit must fire even when stop-loss is disabled"


# ---------- 4. Per-position disable_stop_loss still respected ----------

def test_per_position_disable_still_works_when_global_enabled(install_position, monkeypatch):
    """When global flag True but position has disable_stop_loss: True → skip that position."""
    import config
    monkeypatch.setattr(config, "STOP_LOSS_ENABLED", True)
    key, cid, tok = install_position(shares=100.0, avg_entry=0.50, disable_sl=True)
    spy = _setup_mocks(monkeypatch, current_bid=0.05)   # would trigger normally

    import exit_manager
    exit_manager.check_exits()

    assert spy.call_count == 0, "per-position disable_stop_loss must skip even when global ON"


# ---------- 5. Default (config missing) → safe to ENABLED ----------

def test_default_when_missing_config_constant_is_enabled(install_position, monkeypatch):
    """If config.STOP_LOSS_ENABLED is missing entirely → default to True (safe)."""
    import config
    if hasattr(config, "STOP_LOSS_ENABLED"):
        monkeypatch.delattr(config, "STOP_LOSS_ENABLED")
    key, cid, tok = install_position(shares=100.0, avg_entry=0.50)
    spy = _setup_mocks(monkeypatch, current_bid=0.05)

    import exit_manager
    exit_manager.check_exits()

    assert spy.call_count == 1, "missing config → default ENABLED → stop-loss fires"
