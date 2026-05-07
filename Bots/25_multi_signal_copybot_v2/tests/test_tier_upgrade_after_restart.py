"""Regression test for the 2026-04-16 tier-upgrade-after-restart bug.

Bug reproduction:
    1. Bot opens a denizz position at 22:44 (cost_usd=$5.50 — tiny tier-1 entry).
    2. Bot is restarted at 22:56. `_rehydrate_from_tracker` runs:
         - `_signaled_keys[denizz]` gets the buf_key (Direction 1).
         - `_buy_buffers[denizz][buf_key]` is recreated with
           `buys=[]`, `total_usd=0`, `last_tier_bet=cost_usd`.
    3. At 00:01:23 denizz tops up $269 @ 0.272 on the SAME token.
    4. Expected: tier-upgrade branch fires, execute_part1(tier="upgrade").
    5. Observed (buggy): because `buf["total_usd"] = 269 < MIN_PLAYER_INVESTED=500`,
       the `if total_spent < min_invested: return` on-line-493 path fires FIRST,
       so the bot just logs "Buffering buy #1" and drops the event.

The current code has the two guards in this order:
        if total_spent < min_invested:       # <-- wins, wrongly
            return
        if buf_key in _signaled_keys[...] or _force_tier_upgrade:
            ... tier upgrade ...

This test intentionally arranges a buffer that mirrors what `_rehydrate_from_tracker`
leaves behind (empty `buys`, `last_tier_bet>0`, buf_key in `_signaled_keys`) and
a $269 buy event. It asserts the tier-upgrade branch fires.

NOTE: The test is expected to FAIL against the CURRENT main.py and PASS after the
proposed fix ("apply min_invested gate only for NEW signals, not tier upgrades").
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


def _make_event(cost_usd, price, token_id="URAN_TOK", condition_id="0xURAN",
                title="Iran uranium"):
    return {
        "player": "denizz",
        "token_id": token_id,
        "condition_id": condition_id,
        "price": price,
        "size": cost_usd / price,
        "cost_usd": cost_usd,
        "title": title,
        "outcome": "Yes",
        "event_slug": "iran-uranium",
    }


def _prime(monkeypatch, topup_fn=None, bet_size=20.0, already_bet=5.50):
    """Wire every downstream dep used by handle_buy."""
    import entry_manager, filters, tracker, telegram_notify as tg, exit_manager

    entry_spy = MagicMock(return_value=True)
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: True)
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: True)
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
                        lambda *a, **k: 0.27)
    monkeypatch.setattr(filters, "get_horizon_multiplier",
                        lambda *a, **k: (1.0, "ok"))
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda *a, **k: (0.272, 0.273))
    monkeypatch.setattr(filters, "get_max_slippage", lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-12-31T00:00:00Z"})

    if topup_fn is None:
        topup_fn = lambda *a, **k: (2000.0, True)
    monkeypatch.setattr(filters, "get_denizz_size_before_event", topup_fn)
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


def test_tier_upgrade_fires_after_restart_rehydrate(monkeypatch, log_capture):
    """Reproduce the 2026-04-16 Iran-uranium incident.

    State after restart+rehydrate:
      buf_key in _signaled_keys[denizz]  (Direction 1 of rehydrate)
      buf["buys"] = []                   (rehydrated empty)
      buf["total_usd"] = 0
      buf["last_tier_bet"] = 5.50        (synced from tracker cost)

    Incoming event: denizz tops up $269 @ 0.272 on same token.
    Expected: tier-upgrade branch fires, execute_part1(tier="upgrade").
    """
    entry_spy = _prime(monkeypatch, already_bet=5.50, bet_size=25.0)

    # Simulate post-rehydrate state exactly
    buf_key = "0xURAN_URAN_TOK"
    main._signaled_keys["denizz"].add(buf_key)
    main._buy_buffers["denizz"][buf_key] = {
        "buys": [],
        "total_usd": 0.0,
        "notified": True,
        "first_price": 0.25,
        "last_tier_bet": 5.50,
    }

    main.handle_buy("denizz", _make_event(cost_usd=269.0, price=0.272))

    # Must NOT buffer — the buffering log is the bug signature.
    assert "Buffering buy" not in log_capture.text, (
        "REGRESSION: small top-up after restart was buffered instead of "
        "routed to tier-upgrade. Log:\n" + log_capture.text
    )

    # Tier-upgrade branch must fire.
    assert entry_spy.called, (
        "execute_part1 was never called — tier-upgrade branch did not run.\n"
        + log_capture.text
    )
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") == "upgrade", (
        f"expected tier='upgrade', got {kwargs.get('tier')!r}\n"
        + log_capture.text
    )


def test_new_signal_still_buffers_below_min_invested(monkeypatch, log_capture):
    """Regression guard for the complementary path: a NEW signal (buf_key NOT
    in _signaled_keys, no prior on-chain shares) that accumulates below
    MIN_PLAYER_INVESTED must still buffer and wait — the existing semantics
    for Path A must not change after the fix.
    """
    entry_spy = _prime(
        monkeypatch,
        topup_fn=lambda *a, **k: (0.0, False),  # no prior shares
        bet_size=100.0,
        already_bet=0.0,
    )
    # Fresh state: _buy_buffers and _signaled_keys both empty (from _prime).

    main.handle_buy("denizz", _make_event(cost_usd=200.0, price=0.50))

    assert "Buffering buy" in log_capture.text, (
        "Expected buffering for sub-$500 new signal; log:\n" + log_capture.text
    )
    entry_spy.assert_not_called()
