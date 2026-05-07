"""Tests for on-chain top-up detection in main.handle_buy.

Bugfix #1 context (2026-04-15): 82% of denizz's $100-500 BUY events are
top-ups to his existing positions. The bot used to classify "new vs
top-up" from our internal `_signaled_keys` state, which misses cases
where denizz held a position for months before our bot ever saw it.
The fix is an on-chain CTF.balanceOf check that routes such events to
the existing tier-upgrade branch instead of Path A.

All tests MUST mock the on-chain helper. No real RPC calls.
"""
import sys as _sys
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

import logging  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402
import pytest  # noqa: E402


class _CapsysProxy:
    """Accumulating wrapper around pytest capsys so multiple reads see the
    full output of a test run."""
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
                size: float = None, token_id: str = "99",
                condition_id: str = "0xCID_TEST"):
    """Minimal BUY event dict matching monitor's shape."""
    if size is None:
        size = cost_usd / price
    return {
        "player": "denizz",
        "token_id": token_id,
        "condition_id": condition_id,
        "price": price,
        "size": size,
        "cost_usd": cost_usd,
        "title": "Test market",
        "outcome": "Yes",
        "event_slug": "test",
    }


def _prime(monkeypatch, topup_fn=None, we_have_position=False):
    """Mock every downstream dep of handle_buy. Return (entry_spy, rpc_spy).

    topup_fn: replacement for filters.get_denizz_size_before_event. If None,
    uses default (0.0, True) = "no prior shares, cache hit" which keeps the
    existing tests' Path A branch alive.
    we_have_position: whether tracker reports an open position on this condition.
    """
    import entry_manager, filters, tracker, telegram_notify as tg, exit_manager
    import main

    entry_spy = MagicMock(return_value=True)
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: we_have_position)
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: we_have_position)
    monkeypatch.setattr(tracker, "get_available_balance", lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load", lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)

    monkeypatch.setattr(filters, "check_signal",
                        lambda *a, **k: (True, 50.0, "ok", {}))
    monkeypatch.setattr(filters, "calculate_bet_size", lambda *a, **k: 100.0)
    monkeypatch.setattr(filters, "calculate_entry_size_multiplier",
                        lambda *a, **k: (1.0, "on-time"))
    monkeypatch.setattr(filters, "get_player_invested_on_token", lambda *a, **k: 7000.0)
    monkeypatch.setattr(filters, "get_player_avg_price", lambda *a, **k: 0.24)
    monkeypatch.setattr(filters, "get_horizon_multiplier", lambda *a, **k: (1.0, "ok"))
    monkeypatch.setattr(filters, "get_orderbook_prices", lambda *a, **k: (0.50, 0.51))
    monkeypatch.setattr(filters, "get_max_slippage", lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-04-30T00:00:00Z"})

    # RPC spy wired through exit_manager — the L2 branch of
    # get_denizz_size_before_event routes here. Tests that exercise cache
    # hits verify this spy was NOT called.
    rpc_spy = MagicMock(return_value=None)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain", rpc_spy)
    monkeypatch.setattr(exit_manager, "_cache_get", lambda *a, **k: None)

    if topup_fn is not None:
        monkeypatch.setattr(filters, "get_denizz_size_before_event", topup_fn)
    else:
        monkeypatch.setattr(filters, "get_denizz_size_before_event",
                            lambda *a, **k: (0.0, True))

    for name in ["player_buy", "skip", "entry_placed", "sell_placed", "error",
                 "signal_detected", "buy_placed", "buy_filled"]:
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

    return entry_spy, rpc_spy


# ---------- tests ----------

def test_topup_detected_routes_to_tier_upgrade_path(monkeypatch, log_capture):
    """On-chain shows 1000 shares, no prior _signaled_keys entry -> route
    to the tier-upgrade branch (not Path A). Assert via the log line and
    via execute_part1 having been invoked with tier='upgrade'."""
    import main
    entry_spy, _ = _prime(monkeypatch,
                          topup_fn=lambda *a, **k: (1000.0, False),
                          we_have_position=True)

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    assert "TOP-UP detected" in log_capture.text
    assert "routing to tier-upgrade path" in log_capture.text
    # Tier-upgrade branch must have reached execute_part1 with tier='upgrade'
    assert entry_spy.called, "execute_part1 was never called"
    # tier kw-arg is 'upgrade' in tier-upgrade branch, not 'B'/'S'/'A'
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") == "upgrade", \
        f"expected tier='upgrade', got {kwargs.get('tier')}"


def test_new_entry_when_denizz_has_no_shares(monkeypatch, log_capture):
    """Zero shares on-chain -> Path A as before. No top-up log, tier!=upgrade."""
    import main
    entry_spy, _ = _prime(monkeypatch,
                          topup_fn=lambda *a, **k: (0.0, False))

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    assert "TOP-UP detected" not in log_capture.text
    assert entry_spy.called
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") != "upgrade"


def test_dust_balance_treated_as_new_entry(monkeypatch, log_capture):
    """2 shares is below TOPUP_DUST_SHARES (5.0) -> Path A, no top-up log."""
    import main
    entry_spy, _ = _prime(monkeypatch,
                          topup_fn=lambda *a, **k: (2.0, False))

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    assert "TOP-UP detected" not in log_capture.text
    assert entry_spy.called
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") != "upgrade"


def test_rpc_failure_triggers_fail_safe_skip(monkeypatch, log_capture):
    """Helper returns None -> SKIP logged, execute_part1 NOT called."""
    import main
    entry_spy, _ = _prime(monkeypatch,
                          topup_fn=lambda *a, **k: (None, False))

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    assert "top-up detection RPC failed" in log_capture.text
    assert "fail-safe" in log_capture.text
    entry_spy.assert_not_called()


def test_cached_size_used_when_available(monkeypatch, log_capture):
    """When L1 cache has a value, the L2 RPC helper must NOT be invoked.

    This exercises the real filters.get_denizz_size_before_event (we do NOT
    override it with a fake). We seed exit_manager._cache_get to return 1500
    shares and assert exit_manager._get_player_size_onchain was untouched.
    """
    import main, exit_manager, filters

    # Capture the REAL function BEFORE _prime monkeypatches it.
    real_fn = filters.get_denizz_size_before_event

    entry_spy, _ = _prime(monkeypatch, topup_fn=None)
    # Restore the real implementation so we truly exercise it
    monkeypatch.setattr(filters, "get_denizz_size_before_event", real_fn)

    # L1 cache hit
    monkeypatch.setattr(exit_manager, "_cache_get",
                        lambda player, cid, tok: 1500.0)
    # Spy: L2 RPC must not be called
    rpc_spy = MagicMock(return_value=None)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain", rpc_spy)

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    rpc_spy.assert_not_called()
    # And because size_before (1500 - ~1200_event = ~300) > dust, we should
    # see the top-up log too.
    assert "TOP-UP detected cache" in log_capture.text


def test_topup_detected_with_existing_signal_goes_tier_upgrade_as_before(
        monkeypatch, log_capture):
    """Classic case: buf_key already in _signaled_keys AND denizz holds
    shares on-chain. Behavior identical to pre-bugfix: tier-upgrade path
    fires, and we do NOT emit the new TOP-UP routing log (it's redundant)."""
    import main
    entry_spy, _ = _prime(monkeypatch,
                          topup_fn=lambda *a, **k: (800.0, True),
                          we_have_position=True)

    # Pre-existing signal entry (e.g. left over from an earlier handle_buy
    # that already ran Path A on this market).
    buf_key = "0xCID_TEST_99"
    main._signaled_keys["denizz"].add(buf_key)

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    # New log must NOT appear — we didn't need to "force" the route.
    assert "TOP-UP detected" not in log_capture.text
    # But tier-upgrade branch still executed.
    assert entry_spy.called
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") == "upgrade"


def test_l2_rpc_used_on_cache_miss(monkeypatch, log_capture):
    """Cache miss (L1 returns None) -> L2 CTF.balanceOf is called. Exercise
    the real filters.get_denizz_size_before_event so both branches are
    actually covered (not just mocked away)."""
    import main, exit_manager, filters

    real_fn = filters.get_denizz_size_before_event
    entry_spy, _ = _prime(monkeypatch, topup_fn=None)
    monkeypatch.setattr(filters, "get_denizz_size_before_event", real_fn)

    monkeypatch.setattr(exit_manager, "_cache_get", lambda *a, **k: None)
    rpc_spy = MagicMock(return_value=2500.0)  # 2500 shares on-chain
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain", rpc_spy)

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    rpc_spy.assert_called_once()
    assert "TOP-UP detected on-chain" in log_capture.text


def test_l2_rpc_returns_none_fails_safe(monkeypatch, log_capture):
    """Cache miss + RPC returns None -> real helper propagates None, caller
    SKIPs. Covers the `if onchain is None: return None, False` branch."""
    import main, exit_manager, filters

    real_fn = filters.get_denizz_size_before_event
    entry_spy, _ = _prime(monkeypatch, topup_fn=None)
    monkeypatch.setattr(filters, "get_denizz_size_before_event", real_fn)

    monkeypatch.setattr(exit_manager, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda *a, **k: None)

    main.handle_buy("denizz", _make_event(cost_usd=600.0))

    assert "top-up detection RPC failed" in log_capture.text
    entry_spy.assert_not_called()


def test_noise_topup_skipped_by_ratio_filter(monkeypatch, log_capture):
    """When denizz has a large position and buys tiny (ratio < 3%), the ratio
    filter skips the event as noise. On-chain check DOES run (it's upstream
    of ratio filter now), but no entry is placed."""
    import main
    # denizz has 9999 shares; at price $0.50 that's $4999. A $50 buy = 1% ratio
    entry_spy, _ = _prime(monkeypatch,
                          topup_fn=lambda *a, **k: (9999.0, False))

    main.handle_buy("denizz", _make_event(cost_usd=50.0))

    assert "SKIP: noise topup" in log_capture.text
    entry_spy.assert_not_called()
