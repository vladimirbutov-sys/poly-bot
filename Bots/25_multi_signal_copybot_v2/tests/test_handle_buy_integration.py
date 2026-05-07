"""End-to-end regression tests for main.handle_buy after Bugfix #1.

These tests stitch the full decision pipeline together (on-chain top-up
detection -> ratio noise filter -> tier-upgrade vs Path A branching ->
Rule C whipsaw protection -> check_signal gate -> execute_part1) and
verify the downstream behavior is unchanged for the scenarios the bot
handles in production. All network/RPC calls are mocked.
"""
import sys as _sys
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

from datetime import datetime, timezone
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


def _make_event(cost_usd: float = 600.0, price: float = 0.50,
                token_id: str = "99", condition_id: str = "0xCID_TEST",
                title: str = "Test market"):
    return {
        "player": "denizz",
        "token_id": token_id,
        "condition_id": condition_id,
        "price": price,
        "size": cost_usd / price,
        "cost_usd": cost_usd,
        "title": title,
        "outcome": "Yes",
        "event_slug": "test",
    }


def _prime(monkeypatch,
           topup_fn=None,
           check_signal_fn=None,
           horizon_fn=None,
           has_open_position: bool = False):
    """Wire the complete dependency surface of handle_buy.

    Defaults imply a 'happy path' new signal: no prior denizz shares,
    check_signal passes, horizon allows, tracker is empty, no recent exit.
    Tests override individual knobs to simulate each scenario.
    """
    import entry_manager, filters, tracker, telegram_notify as tg, exit_manager
    import main

    entry_spy = MagicMock(return_value=True)
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: has_open_position)
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: True)
    monkeypatch.setattr(tracker, "get_available_balance",
                        lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load", lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)

    if check_signal_fn is None:
        check_signal_fn = lambda *a, **k: (True, 50.0, "ok", {"category": "geo"})
    monkeypatch.setattr(filters, "check_signal", check_signal_fn)

    monkeypatch.setattr(filters, "calculate_bet_size", lambda *a, **k: 100.0)
    monkeypatch.setattr(filters, "calculate_entry_size_multiplier",
                        lambda *a, **k: (1.0, "on-time"))
    monkeypatch.setattr(filters, "get_player_invested_on_token",
                        lambda *a, **k: 7000.0)
    monkeypatch.setattr(filters, "get_player_avg_price", lambda *a, **k: 0.24)
    if horizon_fn is None:
        horizon_fn = lambda *a, **k: (1.0, "ok")
    monkeypatch.setattr(filters, "get_horizon_multiplier", horizon_fn)
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda *a, **k: (0.50, 0.51))
    monkeypatch.setattr(filters, "get_max_slippage", lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-04-30T00:00:00Z"})

    # Default top-up detector: no prior shares (Path A).
    if topup_fn is None:
        topup_fn = lambda *a, **k: (0.0, True)
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


# ---------- tests ----------

def test_full_flow_new_signal_first_time(monkeypatch, log_capture):
    """Fresh market, first-ever denizz buy, on-chain = 0 -> Path A opens
    a new position. Verify execute_part1 called with NON-upgrade tier and
    _signaled_keys now contains the buf_key (existing Path A behavior).
    """
    import main
    entry_spy = _prime(monkeypatch,
                       topup_fn=lambda *a, **k: (0.0, False))

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    assert "TOP-UP detected" not in log_capture.text
    assert "SIGNAL from denizz" in log_capture.text
    assert entry_spy.called
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") != "upgrade"
    # Path A writes to _signaled_keys
    assert "0xCID_TEST_99" in main._signaled_keys["denizz"]


def test_full_flow_tier_upgrade_from_signaled_keys(monkeypatch, log_capture):
    """Pre-existing signaled entry + denizz on-chain shows prior size ->
    classic tier-upgrade path. Rule A+ returns 1.0 (on-time), horizon ok,
    increment passes MIN_UPGRADE_USD -> execute_part1(tier='upgrade').
    """
    import main
    entry_spy = _prime(monkeypatch,
                       topup_fn=lambda *a, **k: (800.0, True))

    # Pre-seed the buffer + signaled key like an earlier entry would have.
    # _prune_buffer recomputes total_usd from buys[], so we must inject
    # a recent-enough entry rather than just setting total_usd directly.
    import time as _t
    buf_key = "0xCID_TEST_99"
    main._signaled_keys["denizz"].add(buf_key)
    buf = main._get_buf("denizz", buf_key, 0.50)
    buf["buys"] = [[_t.time(), 10000.0]]
    buf["total_usd"] = 10000.0
    buf["last_tier_bet"] = 50.0
    buf["notified"] = True

    main.handle_buy("denizz", _make_event(cost_usd=300.0))

    # Tier upgrade branch log
    assert "TIER UPGRADE" in log_capture.text
    assert entry_spy.called
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") == "upgrade"


def test_full_flow_rule_c_re_entry_still_works(monkeypatch, log_capture):
    """We closed profitably; denizz re-enters; on-chain = 0 (he sold earlier).
    Rule C ALLOW must fire (not SKIP) because previous exit was profitable.
    Path A opens a fresh position.
    """
    import main
    entry_spy = _prime(monkeypatch,
                       topup_fn=lambda *a, **k: (0.0, False))

    # Simulate a recent PROFITABLE exit on this market
    monkeypatch.setattr(
        main, "_recent_exit_on_market",
        lambda cid, token, hours=12: (
            datetime.now(timezone.utc), 0.50, 5.0,  # exit price 0.50, +$5 PnL
        ),
    )

    main.handle_buy("denizz", _make_event(cost_usd=500.0))

    assert "Rule C ALLOW" in log_capture.text
    assert "RULE C SKIP" not in log_capture.text
    assert entry_spy.called


def test_full_flow_excluded_keyword_still_blocks(monkeypatch, log_capture):
    """check_signal returns passed=False with reason about excluded keyword
    -> handle_buy respects that and SKIPs. No execute_part1. The on-chain
    check still runs (it's upstream of the ratio filter) but that's fine."""
    import main
    entry_spy = _prime(
        monkeypatch,
        topup_fn=lambda *a, **k: (0.0, False),
        check_signal_fn=lambda *a, **k: (False, 0.0, "excluded keyword: BTC", {}),
    )

    main.handle_buy("denizz",
                    _make_event(cost_usd=600.0, title="Bitcoin above 100k"))

    assert "SKIP" in log_capture.text
    assert "excluded keyword" in log_capture.text
    entry_spy.assert_not_called()


def test_full_flow_horizon_block_still_works(monkeypatch, log_capture):
    """Event on a far-horizon market (e.g. 300 days out). For a NEW ENTRY
    Path A delegates horizon handling to check_signal — we simulate that
    path by having check_signal SKIP with a horizon reason. execute_part1
    is never called.
    """
    import main
    entry_spy = _prime(
        monkeypatch,
        topup_fn=lambda *a, **k: (0.0, False),
        check_signal_fn=lambda *a, **k: (False, 0.0,
                                         "horizon blocked (300d >= 120d)", {}),
        horizon_fn=lambda *a, **k: (0.0, "horizon blocked (300d >= 120d)"),
    )

    main.handle_buy("denizz",
                    _make_event(cost_usd=600.0, title="Far future market"))

    assert "SKIP" in log_capture.text
    assert "horizon" in log_capture.text
    entry_spy.assert_not_called()
