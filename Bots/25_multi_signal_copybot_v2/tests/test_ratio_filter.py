"""Tests for the ratio-based noise filter that replaced MIN_BUY_EVENT_USD.

The ratio filter works as follows:
  - On-chain check runs FIRST to get _size_before (denizz's shares on this token)
  - If _size_before > TOPUP_DUST_SHARES (denizz has an existing position):
      ratio = cost_usd / (_size_before * entry_price)
      if ratio < 3% (TOPUP_RATIO_TIERS[0][1]) -> SKIP as noise
  - If _size_before <= TOPUP_DUST_SHARES (new market) -> pass ALL to buffer
  - If on-chain check returns None (RPC failure) -> SKIP (fail-safe)
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


def _make_event(cost_usd: float, price: float = 0.50,
                token_id: str = "99", condition_id: str = "0xCID_TEST"):
    size = cost_usd / price if price else 0
    return {
        "player": "denizz",
        "token_id": token_id,
        "condition_id": condition_id,
        "price": price,
        "size": size,
        "cost_usd": cost_usd,
        "title": "Test market for ratio filter",
        "outcome": "Yes",
        "event_slug": "test",
    }


def _prime_handle_buy_mocks(monkeypatch, size_before=0.0):
    """Neutralise every downstream dependency of handle_buy.

    size_before: value for get_denizz_size_before_event (shares count).
    Returns entry_spy (MagicMock for entry_manager.execute_part1).
    """
    import entry_manager, filters, tracker, telegram_notify as tg
    import main

    entry_spy = MagicMock()
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition", lambda data, cid: False)
    monkeypatch.setattr(tracker, "has_position_on_event", lambda data, slug: False)
    monkeypatch.setattr(tracker, "get_available_balance", lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load", lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)

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

    # On-chain top-up detection
    if size_before is None:
        monkeypatch.setattr(filters, "get_denizz_size_before_event",
                            lambda *a, **k: (None, False))
    else:
        monkeypatch.setattr(filters, "get_denizz_size_before_event",
                            lambda *a, **k: (size_before, True))

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

    return entry_spy


# ---------- tests ----------

def test_noise_topup_skipped(monkeypatch, log_capture):
    """Denizz has 20000 shares @ $0.35 ($7000 position), buys $2
    (ratio = 2 / 7000 = 0.03%) -> SKIP noise topup."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=20000.0)

    ev = _make_event(cost_usd=2.0, price=0.35)
    main.handle_buy("denizz", ev)

    assert "SKIP: noise topup" in log_capture.text
    assert "0.0%" in log_capture.text  # ratio rounds to 0.0%
    entry_spy.assert_not_called()


def test_noise_topup_boundary_3pct_passes(monkeypatch, log_capture):
    """Denizz has 1000 shares @ $0.50 ($500 position), buys $15
    (ratio = 15 / 500 = 3.0%) -> NOT skip (boundary, >= 3%)."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=1000.0)

    ev = _make_event(cost_usd=15.0, price=0.50)
    main.handle_buy("denizz", ev)

    assert "noise topup" not in log_capture.text


def test_new_market_no_shares_passes_to_buffer(monkeypatch, log_capture):
    """Denizz has NO shares (_size_before=0), buys $100 -> event passes
    through to buffer (Buffering buy #1)."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=0.0)

    ev = _make_event(cost_usd=100.0, price=0.50)
    main.handle_buy("denizz", ev)

    assert "noise topup" not in log_capture.text
    assert "Buffering buy #1" in log_capture.text
    entry_spy.assert_not_called()  # below MIN_PLAYER_INVESTED, stays in buffer


def test_new_market_small_buys_accumulate(monkeypatch, log_capture):
    """Denizz has no shares, 4 buys of $150 each -> buffer accumulates
    $600 -> passes MIN_PLAYER_INVESTED ($500) on buy #4."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=0.0)

    for i in range(3):
        main.handle_buy("denizz", _make_event(cost_usd=150.0, price=0.50))

    text = log_capture.text
    assert "Buffering buy #1" in text
    assert "Buffering buy #2" in text
    assert "Buffering buy #3" in text

    # 4th buy pushes total to $600, which exceeds MIN_PLAYER_INVESTED ($500)
    main.handle_buy("denizz", _make_event(cost_usd=150.0, price=0.50))

    text = log_capture.text
    # Should have crossed the threshold and reached SIGNAL path
    assert "SIGNAL from denizz" in text


def test_large_topup_25pct_passes(monkeypatch, log_capture):
    """Denizz has 4500 shares @ $0.32 ($1440 position), buys $356
    (ratio = 356 / 1440 = 24.7%) -> passes filter."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=4500.0)

    ev = _make_event(cost_usd=356.0, price=0.32)
    main.handle_buy("denizz", ev)

    assert "noise topup" not in log_capture.text


def test_rpc_failure_skips_event(monkeypatch, log_capture):
    """On-chain check returns None -> SKIP (fail-safe)."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=None)

    ev = _make_event(cost_usd=500.0, price=0.50)
    main.handle_buy("denizz", ev)

    assert "top-up detection RPC failed" in log_capture.text
    assert "fail-safe" in log_capture.text
    entry_spy.assert_not_called()


def test_rule_c_micro_buy_blocked_by_ratio(monkeypatch, log_capture):
    """$2 buy, denizz has shares (20000 @ $0.50 = $10000), ratio < 3%
    -> SKIP. Verify Rule C path is NOT reached (execute_part1 not called)."""
    import main
    entry_spy = _prime_handle_buy_mocks(monkeypatch, size_before=20000.0)

    # Simulate recent profitable exit so Rule C WOULD allow re-entry
    monkeypatch.setattr(main, "_recent_exit_on_market",
                        lambda cid, token, hours=2: (
                            __import__('datetime').datetime.now(
                                __import__('datetime').timezone.utc),
                            0.50, 5.0,
                        ))

    ev = _make_event(cost_usd=2.0, price=0.50)
    main.handle_buy("denizz", ev)

    assert "SKIP: noise topup" in log_capture.text
    assert "Rule C" not in log_capture.text
    entry_spy.assert_not_called()
