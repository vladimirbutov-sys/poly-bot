"""Regression tests for 2026-04-21 hedge-detector fix:
Two directional overrides were added to detect_timeseries_hedge so that
legitimate top-ups are no longer misclassified as hedges.

Reference incident:
  Trump end mil ops Apr 30 YES — denizz bought $2050+$3979+$123 on 21.04
  Bot: SKIP hedge — we have no primary position to hedge
  BUG: denizz was topping up his directional Apr 30 YES bet, but the
  detector saw his Apr 21 NO sibling ($45K) and classified as hedge.

Fix adds two pre-classification overrides:
  1. denizz_same_side_usd >= $500 → directional top-up, NOT hedge
  2. event_usd >= $1500 → conviction override, NOT hedge
"""
import pytest
from unittest.mock import patch
import filters


class _FakeResp:
    def __init__(self, markets):
        self.status_code = 200
        self._markets = markets
    def json(self):
        return [{"markets": self._markets}]


@pytest.fixture
def setup_mocks(monkeypatch):
    """Shared mock setup for detect_timeseries_hedge."""
    def _setup(gamma_markets, denizz_positions, same_side_usd=0.0):
        def fake_get(url, params=None, timeout=None):
            if "/events" in url:
                return _FakeResp(gamma_markets)
            class Empty:
                status_code = 200
                def json(self): return []
            return Empty()
        monkeypatch.setattr(filters.requests, "get", fake_get)

        def fake_player_usd(cid, wallet, outcome):
            if cid == "0xCID_APR30" and outcome.strip().capitalize() == "Yes":
                return same_side_usd
            return denizz_positions.get((cid, outcome.strip().capitalize()), 0.0)
        monkeypatch.setattr(filters, "get_player_usd_on_outcome", fake_player_usd)
        monkeypatch.setattr(filters, "PLAYERS", {"denizz": "0xWALLET"}, raising=False)
    return _setup


MARKET_APR21 = {"conditionId": "0xCID_APR21",
                "question": "Trump announces end of military operations against Iran by April 21st?"}
MARKET_APR30 = {"conditionId": "0xCID_APR30",
                "question": "Trump announces end of military operations against Iran by April 30th?"}
MARKET_MAY31 = {"conditionId": "0xCID_MAY31",
                "question": "Trump announces end of military operations against Iran by May 31st?"}


# ==============================================================
# Override 1: denizz same-cid same-side >= $500 → NOT hedge
# ==============================================================

def test_same_side_override_small_buy(setup_mocks):
    """Denizz holds $1K YES on Apr 30 + buys $200 YES more.
    Siblings have denizz NO $45K (would normally trigger hedge).
    Expected: NOT hedge (override 1 triggered by same-side $1K)."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30, MARKET_MAY31],
        denizz_positions={("0xCID_APR21", "No"): 45000.0},
        same_side_usd=1000.0,  # denizz Apr 30 YES existing
    )
    r = filters.detect_timeseries_hedge(
        event_slug="trump-event", condition_id="0xCID_APR30",
        outcome="Yes", player_name="denizz",
        player_invested=200.0, title=MARKET_APR30["question"],
    )
    assert r["is_hedge"] is False
    assert "same-cid same-side" in r["reason"]


def test_same_side_override_threshold_exact(setup_mocks):
    """Denizz same-side exactly $500 → override triggered."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30],
        denizz_positions={("0xCID_APR21", "No"): 10000.0},
        same_side_usd=500.0,
    )
    r = filters.detect_timeseries_hedge(
        event_slug="trump-event", condition_id="0xCID_APR30",
        outcome="Yes", player_name="denizz",
        player_invested=100.0, title=MARKET_APR30["question"],
    )
    assert r["is_hedge"] is False


def test_same_side_below_threshold_still_hedges(setup_mocks):
    """Denizz same-side $499 (below threshold) + no buy-size override →
    classic hedge (if we have no primary, SKIP)."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30],
        denizz_positions={("0xCID_APR21", "No"): 10000.0},
        same_side_usd=499.0,
    )
    # Also need tracker mock for our positions (none)
    import tracker
    with patch.object(tracker, "load", return_value={"positions": {}}):
        r = filters.detect_timeseries_hedge(
            event_slug="trump-event", condition_id="0xCID_APR30",
            outcome="Yes", player_name="denizz",
            player_invested=100.0,  # small, below override 2 threshold
            title=MARKET_APR30["question"],
        )
    assert r["is_hedge"] is True, "expected hedge when same-side below threshold and no event override"


# ==============================================================
# Override 2: player_invested (event size) >= $1500 → NOT hedge
# ==============================================================

def test_event_override_large_buy(setup_mocks):
    """Single buy of $2050 → override 2 triggered, NOT hedge
    (matches Trump Apr 30 $2050 incident)."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30, MARKET_MAY31],
        denizz_positions={("0xCID_APR21", "No"): 45000.0},
        same_side_usd=0.0,  # no same-side stake
    )
    r = filters.detect_timeseries_hedge(
        event_slug="trump-event", condition_id="0xCID_APR30",
        outcome="Yes", player_name="denizz",
        player_invested=2050.0, title=MARKET_APR30["question"],
    )
    assert r["is_hedge"] is False
    assert "large buy" in r["reason"]


def test_event_override_threshold_exact(setup_mocks):
    """Buy of exactly $1500 → override 2 triggered."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30],
        denizz_positions={("0xCID_APR21", "No"): 20000.0},
    )
    r = filters.detect_timeseries_hedge(
        event_slug="trump-event", condition_id="0xCID_APR30",
        outcome="Yes", player_name="denizz",
        player_invested=1500.0, title=MARKET_APR30["question"],
    )
    assert r["is_hedge"] is False


def test_event_override_below_threshold(setup_mocks):
    """Buy of $1499 + no same-side + has primary → still hedge."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30],
        denizz_positions={("0xCID_APR21", "No"): 20000.0},
    )
    import tracker
    with patch.object(tracker, "load", return_value={"positions": {}}):
        r = filters.detect_timeseries_hedge(
            event_slug="trump-event", condition_id="0xCID_APR30",
            outcome="Yes", player_name="denizz",
            player_invested=1499.0,  # just below
            title=MARKET_APR30["question"],
        )
    assert r["is_hedge"] is True


# ==============================================================
# Non-regression: classic hedge still detected
# ==============================================================

def test_no_override_classic_hedge(setup_mocks):
    """Small buy $200, no same-side stake, denizz has big opposite primary
    → classic hedge, IS hedge, SKIP (no primary on our side)."""
    setup_mocks(
        gamma_markets=[MARKET_APR21, MARKET_APR30],
        denizz_positions={("0xCID_APR21", "No"): 50000.0},
        same_side_usd=0.0,
    )
    import tracker
    with patch.object(tracker, "load", return_value={"positions": {}}):
        r = filters.detect_timeseries_hedge(
            event_slug="trump-event", condition_id="0xCID_APR30",
            outcome="Yes", player_name="denizz",
            player_invested=200.0, title=MARKET_APR30["question"],
        )
    assert r["is_hedge"] is True
    assert "no primary position" in r["reason"]


def test_no_siblings_returns_not_hedge(setup_mocks):
    """No time-series siblings → NOT hedge regardless of buy size."""
    setup_mocks(
        gamma_markets=[MARKET_APR30],  # only self
        denizz_positions={},
    )
    r = filters.detect_timeseries_hedge(
        event_slug="trump-event", condition_id="0xCID_APR30",
        outcome="Yes", player_name="denizz",
        player_invested=500.0, title=MARKET_APR30["question"],
    )
    assert r["is_hedge"] is False
