"""Integration tests for post-close re-entry behavior (Variant B lifecycle).

After a position is closed, main._on_position_closed clears _signaled_keys +
_buy_buffers. These tests verify the NEXT handle_buy call on the same market
is classified correctly — no "Already signaled (inc -$N)" misfires, which is
exactly the 2026-04-15 US-Iran nuclear deal incident.
"""
import sys as _sys
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock  # noqa: E402
import pytest  # noqa: E402

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


def _make_event(cost_usd=600.0, price=0.31, token_id="99",
                condition_id="0xCID_TEST", title="Test market"):
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


def _prime(monkeypatch, topup_fn=None, recent_exit=None):
    """Minimal wiring so handle_buy can reach a decision without network IO."""
    import entry_manager, filters, telegram_notify as tg, exit_manager

    entry_spy = MagicMock(return_value=True)
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition",
                        lambda data, cid: False)
    monkeypatch.setattr(tracker, "has_position_on_event",
                        lambda data, slug: True)
    monkeypatch.setattr(tracker, "get_available_balance",
                        lambda data, *a, **k: 2000.0)
    monkeypatch.setattr(tracker, "load", lambda: {"positions": {}, "stats": {}})
    monkeypatch.setattr(tracker, "save", lambda data: None)

    monkeypatch.setattr(filters, "check_signal",
                        lambda *a, **k: (True, 50.0, "ok", {"category": "geo"}))
    monkeypatch.setattr(filters, "calculate_bet_size", lambda *a, **k: 100.0)
    monkeypatch.setattr(filters, "calculate_entry_size_multiplier",
                        lambda *a, **k: (1.0, "on-time"))
    monkeypatch.setattr(filters, "get_player_invested_on_token",
                        lambda *a, **k: 7000.0)
    monkeypatch.setattr(filters, "get_player_avg_price", lambda *a, **k: 0.24)
    monkeypatch.setattr(filters, "get_horizon_multiplier",
                        lambda *a, **k: (1.0, "ok"))
    monkeypatch.setattr(filters, "get_orderbook_prices",
                        lambda *a, **k: (0.30, 0.31))
    monkeypatch.setattr(filters, "get_max_slippage", lambda *a, **k: 0.05)
    monkeypatch.setattr(filters, "get_market_info",
                        lambda *a, **k: {"endDate": "2026-04-30T00:00:00Z"})

    if topup_fn is None:
        topup_fn = lambda *a, **k: (0.0, True)
    monkeypatch.setattr(filters, "get_denizz_size_before_event", topup_fn)
    monkeypatch.setattr(exit_manager, "_get_player_size_onchain",
                        lambda *a, **k: None)
    monkeypatch.setattr(exit_manager, "_cache_get", lambda *a, **k: None)

    for name in ["player_buy", "skip", "entry_placed", "sell_placed", "error",
                 "signal_detected", "buy_placed", "buy_filled"]:
        if hasattr(tg, name):
            monkeypatch.setattr(tg, name, lambda *a, **k: None)

    monkeypatch.setattr(
        main, "_recent_exit_on_market", lambda cid, token, hours=12: recent_exit
    )

    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}
    monkeypatch.setattr(main, "_save_buffers", lambda: None)
    tracker.register_on_close(main._on_position_closed)

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


def _seed_stale_state(buf_key, last_tier_bet=50.0):
    """Seed main with stale _signaled_keys + buffer entry as if a prior
    (now-closed) position had existed."""
    main._signaled_keys["denizz"].add(buf_key)
    main._buy_buffers["denizz"][buf_key] = {
        "buys": [[1.0, 300.0]],
        "total_usd": 300.0,
        "notified": True,
        "first_price": 0.40,
        "last_tier_bet": last_tier_bet,
    }


def _simulate_close(cid, token):
    """Fire the lifecycle callback the way tracker would on full close."""
    tracker._fire_on_close(cid, token, "denizz", "record_sell:auto_exit")


# ---------- 10. Path A after cleanup (no denizz shares) ----------

def test_new_denizz_buy_after_cleanup_uses_path_A(monkeypatch, log_capture):
    """After cleanup + denizz holds zero on-chain -> Path A (tier != 'upgrade')."""
    entry_spy = _prime(monkeypatch, topup_fn=lambda *a, **k: (0.0, False))

    cid, tok = "0xCID_TEST", "99"
    buf_key = f"{cid}_{tok}"
    _seed_stale_state(buf_key, last_tier_bet=50.0)
    _simulate_close(cid, tok)

    # Stale state must be gone after callback.
    assert buf_key not in main._signaled_keys["denizz"]
    assert buf_key not in main._buy_buffers["denizz"]

    main.handle_buy("denizz", _make_event(cost_usd=600.0,
                                          condition_id=cid, token_id=tok))

    assert entry_spy.called, "execute_part1 never called"
    _, kwargs = entry_spy.call_args
    assert kwargs.get("tier") != "upgrade", (
        f"expected Path A (non-upgrade tier), got {kwargs.get('tier')}"
    )
    # Path A writes buf_key back into _signaled_keys.
    assert buf_key in main._signaled_keys["denizz"]


# ---------- 11. Tier-upgrade after cleanup with last_tier_bet=0 ----------

def test_top_up_after_cleanup_goes_path_a_when_no_position(monkeypatch, log_capture):
    """After cleanup + denizz still holds shares on-chain BUT we have no
    position -> routes to Path A (new entry), NOT tier-upgrade.

    Bug fix 2026-04-16: previously _force_tier_upgrade was set purely based
    on denizz's on-chain shares, ignoring whether WE have a position.  After
    cleanup our position is closed, so tier-upgrade is wrong — Path A is the
    correct route for a fresh entry."""
    entry_spy = _prime(monkeypatch, topup_fn=lambda *a, **k: (800.0, False))

    cid, tok = "0xCID_TEST", "99"
    buf_key = f"{cid}_{tok}"
    _seed_stale_state(buf_key, last_tier_bet=50.0)
    _simulate_close(cid, tok)

    assert buf_key not in main._signaled_keys["denizz"]
    assert buf_key not in main._buy_buffers["denizz"]

    main.handle_buy("denizz", _make_event(cost_usd=600.0,
                                          condition_id=cid, token_id=tok))

    text = log_capture.text
    # Must detect top-up but route to Path A (we have no position after cleanup).
    assert "TOP-UP detected" in text
    assert "WE have no position" in text
    assert entry_spy.called
    _, kwargs = entry_spy.call_args
    # Path A creates a new entry — tier should NOT be 'upgrade'
    assert kwargs.get("tier") != "upgrade", (
        f"expected Path A (non-upgrade tier), got {kwargs.get('tier')}"
    )
    # Path A writes buf_key into _signaled_keys.
    assert buf_key in main._signaled_keys["denizz"]


# ---------- 12. Rule C still works after cleanup ----------

def test_rule_c_still_works_after_cleanup(monkeypatch, log_capture):
    """Profitable prior exit + cleanup -> Rule C ALLOW (not SKIP)."""
    recent = (datetime.now(timezone.utc) - timedelta(hours=2), 0.31, 5.0)
    entry_spy = _prime(monkeypatch,
                       topup_fn=lambda *a, **k: (0.0, False),
                       recent_exit=recent)

    cid, tok = "0xCID_TEST", "99"
    buf_key = f"{cid}_{tok}"
    _seed_stale_state(buf_key, last_tier_bet=30.0)
    _simulate_close(cid, tok)

    main.handle_buy("denizz", _make_event(cost_usd=500.0, price=0.31,
                                          condition_id=cid, token_id=tok))

    text = log_capture.text
    assert "Rule C ALLOW" in text
    assert "RULE C SKIP" not in text
    assert entry_spy.called


# ---------- 13. Reproduction of 2026-04-15 incident ----------

def test_incident_2026_04_15_reproduction_after_fix(monkeypatch, log_capture):
    """Reproduces US-Iran nuclear deal incident.

    Timeline:
      1. Bot opens position at $0.31 on denizz signal — seeds _signaled_keys
         and _buy_buffers["denizz"][buf_key] with last_tier_bet ~$17.
      2. User manually sells entire 149 sh position. record_sell fires the
         on-close callback -> state cleaned.
      3. Denizz adds $7,000 on the same market. On-chain still shows large
         denizz balance -> top-up detection routes to tier-upgrade.
      4. After fix: last_tier_bet=0 so increment = full bet (not -$17).
         Bot either enters OR is blocked by a *legitimate* filter, NOT by
         'Already signaled (inc -$17 < $5 min)'.
    """
    entry_spy = _prime(monkeypatch, topup_fn=lambda *a, **k: (5000.0, False))

    cid, tok = "0xNUCLEAR", "98765"
    buf_key = f"{cid}_{tok}"

    # Step 1 — seed as if the earlier $17 bet had executed.
    _seed_stale_state(buf_key, last_tier_bet=17.0)

    # Step 2 — fire close callback with a manual_sell reason.
    tracker._fire_on_close(cid, tok, "denizz", "record_sell:manual_sell_usiran_nuclear")

    # Post-callback: stale state gone.
    assert buf_key not in main._signaled_keys["denizz"]
    assert buf_key not in main._buy_buffers["denizz"]

    # Step 3 — denizz adds $7,000. Event cost dominates min bet threshold.
    main.handle_buy("denizz", _make_event(cost_usd=7000.0, price=0.31,
                                          condition_id=cid, token_id=tok,
                                          title="US-Iran nuclear deal by April 30"))

    text = log_capture.text
    # The specific incident log MUST NOT appear.
    assert "inc $-17" not in text
    assert "inc $-" not in text, (
        f"Negative-increment SKIP detected after fix: {text[-400:]}"
    )
    # Bot must have acted: either execute_part1 called (tier-upgrade with
    # full bet), or one of the legitimate filter SKIPs — but NOT the stale
    # "Already signaled" misclassification.
    assert "Already signaled" not in text, (
        f"Bot still hit 'Already signaled' after fix: {text[-400:]}"
    )
