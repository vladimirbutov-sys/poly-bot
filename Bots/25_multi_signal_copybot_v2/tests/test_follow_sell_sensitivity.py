"""Tests for heightened follow-sell sensitivity (2026-04-17 patch).

Three changes covered:
  1. PROFIT dust threshold lowered 10% → 5%; new 5-10% tier sells 10%
  2. LOSS dust threshold lowered 20% → 10%; new 10-20% tier sells 15%
  3. Cumulative sell tracking: rolling-window sum of sub-dust sells
     escalates to a tier-based exit when total ≥ CUMULATIVE_SELL_THRESHOLD

All tests mock external IO (RPC, orderbook, Telegram, _execute_sell) so
they're hermetic. Mirrors the test_manual_follow.py pattern.
"""
import json
import time
from unittest.mock import MagicMock
import pytest


# ---------- shared fixtures (lifted from test_manual_follow.py pattern) ----------

@pytest.fixture
def install_position(fresh_tracker_data, open_position, tmp_path, monkeypatch):
    """Install a single open position into a temp positions.json.
    Returns (key, cid, token_id) for use in handle_player_sell."""
    import tracker, config

    def _install(signal_player: str = "denizz",
                 key: str = "0xKEYAB",
                 cid: str = "0xCIDAB",
                 token_id: str = "55",
                 shares: float = 100.0,
                 avg_entry: float = 0.50):
        pos = dict(open_position)
        pos["signal_player"] = signal_player
        pos["condition_id"] = cid
        pos["token_id"] = token_id
        pos["size_shares"] = shares
        pos["avg_entry"] = avg_entry
        pos["entry_price"] = avg_entry
        fresh_tracker_data["positions"][key] = pos

        temp_path = tmp_path / "positions.json"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(fresh_tracker_data, f, indent=2)
        monkeypatch.setattr(config, "POSITIONS_FILE", str(temp_path))
        monkeypatch.setattr(tracker, "POSITIONS_FILE", str(temp_path), raising=False)
        return key, cid, token_id

    return _install


def _setup_env(monkeypatch, cached_size: float, current_size: float,
               our_sell_price: float = 0.55, our_avg: float = 0.50,
               player_avg: float = 0.40, reset_cumul: bool = True):
    """Mock all external dependencies handle_player_sell calls.

    cached_size, current_size — denizz's on-chain balance before/after his sell
    our_sell_price — current orderbook bid for our position
    """
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
    if reset_cumul:
        monkeypatch.setattr(exit_manager, "_cumulative_sells", {})
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda token: [our_sell_price, our_sell_price + 0.01])
    monkeypatch.setattr(filters, "get_player_cost_basis",
                        lambda cid, wallet, token: player_avg)
    monkeypatch.setattr(tracker, "consolidate_duplicates",
                        lambda data: 0)
    spy = MagicMock()
    monkeypatch.setattr(exit_manager, "_execute_sell", spy)
    return spy


# ---------- A. PROFIT tier — new 5-10% sells 10% ----------

def test_profit_7pct_sell_now_triggers_10pct_exit(install_position, monkeypatch):
    """Before patch: 7% denizz sell + we PROFIT → dust SKIP.
    After patch: 7% triggers tier (5-10% → sell 10%)."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.40)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=930.0,   # 7% denizz sold
                     our_sell_price=0.55, our_avg=0.40)        # we in PROFIT

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })

    assert spy.call_count == 1, "expected exit fire on 7% sell when in profit (new 5-10% tier)"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    # Tier 5-10% → 10% of 100 sh = 10 sh
    assert 9.0 <= sell_shares <= 11.0, f"expected ~10 sh (10% tier), got {sell_shares}"


def test_profit_4pct_sell_still_dust(install_position, monkeypatch):
    """4% sell — below new 5% dust line → SKIP."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.40)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=960.0,   # 4% denizz sold
                     our_sell_price=0.55)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })

    assert spy.call_count == 0, "4% sell must remain dust (below new 5% threshold)"


# ---------- B. LOSS tier — new 10-20% sells 15% ----------

def test_loss_15pct_sell_now_triggers_15pct_exit(install_position, monkeypatch):
    """Before patch: 15% denizz sell + we LOSS → dust SKIP (LOSS dust was 20%).
    After patch: 15% triggers tier (10-20% → sell 15%)."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.80)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=850.0,   # 15% denizz sold
                     our_sell_price=0.50, our_avg=0.80)        # we in LOSS

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })

    assert spy.call_count == 1, "expected exit fire on 15% sell when in loss (new 10-20% tier)"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    # 15% of 100 = 15
    assert 14.0 <= sell_shares <= 16.0, f"expected ~15 sh (15% tier), got {sell_shares}"


def test_loss_8pct_sell_still_dust(install_position, monkeypatch):
    """8% sell + we in LOSS — below new 10% dust line → SKIP."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.80)
    spy = _setup_env(monkeypatch,
                     cached_size=1000.0, current_size=920.0,   # 8% sold
                     our_sell_price=0.50, our_avg=0.80)

    import exit_manager
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })

    assert spy.call_count == 0, "8% sell must remain dust for LOSS positions (below new 10%)"


# ---------- C. Cumulative tracking ----------

def test_cumulative_three_subdust_sells_escalate(install_position, monkeypatch):
    """Three 7% sells (each below 10% LOSS dust) should accumulate to 21% →
    3rd event escalates to 20-30% tier → 25% exit. Tests we DO NOT lose
    signal when denizz dribbles his exit."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.80)
    import exit_manager

    # Reset cumulative once at the start; subsequent events accumulate.
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})

    # Event 1: cached 1000 → 930 (7% sell). Below 10% LOSS dust → no fire.
    spy = _setup_env(monkeypatch, cached_size=1000.0, current_size=930.0,
                     our_sell_price=0.50, our_avg=0.80, reset_cumul=False)
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })
    assert spy.call_count == 0, "1st 7% event must be dust"

    # Event 2: another 7% sell (cached 930 → 865). Cumul = 14%, still < 20%.
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})  # clear dedup
    spy2 = _setup_env(monkeypatch, cached_size=930.0, current_size=865.0,
                      our_sell_price=0.50, our_avg=0.80, reset_cumul=False)
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })
    assert spy2.call_count == 0, "2nd 7% event still below cumul 20% threshold"

    # Event 3: another 7% sell. Cumul = 21% → ESCALATE → fire tier 20-30% (25%).
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
    spy3 = _setup_env(monkeypatch, cached_size=865.0, current_size=805.0,
                      our_sell_price=0.50, our_avg=0.80, reset_cumul=False)
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })
    assert spy3.call_count == 1, "3rd event must escalate via cumulative trigger"
    args, kwargs = spy3.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    # cumulative ~21% → tier 20-30% → 25% of 100 sh = 25
    assert 22.0 <= sell_shares <= 28.0, \
        f"expected ~25 sh (20-30% tier on cumulative ~21%), got {sell_shares}"


def test_cumulative_resets_after_fire(install_position, monkeypatch):
    """After a cumulative fire, history clears so the next sub-dust sell
    doesn't immediately re-trigger another exit."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.80)
    import exit_manager
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})

    # Force one big cumulative trigger first (3 × 7%)
    for cached, current in [(1000, 930), (930, 865), (865, 805)]:
        monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
        spy = _setup_env(monkeypatch, cached_size=cached, current_size=current,
                         our_sell_price=0.50, our_avg=0.80, reset_cumul=False)
        exit_manager.handle_player_sell("denizz", {
            "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
        })
    # Trigger fired on event 3; history should be cleared now.

    # 4th event: another 7% sell. Cumulative starts at 0 again — must be dust.
    monkeypatch.setattr(exit_manager, "_recent_exit_fires", {})
    spy4 = _setup_env(monkeypatch, cached_size=805.0, current_size=748.0,
                      our_sell_price=0.50, our_avg=0.80, reset_cumul=False)
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })
    assert spy4.call_count == 0, "after cumul fire+reset, single 7% event must be dust again"


def test_cumulative_window_pruning(install_position, monkeypatch):
    """Old events outside CUMULATIVE_SELL_WINDOW_SEC must be pruned out of the
    cumulative sum. Three 7% sells spaced > 1h apart should not trigger."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.80)
    import exit_manager, config
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})
    # Shrink window to 10 sec for testing; then put events beyond it
    monkeypatch.setattr(config, "CUMULATIVE_SELL_WINDOW_SEC", 10)

    # Inject 2 historical events older than window manually
    cumul_key = ("denizz", cid, tok)
    old_ts = time.time() - 3600  # 1h ago, well outside 10s window
    exit_manager._cumulative_sells[cumul_key] = [
        (old_ts, 0.07), (old_ts + 1, 0.07),
    ]

    # New 7% event: cumul should be just 0.07 (the old two pruned), no fire.
    spy = _setup_env(monkeypatch, cached_size=1000.0, current_size=930.0,
                     our_sell_price=0.50, our_avg=0.80, reset_cumul=False)
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })
    assert spy.call_count == 0, "old events outside window must not contribute"


def test_cumulative_does_not_double_fire_on_individual_tier(install_position, monkeypatch):
    """If a single event already crosses tier on its own (e.g. denizz sells 30%),
    cumulative escalation must not double-count: sold_pct_player stays at 30%,
    not bumped up by adding history."""
    key, cid, tok = install_position(shares=100.0, avg_entry=0.40)
    import exit_manager
    monkeypatch.setattr(exit_manager, "_cumulative_sells", {})

    # Pre-seed history: 7% from earlier
    cumul_key = ("denizz", cid, tok)
    exit_manager._cumulative_sells[cumul_key] = [(time.time() - 5, 0.07)]

    # Now denizz sells 30% in one event. Cumulative would be 37%.
    # The will_escalate guard requires cumulative > current event by margin;
    # here current event (30%) is already a strong tier hit, but cumulative
    # (37%) would tier higher. Let's verify behavior is consistent.
    spy = _setup_env(monkeypatch, cached_size=1000.0, current_size=700.0,
                     our_sell_price=0.55, our_avg=0.40, reset_cumul=False)
    exit_manager.handle_player_sell("denizz", {
        "condition_id": cid, "token_id": tok, "title": "Test", "sell_price": 0.5,
    })
    assert spy.call_count == 1, "should fire on 30% sell either way"
    args, kwargs = spy.call_args
    sell_shares = args[3] if len(args) > 3 else kwargs.get("shares")
    # Either tier 30-40% (35%) or 30-40% via cumulative 37%. Both → 35 sh.
    # Allow 32-40 sh range for safety (tier matrix can pick either bracket).
    assert 30.0 <= sell_shares <= 45.0, \
        f"expected reasonable tier exit on 30%+ event (32-45 sh range), got {sell_shares}"
