"""Regression tests for 2026-04-21 bug:
Positions adopted by tracker.sync_with_onchain reverse-scan have
signal_player='unknown' — exit_manager.handle_player_sell was blocking
follow-sell on these, leaving orphan positions stuck forever.

Fix: treat '', 'unknown', None signal_player same as 'manual' — allow
follow-sell from any active player. Cross-player protection only applies
between REAL known players (denizz vs car).

Reference incident:
  Iran agrees to unrestricted shipping through Hormuz in April
  (CID 0x3e1363efbf76…)
  2026-04-17 16:32: denizz sold 84% → our bot logged
  'SKIP: denizz sold but position was opened by unknown'
  — BUG: 205 sh YES stayed stuck, now worth $48 vs cost $62.
"""
import json
import time
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def install_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    import tracker, config

    def _install(signal_player="denizz", key="0xKEY", cid="0xCID", token_id="55",
                 shares=100.0, avg_entry=0.30, adopted_from=None):
        pos = dict(open_position)
        pos["signal_player"] = signal_player
        pos["condition_id"] = cid
        pos["token_id"] = token_id
        pos["size_shares"] = shares
        pos["avg_entry"] = avg_entry
        pos["entry_price"] = avg_entry
        if adopted_from is not None:
            pos["_adopted_from"] = adopted_from
        fresh_tracker_data["positions"][key] = pos

        path = tmp_path / "positions.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fresh_tracker_data, f, indent=2)
        monkeypatch.setattr(config, "POSITIONS_FILE", str(path))
        monkeypatch.setattr(tracker, "POSITIONS_FILE", str(path), raising=False)
        return key, cid, token_id
    return _install


def _setup_env(monkeypatch, cached_size, current_size,
               our_sell_price=0.45, our_avg=0.30, player_avg=0.30):
    import exit_manager, filters, telegram_notify as tg, tracker
    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda wallet, token: current_size)
    monkeypatch.setattr(exit_manager, "_cache_get",
                        lambda player, cid, token: cached_size)
    monkeypatch.setattr(exit_manager, "_cache_set", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_peak_get",
                        lambda player, cid, token: cached_size)
    monkeypatch.setattr(exit_manager, "_peak_set", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_compute_player_peak",
                        lambda *a, **k: cached_size)
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda token: [our_sell_price, our_sell_price + 0.01])
    monkeypatch.setattr(filters, "get_player_cost_basis",
                        lambda cid, wallet, token: player_avg)
    monkeypatch.setattr(tracker, "consolidate_duplicates", lambda data: 0)
    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)
    return spy


# ---------- BUG regression: onchain_sync orphan follows denizz ----------

def test_unknown_signal_player_follows_denizz(install_position, monkeypatch):
    """Iran unrestricted shipping regression — position adopted from onchain_sync
    with signal_player='unknown' must allow follow-sell from denizz."""
    cid, tok = "0xCID", "55"
    key, _, _ = install_position(signal_player="unknown", cid=cid, token_id=tok,
                                 shares=205.0, avg_entry=0.30,
                                 adopted_from="onchain_sync")
    spy = _setup_env(monkeypatch,
                     cached_size=2754.0, current_size=453.0,   # 84% denizz sold
                     our_sell_price=0.94, our_avg=0.30)         # PROFIT

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test market",
        "sell_price": 0.9,
    })

    assert spy.call_count == 1, "expected follow-sell fire on unknown-adopted position"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    # 84% → tier 80-100 → 100% of 205 ≈ 205 (with safe-sell margin)
    assert 195.0 <= sell_shares <= 206.0, f"expected full exit, got {sell_shares}"


def test_empty_signal_player_follows_denizz(install_position, monkeypatch):
    """Empty string signal_player should behave like 'unknown'."""
    cid, tok = "0xCID", "66"
    key, _, _ = install_position(signal_player="", cid=cid, token_id=tok,
                                 shares=100.0, avg_entry=0.50)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=0.0,   # 100%
                     our_sell_price=0.80, our_avg=0.50)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test",
        "sell_price": 0.8,
    })
    assert spy.call_count == 1, "empty signal_player must allow follow-sell"


def test_denizz_signaled_still_follows_denizz(install_position, monkeypatch):
    """Non-regression: normal denizz-opened position still follows denizz."""
    cid, tok = "0xCID", "77"
    key, _, _ = install_position(signal_player="denizz", cid=cid, token_id=tok,
                                 shares=100.0, avg_entry=0.40)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=500.0,  # 50%
                     our_sell_price=0.55, our_avg=0.40)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test",
        "sell_price": 0.55,
    })
    assert spy.call_count == 1


def test_other_player_blocks_denizz_sell(install_position, monkeypatch):
    """Cross-player protection MUST still work between real known players:
    a 'car'-signaled position should NOT follow a 'denizz' sell."""
    cid, tok = "0xCID", "88"
    key, _, _ = install_position(signal_player="car", cid=cid, token_id=tok,
                                 shares=100.0, avg_entry=0.40)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=0.0,
                     our_sell_price=0.55, our_avg=0.40)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test",
        "sell_price": 0.55,
    })
    # signal_player=car and player=denizz → cross-player SKIP
    assert spy.call_count == 0, "cross-player protection between real players must hold"


def test_manual_still_follows_denizz(install_position, monkeypatch):
    """Non-regression: manual positions must keep following any active player
    (original 2026-04-15 fix preserved)."""
    cid, tok = "0xCID", "99"
    key, _, _ = install_position(signal_player="manual", cid=cid, token_id=tok,
                                 shares=50.0, avg_entry=0.40)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=0.0,
                     our_sell_price=0.60, our_avg=0.40)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test",
        "sell_price": 0.6,
    })
    assert spy.call_count == 1
