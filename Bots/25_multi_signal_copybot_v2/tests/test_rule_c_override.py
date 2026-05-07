"""Regression tests for 2026-04-21 Rule C (whipsaw) override fix.

Rule C previously blocked any new entry if:
  - we exited on same (cid, token) within POST_EXIT_WINDOW_HOURS
  - new entry price within 5% of exit price
  - last exit PnL <= 0

This missed legitimate re-entry signals when the player was making a LARGE
accumulation (convicted reversal), not a passive retest.

Fix adds two overrides (either triggers):
  (a) single buy event >= $1500 → conviction
  (b) cumulative 24h buffer >= $3000 → heavy accumulation

Reference incident:
  Strait of Hormuz traffic normal by end of April, 21.04 22:39
  Denizz accumulated $10 556 in 45s ($7638 single buy), bot SKIPped all 5
  because we had exited the same market 2h earlier at $0.19 in loss -$209.
"""
import sys as _sys
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest
import tracker


class _CapsysProxy:
    def __init__(self, capsys):
        self._capsys = capsys
    @property
    def text(self):
        out = self._capsys.readouterr()
        self._acc = getattr(self, "_acc", "") + (out.out or "") + (out.err or "")
        return self._acc


@pytest.fixture
def log_capture(capsys):
    return _CapsysProxy(capsys)


def _make_event(cost_usd=600.0, price=0.19, token_id="99",
                condition_id="0xCID_TEST", title="Test market"):
    return {
        "player": "denizz", "token_id": token_id,
        "condition_id": condition_id, "price": price,
        "size": cost_usd / price, "cost_usd": cost_usd,
        "title": title, "outcome": "Yes", "event_slug": "test",
    }


def _prime(monkeypatch, recent_exit_ago_hours=2.0, exit_price=0.19, exit_pnl=-200.0):
    """Wire up mocks + recent_exit with loss to trigger Rule C path."""
    import entry_manager, filters, telegram_notify as tg, exit_manager

    entry_spy = MagicMock(return_value=True)
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: False)
    monkeypatch.setattr(tracker, "has_open_position_on_token",
                        lambda data, tok: False)
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: True)
    monkeypatch.setattr(tracker, "get_available_balance",
                        lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load",
                        lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)

    monkeypatch.setattr(filters, "check_signal",
                        lambda *a, **k: (True, 50.0, "ok", {"category": "geo"}))
    monkeypatch.setattr(filters, "calculate_bet_size", lambda *a, **k: 100.0)
    monkeypatch.setattr(filters, "calculate_entry_size_multiplier",
                        lambda *a, **k: (1.0, "on-time"))
    monkeypatch.setattr(filters, "get_player_invested_on_token",
                        lambda *a, **k: 7000.0)
    monkeypatch.setattr(filters, "get_player_avg_price", lambda *a, **k: 0.18)
    monkeypatch.setattr(filters, "get_horizon_multiplier",
                        lambda *a, **k: (1.0, "ok"))
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda *a, **k: (0.18, 0.19))
    monkeypatch.setattr(filters, "get_max_slippage", lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-04-30T00:00:00Z"})
    monkeypatch.setattr(filters, "detect_timeseries_hedge",
                        lambda *a, **k: {"is_hedge": False, "should_buy": False,
                                         "hedge_usd": 0.0, "denizz_primary_usd": 0.0,
                                         "our_primary_usd": 0.0, "reason": ""})
    monkeypatch.setattr(filters, "get_denizz_size_before_event",
                        lambda *a, **k: (0.0, False))
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_cache_get", lambda *a, **k: None)

    for name in ["player_buy", "skip", "entry_placed", "sell_placed", "error",
                 "signal_detected", "buy_placed", "buy_filled"]:
        if hasattr(tg, name):
            monkeypatch.setattr(tg, name, lambda *a, **k: None)

    # Recent exit with loss (Rule C triggers)
    exit_ts = datetime.now(timezone.utc) - timedelta(hours=recent_exit_ago_hours)
    monkeypatch.setattr(
        main, "_recent_exit_on_market",
        lambda cid, token, hours=12: (exit_ts, exit_price, exit_pnl),
    )

    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}
    monkeypatch.setattr(main, "_save_buffers", lambda: None)

    import threading
    class FakeThread:
        def __init__(self, target=None, daemon=None, **kw):
            self._target = target
        def start(self):
            if self._target is not None:
                try: self._target()
                except Exception: pass
    monkeypatch.setattr(threading, "Thread", FakeThread)

    return entry_spy


import time as _time
_NOW = _time.time()

# ============================================================
# Classic whipsaw: small buy + small buffer → SKIP (no regression)
# ============================================================

def test_classic_whipsaw_small_buy_still_skips(monkeypatch, log_capture):
    """Event must be >=$500 (MIN_PLAYER_INVESTED) to reach Rule C. Small $600
    event, below override threshold $1500, no buffer pre-seed → classic SKIP."""
    entry_spy = _prime(monkeypatch)
    main.handle_buy("denizz", _make_event(cost_usd=600.0, price=0.19))
    text = log_capture.text
    assert "RULE C SKIP" in text, f"small buy must still SKIP:\n{text[-400:]}"
    assert not entry_spy.called


# ============================================================
# Override 1: single buy >= $1500 → bypass whipsaw
# ============================================================

def test_override_single_large_buy(monkeypatch, log_capture):
    """Hormuz incident reproducer: denizz buys $7638 at same price we exited.
    Override should trigger, entry should proceed."""
    entry_spy = _prime(monkeypatch)
    main.handle_buy("denizz", _make_event(cost_usd=7638.0, price=0.19))
    text = log_capture.text
    assert "RULE C OVERRIDE" in text, f"expected override on $7638 buy:\n{text[-500:]}"
    assert "RULE C SKIP" not in text


def test_override_threshold_exact(monkeypatch, log_capture):
    """Buy of exactly $1500 → override fires (>=)."""
    entry_spy = _prime(monkeypatch)
    main.handle_buy("denizz", _make_event(cost_usd=1500.0, price=0.19))
    text = log_capture.text
    assert "RULE C OVERRIDE" in text, f"expected override on $1500:\n{text[-500:]}"


def test_override_just_below_threshold(monkeypatch, log_capture):
    """Buy of $1499 → NOT override (still classic whipsaw)."""
    entry_spy = _prime(monkeypatch)
    main.handle_buy("denizz", _make_event(cost_usd=1499.0, price=0.19))
    text = log_capture.text
    assert "RULE C SKIP" in text, "below threshold must still SKIP"
    assert "OVERRIDE" not in text


# ============================================================
# Override 2: cumulative buffer >= $3000 → bypass whipsaw
# ============================================================

def test_override_buffer_accumulation(monkeypatch, log_capture):
    """Multiple smaller buys that accumulate to >= $3000 in 24h buffer
    should override whipsaw. Pre-seed with fresh timestamps so buffer
    pruning (24h window) does not drop them."""
    entry_spy = _prime(monkeypatch)
    buf_key = "0xCID_TEST_99"
    # Pre-seed buffer with $3000 using fresh timestamps (within 24h window)
    main._buy_buffers["denizz"][buf_key] = {
        "buys": [[_NOW - 100, 1500.0], [_NOW - 50, 1500.0]],
        "total_usd": 3000.0,
        "notified": True,
        "first_price": 0.19, "last_tier_bet": 0.0,
    }
    # Incoming small buy (below override 1 threshold) — override 2 should still fire
    main.handle_buy("denizz", _make_event(cost_usd=600.0, price=0.19))
    text = log_capture.text
    assert "RULE C OVERRIDE" in text, f"expected override on $3K buffer:\n{text[-500:]}"
    assert "buffer" in text.lower()


# ============================================================
# Rule C still ALLOWs on profitable exit (non-regression)
# ============================================================

def test_profitable_exit_allows_regardless_of_buy_size(monkeypatch, log_capture):
    """Previous exit was profitable → Rule C ALLOW branch, override not checked."""
    entry_spy = _prime(monkeypatch, exit_pnl=5.0)  # profit
    main.handle_buy("denizz", _make_event(cost_usd=600.0, price=0.19))
    text = log_capture.text
    assert "Rule C ALLOW" in text
    assert "RULE C SKIP" not in text
