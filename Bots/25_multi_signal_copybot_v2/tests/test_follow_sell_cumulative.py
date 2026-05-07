"""Regression tests for 2026-04-21 bug:
cumulative trigger with sold_pct_player > 1.0 was falling through the tier
loop with our_sell_fraction=0, producing a false "dust sell" SKIP on full
exits. Fix: clamp effective_pct to 0.9999 before tier lookup.

Reference incident:
  US x Iran diplomatic meeting by April 21, 2026? (CID 0x6c31c73a…)
  2026-04-21 11:02:17 CUMULATIVE TRIGGER cumul 153% over 2 events
  2026-04-21 11:02:19 SKIP dust sell (153%) we in PROFIT — BUG
"""
import json
import time
from unittest.mock import MagicMock
import pytest


# Reuse same fixtures pattern as test_follow_sell_sensitivity.py
@pytest.fixture
def install_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    import tracker, config

    def _install(signal_player="denizz", key="0xKEY", cid="0xCID", token_id="55",
                 shares=100.0, avg_entry=0.40):
        pos = dict(open_position)
        pos["signal_player"] = signal_player
        pos["condition_id"] = cid
        pos["token_id"] = token_id
        pos["size_shares"] = shares
        pos["avg_entry"] = avg_entry
        pos["entry_price"] = avg_entry
        fresh_tracker_data["positions"][key] = pos

        path = tmp_path / "positions.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fresh_tracker_data, f, indent=2)
        monkeypatch.setattr(config, "POSITIONS_FILE", str(path))
        monkeypatch.setattr(tracker, "POSITIONS_FILE", str(path), raising=False)
        return key, cid, token_id
    return _install


def _setup_env(monkeypatch, cached_size, current_size,
               our_sell_price=0.55, our_avg=0.40, player_avg=0.40,
               preseed_cumul=None):
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
    if preseed_cumul is not None:
        monkeypatch.setattr(exit_manager, "_cumulative_sells", preseed_cumul)
    else:
        monkeypatch.setattr(exit_manager, "_cumulative_sells", {})
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda token: [our_sell_price, our_sell_price + 0.01])
    monkeypatch.setattr(filters, "get_player_cost_basis",
                        lambda cid, wallet, token: player_avg)
    monkeypatch.setattr(tracker, "consolidate_duplicates", lambda data: 0)
    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)
    return spy


# ---------- The bug regression: cumul 153% must map to 100% ----------

def test_cumul_153pct_profit_fires_full_exit(install_position, monkeypatch):
    """BUG regression — cumul 1.53 must map to top tier (100% our-sell),
    not fall through as 'dust sell'."""
    cid, tok = "0xCID", "55"
    key, _, _ = install_position(shares=100.0, avg_entry=0.40,
                                 cid=cid, token_id=tok)

    # Pre-seed cumulative history with a prior 0.53 event (within window)
    preseed = {("denizz", cid, tok): [(time.time() - 30, 0.53)]}

    # Now fire second event: denizz sells his remaining 100%
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=0.0,    # 100% this event
                     our_sell_price=0.55, our_avg=0.40,       # we in PROFIT
                     preseed_cumul=preseed)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Cumul 153% test",
        "sell_price": 0.5,
    })

    assert spy.call_count == 1, "expected full exit fire on cumul 153% (bug: fired 0 before fix)"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    # 100% of 100 sh → exact 100 expected (small tolerance for safe-sell margin)
    assert 99.0 <= sell_shares <= 100.5, f"expected ~100 sh (full exit), got {sell_shares}"


def test_cumul_110pct_loss_fires_full_exit(install_position, monkeypatch):
    """Slightly over 100% cumul + LOSS → top tier 100%."""
    cid, tok = "0xCID", "77"
    key, _, _ = install_position(shares=200.0, avg_entry=0.80,
                                 cid=cid, token_id=tok)

    preseed = {("denizz", cid, tok): [(time.time() - 30, 0.60)]}
    spy = _setup_env(monkeypatch,
                     cached_size=500.0, current_size=250.0,   # 50% this event
                     our_sell_price=0.50, our_avg=0.80,       # LOSS
                     preseed_cumul=preseed)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Cumul 110% test",
        "sell_price": 0.5,
    })

    assert spy.call_count == 1, "expected full exit on cumul 110% in loss"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    assert 195.0 <= sell_shares <= 201.0, f"expected ~200 sh (100% of 200), got {sell_shares}"


def test_cumul_300pct_profit_fires_full_exit(install_position, monkeypatch):
    """Extreme over-ceiling cumul (e.g. many fragmented sells with fresh
    baselines). Must still fire 100%, not collapse to dust."""
    cid, tok = "0xCID", "88"
    key, _, _ = install_position(shares=50.0, avg_entry=0.30,
                                 cid=cid, token_id=tok)

    preseed = {("denizz", cid, tok): [
        (time.time() - 50, 1.00),
        (time.time() - 30, 1.00),
    ]}  # prior sum = 2.00
    spy = _setup_env(monkeypatch,
                     cached_size=100.0, current_size=0.0,     # 100% this event
                     our_sell_price=0.70, our_avg=0.30,       # PROFIT
                     preseed_cumul=preseed)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Cumul 300% test",
        "sell_price": 0.5,
    })

    assert spy.call_count == 1, "expected full exit fire on cumul 300% (extreme over-ceiling)"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    assert 48.0 <= sell_shares <= 50.5, f"expected ~50 sh (full exit), got {sell_shares}"


def test_normal_95pct_profit_still_fires_full_exit(install_position, monkeypatch):
    """Non-regression: a normal 95% sell (no cumul escalation) still maps
    to top tier 100%. Ensures clamp doesn't break the happy path."""
    cid, tok = "0xCID", "99"
    key, _, _ = install_position(shares=80.0, avg_entry=0.40,
                                 cid=cid, token_id=tok)

    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=50.0,   # 95% this event
                     our_sell_price=0.55, our_avg=0.40)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Normal 95% test",
        "sell_price": 0.5,
    })

    assert spy.call_count == 1
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    assert 78.0 <= sell_shares <= 80.5, f"expected ~80 sh (100%), got {sell_shares}"
