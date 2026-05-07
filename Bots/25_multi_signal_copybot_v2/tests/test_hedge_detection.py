"""Tests for filters.detect_hedge_signal / evaluate_hedge_profitability.

Covers the 2026-04-15 incident where a cross-market hedge slipped through
because of IEEE-754 rounding in `ratio == HEDGE_RATIO_MAX`.

All network / tracker calls are mocked — no real HTTP, no disk writes.
"""
import pytest
from unittest.mock import patch

import filters
from config import HEDGE_RATIO_MAX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tracker_payload(positions: dict) -> dict:
    """Wrap a {key: position_dict} map into tracker.load()-shaped data."""
    return {"positions": positions}


def _pos(condition_id, outcome, cost_usd, event_slug,
         status="open", size_shares=100.0, token_id="TK"):
    return {
        "condition_id": condition_id,
        "token_id": token_id,
        "outcome": outcome,
        "cost_usd": cost_usd,
        "size_shares": size_shares,
        "event_slug": event_slug,
        "status": status,
        "avg_entry": cost_usd / size_shares if size_shares else 0,
    }


# Fixed constants for the 2026-04-15 Iran April 21 incident.
IRAN_SLUG = "trump-announces-end-of-military-operations-against-iran-by"
CID_APR21 = "0x1507c50c86fb307e4f1acd9d740b"
CID_APR30 = "0xfa59099fbda1e0f0058ed3cbd57e"
CID_APR15 = "0x68beecc857017df8663fa36c0c86"


# ---------------------------------------------------------------------------
# detect_hedge_signal tests
# ---------------------------------------------------------------------------

def test_incident_2026_04_15_iran_april21():
    """Exact replay of the incident: denizz Yes $4696, our No $223 across
    two different condition_ids on the same event_slug. Must be flagged
    as a hedge (is_hedge=True)."""
    tracker_data = _tracker_payload({
        "k1": _pos(CID_APR30, "No", 120.21, IRAN_SLUG),
        "k2": _pos(CID_APR15, "No", 102.39348, IRAN_SLUG),
    })
    with patch.object(filters, "get_player_usd_on_outcome", return_value=0.0), \
         patch("tracker.load", return_value=tracker_data):
        out = filters.detect_hedge_signal(
            condition_id=CID_APR21,
            signal_player="denizz",
            our_outcome="Yes",
            player_invested=4696.0,
            event_slug=IRAN_SLUG,
        )
    assert out["is_hedge"] is True
    assert out["primary_source"] == "cross-market-tracker"
    assert out["hedge_ratio"] <= HEDGE_RATIO_MAX + 1e-9


def test_hedge_boundary_exact_ratio_max():
    """Same-condition path: player_invested / primary = exactly HEDGE_RATIO_MAX
    → must be classified as a hedge (boundary is inclusive)."""
    # player has $10,000 on opposite — cleanly divisible, no float drift
    with patch.object(filters, "get_player_usd_on_outcome", return_value=10_000.0):
        out = filters.detect_hedge_signal(
            condition_id="0xCID",
            signal_player="denizz",
            our_outcome="Yes",
            player_invested=1_200.0,
            event_slug="any",
        )
    assert out["is_hedge"] is True
    assert out["primary_source"] == "same-condition"
    assert abs(out["hedge_ratio"] - HEDGE_RATIO_MAX) < 1e-9


def test_hedge_float_edge_case():
    """Regression: player_invested = 4695.9999 exercises the IEEE-754 edge
    where player_invested / (player_invested / HEDGE_RATIO_MAX) evaluates to
    0.12000000000000001. Pre-fix would return is_hedge=False; post-fix True."""
    tracker_data = _tracker_payload({
        "k1": _pos(CID_APR30, "No", 120.21, IRAN_SLUG),
        "k2": _pos(CID_APR15, "No", 102.39348, IRAN_SLUG),
    })
    pi = 4695.9999
    # Sanity: confirm the raw float pathology exists in the test environment
    primary_raw = max(222.60348, pi / HEDGE_RATIO_MAX)
    assert pi / primary_raw > HEDGE_RATIO_MAX  # the bug

    with patch.object(filters, "get_player_usd_on_outcome", return_value=0.0), \
         patch("tracker.load", return_value=tracker_data):
        out = filters.detect_hedge_signal(
            condition_id=CID_APR21,
            signal_player="denizz",
            our_outcome="Yes",
            player_invested=pi,
            event_slug=IRAN_SLUG,
        )
    assert out["is_hedge"] is True, f"float edge case slipped through: {out}"


def test_hedge_ratio_just_above_max():
    """If the true ratio is materially above HEDGE_RATIO_MAX (13%), it is NOT
    a hedge — it is a directional trade. The EPSILON must not mask this."""
    # player holds $10,000 opposite, buys $1,300 → ratio = 0.13
    with patch.object(filters, "get_player_usd_on_outcome", return_value=10_000.0):
        out = filters.detect_hedge_signal(
            condition_id="0xCID",
            signal_player="denizz",
            our_outcome="Yes",
            player_invested=1_300.0,
            event_slug="any",
        )
    assert out["is_hedge"] is False
    assert out["hedge_ratio"] > HEDGE_RATIO_MAX


def test_same_condition_hedge_flow():
    """When step 1 (same-condition) finds the player's opposite position,
    step 2 (cross-market) must not run. primary_source must be 'same-condition'
    and tracker must not be consulted."""
    with patch.object(filters, "get_player_usd_on_outcome", return_value=5_000.0), \
         patch("tracker.load") as mock_load:
        out = filters.detect_hedge_signal(
            condition_id="0xCID",
            signal_player="denizz",
            our_outcome="Yes",
            player_invested=300.0,  # ratio 0.06 → hedge
            event_slug="some-event",
        )
    assert out["is_hedge"] is True
    assert out["primary_source"] == "same-condition"
    # Cross-market branch must be skipped entirely
    mock_load.assert_not_called()


# ---------------------------------------------------------------------------
# evaluate_hedge_profitability tests
# ---------------------------------------------------------------------------

def test_cross_market_profitable_primary_copies():
    """Our primary (No) is up +15% → copying the hedge locks in profit.
    should_copy must be True."""
    # Primary: entry 0.50, current bid 0.60 → +20%
    tracker_data = _tracker_payload({
        "p1": _pos(CID_APR30, "No", cost_usd=100.0, event_slug=IRAN_SLUG,
                   size_shares=200.0, token_id="TK_APR30_NO"),
    })
    with patch("tracker.load", return_value=tracker_data), \
         patch.object(filters, "get_orderbook_prices", return_value=(0.60, 0.61)):
        out = filters.evaluate_hedge_profitability(
            our_outcome="Yes",
            condition_id=CID_APR21,
            token_id="TK_APR21_YES",
            event_slug=IRAN_SLUG,
        )
    assert out["should_copy"] is True
    assert out["gain_pct"] > 0.12
    assert "COPY hedge" in out["reason"]


def test_cross_market_losing_primary_blocks():
    """Our primary is at a loss → copying the hedge would just pile on.
    should_copy must be False. Mirrors the 2026-04-15 incident state
    (entry 0.580, mid ~0.54 → −7%)."""
    tracker_data = _tracker_payload({
        "p1": _pos(CID_APR30, "No", cost_usd=120.21, event_slug=IRAN_SLUG,
                   size_shares=207.26, token_id="TK_APR30_NO"),
    })
    with patch("tracker.load", return_value=tracker_data), \
         patch.object(filters, "get_orderbook_prices", return_value=(0.54, 0.55)):
        out = filters.evaluate_hedge_profitability(
            our_outcome="Yes",
            condition_id=CID_APR21,
            token_id="TK_APR21_YES",
            event_slug=IRAN_SLUG,
        )
    assert out["should_copy"] is False
    assert out["gain_pct"] < 0
    assert "SKIP hedge" in out["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
