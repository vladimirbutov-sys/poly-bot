"""Tests for the ratio-based noise filter in main.handle_buy.

History: originally tested MIN_BUY_EVENT_USD ($150 absolute filter).
Updated 2026-04-15 to test the replacement ratio filter:
  - If denizz has existing shares (> TOPUP_DUST_SHARES), a buy < 3%
    of his position value is classified as noise and SKIPped.
  - If denizz has NO shares (new market), ALL buys pass to the buffer.
"""
import sys as _sys
# Import main BEFORE pytest wraps stdout. main.py sets sys.stdout=_PrintToLog
# at import time; doing this here (at module-collection time) ensures pytest's
# capsys can still wrap cleanly for each test afterwards.
_real_stdout = _sys.stdout
import main  # noqa: E402
# Restore original stdout so capsys works in each test
_sys.stdout = _real_stdout

import logging  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402
import pytest  # noqa: E402


class _CapsysProxy:
    """Thin adapter that reads the latest capsys.readouterr() snapshot."""
    def __init__(self, capsys):
        self._capsys = capsys
    @property
    def text(self):
        # readouterr() consumes the buffer, so accumulate
        out = self._capsys.readouterr()
        self._acc = getattr(self, "_acc", "") + (out.out or "") + (out.err or "")
        return self._acc


@pytest.fixture
def log_capture(capsys):
    """Use pytest's capsys — it captures bot output reliably even after
    main.py's sys.stdout hijack (pytest captures at fd level)."""
    return _CapsysProxy(capsys)


def _make_event(cost_usd: float):
    """Build a minimal BUY event dict resembling what monitor produces."""
    return {
        "player": "denizz",
        "token_id": "99",
        "condition_id": "0xCID_TEST",
        "price": 0.50,
        "size": 100,
        "cost_usd": cost_usd,
        "title": "Test market",
        "outcome": "Yes",
        "event_slug": "test",
    }


def _prime_handle_buy_mocks(monkeypatch, size_before=0.0):
    """Neutralise every downstream dependency of handle_buy.

    Spy `entry_manager.execute_part1` — tests assert whether it was called.
    All other deps return neutral values so handle_buy doesn't crash.

    size_before: value returned by get_denizz_size_before_event (shares).
    """
    import entry_manager, filters, tracker, telegram_notify as tg
    import main

    entry_spy = MagicMock()
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    # tracker.can_open_new -> always allowed
    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition", lambda data, cid: False)
    monkeypatch.setattr(tracker, "has_position_on_event", lambda data, slug: False)
    monkeypatch.setattr(tracker, "get_available_balance", lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load", lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)

    # filters: let check_signal say "passed, bet $50"
    monkeypatch.setattr(filters, "check_signal",
                        lambda *a, **k: (True, 50.0, "ok", {}))
    monkeypatch.setattr(filters, "calculate_bet_size",
                        lambda *a, **k: 100.0)
    monkeypatch.setattr(filters, "calculate_entry_size_multiplier",
                        lambda *a, **k: (1.0, "on-time"))
    monkeypatch.setattr(filters, "get_player_invested_on_token",
                        lambda *a, **k: 7000.0)
    monkeypatch.setattr(filters, "get_player_avg_price",
                        lambda *a, **k: 0.24)
    monkeypatch.setattr(filters, "get_horizon_multiplier",
                        lambda *a, **k: (1.0, "ok"))
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda *a, **k: (0.50, 0.51))
    monkeypatch.setattr(filters, "get_max_slippage",
                        lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-04-30T00:00:00Z"})
    # On-chain top-up detection: controllable size_before
    monkeypatch.setattr(filters, "get_denizz_size_before_event",
                        lambda *a, **k: (size_before, True))

    # tg notifications are no-ops
    for name in ["player_buy", "skip", "entry_placed", "sell_placed", "error"]:
        if hasattr(tg, name):
            monkeypatch.setattr(tg, name, lambda *a, **k: None)

    # Clear signal buffers & signaled_keys per test
    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}

    # Prevent actual thread spawn from entry path
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


# ---------- tests ----------

def test_skip_noise_topup_blocks_entry(monkeypatch, log_capture):
    """$2 event on $7000 position (ratio=0.06%) -> SKIP noise topup;
    execute_part1 never called (today's incident)."""
    import main
    # 20000 shares @ $0.35 = $7000 position
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=20000.0)

    ev = _make_event(cost_usd=2.0)
    ev["price"] = 0.35
    main.handle_buy("denizz", ev)

    assert "SKIP: noise topup" in log_capture.text
    entry_spy.assert_not_called()


def test_buy_above_noise_threshold_passes_filter(monkeypatch, log_capture):
    """$150 buy on $5000 position (ratio=3%) passes the filter (>= 3%)."""
    import main
    # 10000 shares @ $0.50 = $5000 position
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=10000.0)

    main.handle_buy("denizz", _make_event(cost_usd=150.0))

    assert "noise topup" not in log_capture.text


def test_new_market_small_buy_passes_to_buffer(monkeypatch, log_capture):
    """No prior shares (new market), $100 buy -> passes to buffer,
    not blocked by ratio filter."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=0.0)

    main.handle_buy("denizz", _make_event(cost_usd=100.0))

    assert "noise topup" not in log_capture.text
    # Should be buffering (below MIN_PLAYER_INVESTED)
    assert "Buffering buy" in log_capture.text


def test_noise_topup_blocks_re_entry_via_rule_c(monkeypatch, log_capture):
    """Even if a profitable previous exit would allow Rule C re-entry,
    a noise topup (ratio < 3%) is still blocked by the ratio filter."""
    import main
    # 20000 shares @ $0.50 = $10000 position
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=20000.0)

    # Simulate recent profitable exit so Rule C WOULD allow re-entry
    monkeypatch.setattr(main, "_recent_exit_on_market",
                        lambda cid, token, hours=2: (
                            __import__('datetime').datetime.now(
                                __import__('datetime').timezone.utc),
                            0.50, 5.0,  # exit price, profitable PnL
                        ))

    main.handle_buy("denizz", _make_event(cost_usd=100.0))

    assert "SKIP: noise topup" in log_capture.text
    assert "Rule C ALLOW" not in log_capture.text  # never reached Rule C
    entry_spy.assert_not_called()


def test_noise_topup_blocks_tier_upgrade(monkeypatch, log_capture):
    """Even if position is already signaled (tier-upgrade path), a
    noise topup is blocked by the ratio filter."""
    import main
    # 20000 shares @ $0.50 = $10000 position
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=20000.0)
    buf_key = "0xCID_TEST_99"
    main._signaled_keys["denizz"].add(buf_key)

    main.handle_buy("denizz", _make_event(cost_usd=100.0))

    assert "SKIP: noise topup" in log_capture.text
    assert "TIER UPGRADE" not in log_capture.text
    assert "Already signaled" not in log_capture.text
    entry_spy.assert_not_called()


def test_buy_large_event_passes_filter(monkeypatch, log_capture):
    """$500 event on $5000 position (ratio=10%) -> passes filter."""
    import main
    # 10000 shares @ $0.50 = $5000 position
    _prime_handle_buy_mocks(monkeypatch, size_before=10000.0)

    main.handle_buy("denizz", _make_event(cost_usd=500.0))

    assert "noise topup" not in log_capture.text


def test_min_upgrade_usd_still_works_independently(monkeypatch, log_capture):
    """Regression: the two filters coexist.
    Event $200 passes ratio filter (big enough ratio). Tier-upgrade path is
    reached. If our calculated increment ends up < MIN_UPGRADE_USD ($5),
    the tier-upgrade MUST still skip with the existing 'Already signaled'
    log (proving that filter didn't disappear).
    """
    import main, filters
    # 1000 shares @ $0.50 = $500 position. $200 buy = 40% ratio -> passes
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=1000.0)
    # Position is already signaled (forces tier-upgrade branch)
    buf_key = f"0xCID_TEST_99"
    main._signaled_keys["denizz"].add(buf_key)
    # Force tiny increment: calculate_bet_size returns identical to already_bet.
    monkeypatch.setattr(filters, "calculate_bet_size", lambda *a, **k: 0.5)
    # Seed the buffer so already_bet exists
    from config import MIN_PLAYER_INVESTED
    buf = main._get_buf("denizz", buf_key, 0.50)
    buf["last_tier_bet"] = 0.0   # so increment = 0.5 - 0 = 0.5, < MIN_UPGRADE_USD=5
    buf["total_usd"] = 10000    # already past MIN_PLAYER_INVESTED
    buf["notified"] = True

    main.handle_buy("denizz", _make_event(cost_usd=200.0))

    assert "noise topup" not in log_capture.text   # ratio filter OK-ed it
    assert "Already signaled" in log_capture.text   # old filter still engaged
    entry_spy.assert_not_called()
