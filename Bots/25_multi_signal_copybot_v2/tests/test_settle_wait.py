"""Tests for slippage-settle-wait feature (variant B, 2026-04-17).

Hypothesis: when denizz sells in profit, his market sweep briefly compresses
our bid. Waiting SETTLE_WAIT_SEC (e.g. 30s) and re-reading the bid lets us
catch the natural recovery without complex limit-order machinery.

Tests cover:
  1. Feature disabled → no wait, no bid refresh
  2. denizz in LOSS → urgent path (no wait)
  3. denizz in PROFIT + feature enabled → wait + refresh + use fresh bid
  4. Fresh bid HIGHER than original → we benefit
  5. Fresh bid LOWER than original → we accept it (no protection in this minimal version)
  6. Fresh bid is 0 / empty book → fall back to original price
  7. get_orderbook_prices throws → fall back to original price
  8. Wait duration matches config value
  9. The settle wait does NOT block when sold_pct gives no exit (dust skip)
  10. Regression: no-profit-info path uses default behavior

All tests mock time.sleep so they don't actually wait.
"""
import json
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def install_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    import tracker, config

    def _install(signal_player="denizz", key="0xKEYSW", cid="0xCIDSW",
                 token_id="77", shares=200.0, avg_entry=0.40):
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


def _setup_env(monkeypatch, *, cached, current,
               initial_bid=0.32, fresh_bid=0.35,
               player_avg=0.20, player_sell_price=0.36,
               sleep_spy=None):
    """Prime mocks. Returns spy on _execute_sell.

    initial_bid — bid returned on FIRST call to get_orderbook_prices (decision time)
    fresh_bid — bid returned on SECOND call (after settle)
    player_avg — used to compute player_in_profit (player_sell_price > avg*1.01 → profit)
    """
    import exit_manager, filters, telegram_notify as tg, tracker
    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda wallet, token: current)
    monkeypatch.setattr(exit_manager, "_cache_get",
                        lambda player, cid, token: cached)
    monkeypatch.setattr(exit_manager, "_cache_set", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_peak_get",
                        lambda player, cid, token: cached)
    monkeypatch.setattr(exit_manager, "_peak_set", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_compute_player_peak",
                        lambda *a, **k: cached)
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})
    # Two-stage orderbook mock: first call returns initial_bid, second fresh_bid
    call_count = {"n": 0}
    def fake_orderbook(token):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [initial_bid, initial_bid + 0.01]
        return [fresh_bid, fresh_bid + 0.01]
    monkeypatch.setattr(filters, "get_orderbook_prices", fake_orderbook)
    monkeypatch.setattr(filters, "get_player_cost_basis",
                        lambda cid, wallet, token: player_avg)
    monkeypatch.setattr(tracker, "consolidate_duplicates", lambda data: 0)

    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)

    if sleep_spy is not None:
        monkeypatch.setattr("exit_manager.time.sleep", sleep_spy)
    else:
        # No-op sleep so tests don't actually wait
        monkeypatch.setattr("exit_manager.time.sleep", lambda *a, **k: None)
    return spy, call_count


# ---------- 1. Feature toggle ----------

def test_feature_disabled_skips_settle_wait(install_position, monkeypatch):
    """SLIPPAGE_SETTLE_ENABLED=False → no sleep, no bid refresh, sell at initial bid."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", False)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    sleep_spy = MagicMock()
    spy, call_count = _setup_env(monkeypatch, cached=1000, current=400,
                                  initial_bid=0.32, fresh_bid=0.45,
                                  player_avg=0.20, player_sell_price=0.36,
                                  sleep_spy=sleep_spy)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    assert spy.call_count == 1
    args, _ = spy.call_args
    sell_price = args[4]
    assert abs(sell_price - 0.32) < 1e-6, "must use initial bid (no settle)"
    assert sleep_spy.call_count == 0, "must not sleep when feature disabled"


# ---------- 2. LOSS-mode skips wait ----------

def test_loss_mode_skips_settle_wait(install_position, monkeypatch):
    """When denizz sold in his LOSS (player_sell_price < avg * 1.01) → no wait."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.40)
    sleep_spy = MagicMock()
    # player_avg=0.50, sell_price=0.30 → player in LOSS
    spy, _ = _setup_env(monkeypatch, cached=1000, current=400,
                        initial_bid=0.30, fresh_bid=0.40,
                        player_avg=0.50, player_sell_price=0.30,
                        sleep_spy=sleep_spy)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.30,
    })

    assert spy.call_count == 1
    args, _ = spy.call_args
    assert abs(args[4] - 0.30) < 1e-6, "loss-mode must use initial bid"
    assert sleep_spy.call_count == 0, "loss-mode must not sleep"


# ---------- 3. PROFIT-mode triggers wait ----------

def test_profit_mode_triggers_settle_wait(install_position, monkeypatch):
    """player_in_profit=True + feature enabled → time.sleep called once with config value."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    sleep_spy = MagicMock()
    # player_avg=0.20, sell_price=0.36 → player in PROFIT
    spy, _ = _setup_env(monkeypatch, cached=1000, current=400,
                        initial_bid=0.32, fresh_bid=0.35,
                        player_avg=0.20, player_sell_price=0.36,
                        sleep_spy=sleep_spy)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    assert sleep_spy.call_count == 1, "must sleep once"
    sleep_args, _ = sleep_spy.call_args
    assert sleep_args[0] == 30, f"sleep duration must match config (30s), got {sleep_args[0]}"


# ---------- 4. Fresh bid HIGHER → benefit captured ----------

def test_profit_mode_uses_higher_fresh_bid(install_position, monkeypatch):
    """After settle, fresh bid is higher → that's the price passed to _execute_sell."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    spy, _ = _setup_env(monkeypatch, cached=1000, current=400,
                        initial_bid=0.32, fresh_bid=0.35,   # bid recovered 3c
                        player_avg=0.20, player_sell_price=0.36)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    assert spy.call_count == 1
    sell_price = spy.call_args[0][4]
    assert abs(sell_price - 0.35) < 1e-6, \
        f"must use fresh bid 0.35 after settle, got {sell_price}"


# ---------- 5. Fresh bid LOWER → accept it (no protection in minimal variant) ----------

def test_profit_mode_uses_lower_fresh_bid_too(install_position, monkeypatch):
    """If post-settle bid dropped further, this minimal variant accepts the
    drop (we don't have a guard in variant B). Document expected behavior."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    spy, _ = _setup_env(monkeypatch, cached=1000, current=400,
                        initial_bid=0.32, fresh_bid=0.28,   # bid dropped further
                        player_avg=0.20, player_sell_price=0.36)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    sell_price = spy.call_args[0][4]
    assert abs(sell_price - 0.28) < 1e-6, \
        "minimal variant uses post-settle bid even if lower (acceptable trade-off)"


# ---------- 6. Empty book after settle → fall back ----------

def test_empty_book_after_settle_falls_back_to_original(install_position, monkeypatch):
    """If fresh orderbook returns 0 (empty/invalid) → keep original bid."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    spy, _ = _setup_env(monkeypatch, cached=1000, current=400,
                        initial_bid=0.32, fresh_bid=0.0,    # empty book
                        player_avg=0.20, player_sell_price=0.36)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    sell_price = spy.call_args[0][4]
    assert abs(sell_price - 0.32) < 1e-6, "empty fresh book → use original bid"


# ---------- 7. Orderbook fetch raises → fall back ----------

def test_orderbook_exception_after_settle_falls_back(install_position, monkeypatch):
    """If get_orderbook_prices raises → use original bid."""
    import config, exit_manager, filters, telegram_notify as tg, tracker
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain", lambda w, t: 400)
    monkeypatch.setattr(exit_manager, "_cache_get", lambda p, c, t: 1000)
    monkeypatch.setattr(exit_manager, "_cache_set", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_peak_get", lambda p, c, t: 1000)
    monkeypatch.setattr(exit_manager, "_peak_set", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_compute_player_peak", lambda *a, **k: 1000)
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})
    monkeypatch.setattr(filters, "get_player_cost_basis", lambda c, w, t: 0.20)
    monkeypatch.setattr(tracker, "consolidate_duplicates", lambda data: 0)
    monkeypatch.setattr("exit_manager.time.sleep", lambda *a: None)

    call_count = {"n": 0}
    def fake_orderbook(token):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [0.32, 0.33]
        raise RuntimeError("network down")
    monkeypatch.setattr(filters, "get_orderbook_prices", fake_orderbook)

    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)

    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    assert spy.call_count == 1
    sell_price = spy.call_args[0][4]
    assert abs(sell_price - 0.32) < 1e-6, "exception → use original bid"


# ---------- 8. Wait duration matches config value ----------

def test_wait_duration_matches_config(install_position, monkeypatch):
    """Custom SLIPPAGE_SETTLE_WAIT_SEC is honored."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 60)  # custom
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    sleep_spy = MagicMock()
    _setup_env(monkeypatch, cached=1000, current=400,
               initial_bid=0.32, fresh_bid=0.35,
               player_avg=0.20, player_sell_price=0.36, sleep_spy=sleep_spy)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    assert sleep_spy.call_args[0][0] == 60


# ---------- 9. Dust-skip path doesn't call sleep ----------

def test_dust_skip_does_not_settle_wait(install_position, monkeypatch):
    """If sold_pct triggers dust SKIP, we never reach the settle-wait code."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    sleep_spy = MagicMock()
    # 3% sell — below 5% PROFIT dust threshold → SKIP
    spy, _ = _setup_env(monkeypatch, cached=1000, current=970,
                        initial_bid=0.32, fresh_bid=0.35,
                        player_avg=0.20, player_sell_price=0.36,
                        sleep_spy=sleep_spy)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    assert spy.call_count == 0, "dust skip → no _execute_sell"
    assert sleep_spy.call_count == 0, "dust skip → no sleep"


# ---------- 10. Player profit info missing → no wait ----------

def test_no_player_avg_skips_settle_wait(install_position, monkeypatch):
    """If we can't determine player_in_profit (player_avg=0), no wait — safe default."""
    import config
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_ENABLED", True)
    monkeypatch.setattr(config, "SLIPPAGE_SETTLE_WAIT_SEC", 30)
    key, cid, tok = install_position(shares=200.0, avg_entry=0.20)
    sleep_spy = MagicMock()
    # player_avg=0 → player_in_profit stays None
    spy, _ = _setup_env(monkeypatch, cached=1000, current=400,
                        initial_bid=0.32, fresh_bid=0.40,
                        player_avg=0.0, player_sell_price=0.36,
                        sleep_spy=sleep_spy)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "T",
        "sell_price": 0.36,
    })

    # player_in_profit is None when player_avg <= 0.01 → not True → no settle
    assert sleep_spy.call_count == 0, "missing profit info → no settle wait"
    sell_price = spy.call_args[0][4]
    assert abs(sell_price - 0.32) < 1e-6, "use original bid when no profit info"
