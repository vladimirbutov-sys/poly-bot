"""Tests for the 2026-04-16 bug: _force_tier_upgrade=True when WE have no position.

Bug: denizz already has shares on-chain, but WE don't have a position.
The bot incorrectly routes to tier-upgrade path (which can't create new
positions), the event silently falls through, and we miss the trade.

Fix: before setting _force_tier_upgrade=True, check if WE have an open
position on the same condition_id. If not, leave _force_tier_upgrade=False
so the event goes through Path A (new entry with Rule A+ sizing).
"""
import sys as _sys
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

from unittest.mock import MagicMock  # noqa: E402
import pytest  # noqa: E402


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


def _make_event(cost_usd=356.0, price=0.32, token_id="HORMUZ_TOK",
                condition_id="0xHORMUZ", title="Iran agrees to unrestricted shipping"):
    return {
        "player": "denizz",
        "token_id": token_id,
        "condition_id": condition_id,
        "price": price,
        "size": cost_usd / price,
        "cost_usd": cost_usd,
        "title": title,
        "outcome": "Yes",
        "event_slug": "iran-hormuz",
    }


def _prime(monkeypatch, we_have_position=False, denizz_size_before=2282.0,
           bet_size=20.0, already_bet=0.0):
    """Wire all downstream deps for handle_buy."""
    import entry_manager, filters, tracker, telegram_notify as tg, exit_manager

    entry_spy = MagicMock(return_value=True)
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: we_have_position)
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: we_have_position)
    monkeypatch.setattr(tracker, "get_available_balance",
                        lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load", lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)
    monkeypatch.setattr(
        tracker, "get_cost_on_token",
        lambda data, cid, tok: (already_bet, 0),
    )

    monkeypatch.setattr(filters, "check_signal",
                        lambda *a, **k: (True, bet_size, "ok", {"category": "geo"}))
    monkeypatch.setattr(filters, "calculate_bet_size", lambda *a, **k: bet_size)
    monkeypatch.setattr(filters, "calculate_entry_size_multiplier",
                        lambda *a, **k: (1.0, "on-time"))
    monkeypatch.setattr(filters, "get_player_invested_on_token",
                        lambda *a, **k: 8000.0)
    monkeypatch.setattr(filters, "get_player_avg_price",
                        lambda *a, **k: 0.32)
    monkeypatch.setattr(filters, "get_horizon_multiplier",
                        lambda *a, **k: (1.0, "ok"))
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda *a, **k: (0.320, 0.321))
    monkeypatch.setattr(filters, "get_max_slippage", lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-12-31T00:00:00Z"})

    # denizz_size_before controls whether denizz has prior shares on-chain
    monkeypatch.setattr(filters, "get_denizz_size_before_event",
                        lambda *a, **k: (denizz_size_before, True))
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_cache_get", lambda *a, **k: None)

    for name in ["player_buy", "skip", "entry_placed", "sell_placed",
                 "error", "signal_detected", "buy_placed", "buy_filled"]:
        if hasattr(tg, name):
            monkeypatch.setattr(tg, name, lambda *a, **k: None)

    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}

    import threading
    class FakeThread:
        def __init__(self, target=None, daemon=None, **kw):
            self._target = target
        def start(self):
            if self._target is not None:
                try:
                    self._target()
                except Exception:
                    pass
    monkeypatch.setattr(threading, "Thread", FakeThread)

    return entry_spy


def test_force_tier_upgrade_skipped_when_no_our_position(monkeypatch, log_capture):
    """denizz has 2282 shares on-chain, but WE have no position.

    Expected: _force_tier_upgrade stays False, event goes to Path A
    buffering (not tier-upgrade). No "[VARIANT1]" in log.
    """
    _prime(monkeypatch, we_have_position=False, denizz_size_before=2282.0,
           already_bet=0.0)

    main.handle_buy("denizz", _make_event(cost_usd=356.0, price=0.32))

    log = log_capture.text
    # Must NOT enter tier-upgrade path
    assert "[VARIANT1]" not in log, (
        "BUG: event entered tier-upgrade path despite us having no position.\n"
        + log
    )
    # Must see the "staying on Path A" diagnostic
    assert "WE have no position" in log or "Buffering buy" in log, (
        "Expected Path A buffering or 'no position' diagnostic; log:\n" + log
    )


def test_force_tier_upgrade_works_when_we_have_position(monkeypatch, log_capture):
    """denizz has shares on-chain + WE have an open position.

    Expected: _force_tier_upgrade=True, tier-upgrade path fires,
    "[VARIANT1]" appears in log.
    """
    entry_spy = _prime(monkeypatch, we_have_position=True,
                       denizz_size_before=2282.0, already_bet=5.50)

    main.handle_buy("denizz", _make_event(cost_usd=356.0, price=0.32))

    log = log_capture.text
    # Tier-upgrade path should fire
    assert "tier-upgrade path" in log.lower() or "TIER UPGRADE" in log, (
        "Expected tier-upgrade path; log:\n" + log
    )
    # execute_part1 should have been called with tier="upgrade"
    assert entry_spy.called, (
        "execute_part1 was not called — tier-upgrade did not fire.\n" + log
    )


def test_silent_fallthrough_now_logs(monkeypatch, log_capture):
    """Tier-upgrade path: increment >= min BUT has_position_on_event=False.

    Previously this was a silent fall-through. Now it should log
    "TIER UPGRADE SKIP: no position".
    """
    import tracker

    # We need: _is_upgrade_path=True (buf_key in _signaled_keys),
    # increment >= upgrade_min, but has_position_on_event=False.
    entry_spy = _prime(monkeypatch, we_have_position=False,
                       denizz_size_before=0.0,  # no topup detection
                       already_bet=5.50)

    # has_position_on_condition=True so _force_tier_upgrade could work,
    # but for this test we use _signaled_keys path instead.
    # Override has_position_on_event to return False specifically.
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: False)
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: True)

    buf_key = "0xHORMUZ_HORMUZ_TOK"
    main._signaled_keys["denizz"].add(buf_key)
    main._buy_buffers["denizz"][buf_key] = {
        "buys": [],
        "total_usd": 0.0,
        "notified": True,
        "first_price": 0.30,
        "last_tier_bet": 5.50,
    }

    main.handle_buy("denizz", _make_event(cost_usd=356.0, price=0.32))

    log = log_capture.text
    assert "TIER UPGRADE SKIP: no position" in log, (
        "Expected diagnostic log for tier-upgrade skip; log:\n" + log
    )
