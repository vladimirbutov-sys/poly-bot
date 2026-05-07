"""Tests for main._rehydrate_from_tracker stale-buffer cleanup (2026-04-15 fix).

Background: before this patch, rehydrate only cleaned _signaled_keys but left
stale entries inside _buy_buffers[player]. On restart those stale entries —
many with last_tier_bet > 0 — would be treated as anchor points for the next
tier-upgrade size calculation, producing negative increments.

These tests mock tracker.load() so they do NOT touch disk or the network.
"""
import sys as _sys
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

from unittest.mock import patch  # noqa: E402


def _positions_doc(open_positions):
    """Build a tracker.load()-shaped dict from a list of (oid, cid, tok, player, status)."""
    positions = {}
    for oid, cid, tok, player, status in open_positions:
        positions[oid] = {
            "condition_id": cid,
            "token_id": tok,
            "signal_player": player,
            "status": status,
            "cost_usd": 100.0,
            "avg_entry": 0.5,
        }
    return {"positions": positions}


def test_rehydrate_drops_stale_buffer_with_ltb_positive():
    """An entry with last_tier_bet>0 for a closed position must be removed entirely."""
    # Arrange: inject one stale buffer (no matching open position)
    main._buy_buffers["denizz"].clear()
    main._signaled_keys["denizz"].clear()
    stale_key = "0xSTALE_CID_1"
    main._buy_buffers["denizz"][stale_key] = {
        "buys": [], "total_usd": 0.0, "notified": True,
        "first_price": 0.5, "last_tier_bet": 75.0,
    }

    # tracker sees NO open positions
    with patch("main.tracker.load", return_value=_positions_doc([])), \
         patch("main._save_buffers"):
        main._rehydrate_from_tracker()

    # Act + Assert
    assert stale_key not in main._buy_buffers["denizz"], \
        "stale buffer entry with ltb>0 must be purged entirely (not just reset)"


def test_rehydrate_keeps_legitimate_open_buffer():
    """An entry whose buf_key matches an open position must be preserved as-is."""
    main._buy_buffers["denizz"].clear()
    main._signaled_keys["denizz"].clear()
    live_key = "0xOPEN_CID_1_99"
    main._buy_buffers["denizz"][live_key] = {
        "buys": [], "total_usd": 0.0, "notified": True,
        "first_price": 0.4, "last_tier_bet": 120.0,
    }

    with patch("main.tracker.load",
               return_value=_positions_doc([("o1", "0xOPEN_CID_1", "99", "denizz", "open")])), \
         patch("main._save_buffers"):
        main._rehydrate_from_tracker()

    assert live_key in main._buy_buffers["denizz"]
    assert main._buy_buffers["denizz"][live_key]["last_tier_bet"] == 120.0, \
        "legitimate tier-upgrade anchor must NOT be reset"


def test_rehydrate_keeps_accumulating_buffer_for_new_market():
    """2026-04-17 fix: a buffer with last_tier_bet==0 and no open position
    represents a NEW market accumulating toward MIN_PLAYER_INVESTED ($500).
    It MUST be preserved — otherwise every rehydrate cycle resets the
    accumulation to $0 and the bot never crosses the threshold to enter.

    This is the bug that caused the bot to miss the Lebanon-Jun30 signal
    despite denizz spending $872 cumulatively across multiple buys.
    """
    main._buy_buffers["denizz"].clear()
    main._signaled_keys["denizz"].clear()
    accumulating_key = "0xNEW_MARKET_CID_2"
    main._buy_buffers["denizz"][accumulating_key] = {
        "buys": [[1700000000.0, 200.0], [1700000600.0, 150.0]],
        "total_usd": 350.0,        # below $500 threshold
        "notified": False,         # never crossed
        "first_price": 0.3,
        "last_tier_bet": 0.0,      # never bet (this market is brand new for us)
    }

    with patch("main.tracker.load", return_value=_positions_doc([])), \
         patch("main._save_buffers"):
        main._rehydrate_from_tracker()

    assert accumulating_key in main._buy_buffers["denizz"], \
        "accumulating buffer (last_tier_bet=0) on new market must be preserved across rehydrates"
    assert main._buy_buffers["denizz"][accumulating_key]["total_usd"] == 350.0, \
        "accumulated total must not be reset"
    assert len(main._buy_buffers["denizz"][accumulating_key]["buys"]) == 2, \
        "accumulated buy events must not be cleared"


def test_rehydrate_drops_stale_buffer_with_ltb_after_close():
    """Buffers with last_tier_bet>0 (we previously bet on this market) but no
    open position now must STILL be cleaned. This is the original
    2026-04-15 stale-buffer cleanup case — must not regress."""
    main._buy_buffers["denizz"].clear()
    main._signaled_keys["denizz"].clear()
    closed_market_key = "0xPREVIOUSLY_BET_CID_3"
    main._buy_buffers["denizz"][closed_market_key] = {
        "buys": [[1700000000.0, 600.0]],
        "total_usd": 600.0,
        "notified": True,
        "first_price": 0.4,
        "last_tier_bet": 80.0,    # we placed a bet, then position closed
    }

    with patch("main.tracker.load", return_value=_positions_doc([])), \
         patch("main._save_buffers"):
        main._rehydrate_from_tracker()

    assert closed_market_key not in main._buy_buffers["denizz"], \
        "stale buffer with last_tier_bet>0 + no open position must be purged"
