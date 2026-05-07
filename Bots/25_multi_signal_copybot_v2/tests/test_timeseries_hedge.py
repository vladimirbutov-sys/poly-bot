"""Tests for time-series hedge detection (cross-market umbrella events).

Covers 12 test cases matching the 11 scenarios from the design discussion
plus unit tests for is_time_series_pair.
"""
import sys as _sys

# Import main BEFORE pytest wraps stdout (same pattern as test_min_buy_event)
_real_stdout = _sys.stdout
import main  # noqa: E402
_sys.stdout = _real_stdout

import logging  # noqa: E402
import json  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402
import pytest  # noqa: E402

import filters  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for is_time_series_pair
# ---------------------------------------------------------------------------

class TestIsTimeSeriesPair:

    def test_same_question_different_dates(self):
        a = "Trump announces end of military operations against Iran by April 21st?"
        b = "Trump announces end of military operations against Iran by April 30th?"
        assert filters.is_time_series_pair(a, b) is True

    def test_iran_enrichment_different_months(self):
        a = "Iran agrees to end enrichment of uranium by March 31?"
        b = "Iran agrees to end enrichment of uranium by June 30?"
        assert filters.is_time_series_pair(a, b) is True

    def test_conflict_ends_different_dates(self):
        a = "Iran x Israel/US conflict ends by April 7?"
        b = "Iran x Israel/US conflict ends by April 15?"
        assert filters.is_time_series_pair(a, b) is True

    def test_peace_deal_with_year(self):
        a = "US x Iran permanent peace deal by April 22, 2026?"
        b = "US x Iran permanent peace deal by May 31, 2026?"
        assert filters.is_time_series_pair(a, b) is True

    def test_different_questions_not_timeseries(self):
        a = "Will Trump agree to Iranian enrichment of uranium?"
        b = "Will Trump agree to Iranian transit fees in the Strait of Hormuz?"
        assert filters.is_time_series_pair(a, b) is False

    def test_completely_different_topics(self):
        a = "Bitcoin reaches $100k by June?"
        b = "Iran agrees to end enrichment of uranium by June 30?"
        assert filters.is_time_series_pair(a, b) is False

    def test_empty_strings(self):
        assert filters.is_time_series_pair("", "") is False
        assert filters.is_time_series_pair("foo", "") is False

    def test_identical_titles(self):
        a = "Iran x Israel/US conflict ends by April 7?"
        assert filters.is_time_series_pair(a, a) is True


# ---------------------------------------------------------------------------
# Helpers for detect_timeseries_hedge tests
# ---------------------------------------------------------------------------

def _make_gamma_response(markets):
    """Build a Gamma API response with the given list of market dicts."""
    class FakeResp:
        status_code = 200
        def json(self):
            return [{"markets": markets}]
    return FakeResp()


def _make_tracker_data(positions=None):
    """Build minimal tracker data."""
    return {
        "positions": positions or {},
        "stats": {"current_balance": 2700.0, "peak_balance": 2700.0},
    }


def _setup_hedge_mocks(monkeypatch, gamma_markets, denizz_positions,
                        tracker_positions=None, available=2000.0):
    """Wire up mocks for detect_timeseries_hedge and handle_buy integration.

    Args:
        gamma_markets: list of market dicts returned by gamma API
        denizz_positions: dict mapping (condition_id, outcome) -> usd value
            e.g. {("0xCID_APR30", "No"): 30000.0}
        tracker_positions: dict of tracker position dicts (keyed by arbitrary id)
        available: available balance
    """
    import tracker, entry_manager, telegram_notify as tg

    # Gamma API mock
    def fake_get(url, params=None, timeout=None):
        if "/events" in url:
            return _make_gamma_response(gamma_markets)
        # Default: empty
        class Empty:
            status_code = 200
            def json(self): return []
        return Empty()
    monkeypatch.setattr(filters.requests, "get", fake_get)

    # get_player_usd_on_outcome mock (denizz positions)
    def fake_player_usd(cid, wallet, outcome):
        return denizz_positions.get((cid, outcome.strip().capitalize()), 0.0)
    monkeypatch.setattr(filters, "get_player_usd_on_outcome", fake_player_usd)

    # Tracker mocks
    tdata = _make_tracker_data(tracker_positions or {})
    monkeypatch.setattr(tracker, "load", lambda: tdata)
    monkeypatch.setattr(tracker, "get_available_balance", lambda data, *a, **k: available)
    monkeypatch.setattr(tracker, "can_open_new", lambda data: (True, ""))
    monkeypatch.setattr(tracker, "has_position_on_condition", lambda data, cid: False)
    monkeypatch.setattr(tracker, "has_position_on_event", lambda data, slug: False)
    monkeypatch.setattr(tracker, "save", lambda data: None)

    # Entry manager spy
    entry_spy = MagicMock()
    monkeypatch.setattr(entry_manager, "execute_part1", entry_spy)

    # Silence TG
    for name in ["player_buy", "skip", "entry_placed", "sell_placed", "error", "signal_detected"]:
        if hasattr(tg, name):
            monkeypatch.setattr(tg, name, lambda *a, **k: None)

    # On-chain topup detection: no prior shares (new market)
    monkeypatch.setattr(filters, "get_denizz_size_before_event",
                        lambda *a, **k: (0.0, True))

    # Other filters: neutral
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

    # Clear main buffers
    main._buy_buffers = {"denizz": {}}
    main._signaled_keys = {"denizz": set()}

    # FakeThread: run synchronously
    import threading
    class FakeThread:
        def __init__(self, target=None, daemon=None, **kw):
            self._target = target
        def start(self):
            if self._target:
                try: self._target()
                except Exception: pass
    monkeypatch.setattr(threading, "Thread", FakeThread)

    return entry_spy


# Common market data
MARKET_APR21 = {
    "conditionId": "0xCID_APR21",
    "question": "Trump announces end of military operations against Iran by April 21st?",
}
MARKET_APR30 = {
    "conditionId": "0xCID_APR30",
    "question": "Trump announces end of military operations against Iran by April 30th?",
}
MARKET_MAY31 = {
    "conditionId": "0xCID_MAY31",
    "question": "Trump announces end of military operations against Iran by May 31st?",
}
MARKET_ENRICHMENT = {
    "conditionId": "0xCID_ENRICH",
    "question": "Iran agrees to end enrichment of uranium by March 31?",
}
MARKET_NAVIGATION = {
    "conditionId": "0xCID_NAV",
    "question": "Will Trump agree to Iranian transit fees in the Strait of Hormuz?",
}


def _make_event(condition_id="0xCID_APR21", cost_usd=2000.0, outcome="Yes",
                title="Trump announces end of military operations against Iran by April 21st?",
                event_slug="trump-announces-end-of-military-operations-against-iran-by"):
    return {
        "player": "denizz",
        "token_id": "TOKEN_APR21",
        "condition_id": condition_id,
        "price": 0.10,
        "size": cost_usd / 0.10,
        "cost_usd": cost_usd,
        "title": title,
        "outcome": outcome,
        "event_slug": event_slug,
    }


# ---------------------------------------------------------------------------
# Test cases for detect_timeseries_hedge (unit-level)
# ---------------------------------------------------------------------------

class TestDetectTimeseriesHedge:

    def test_classic_hedge_with_primary(self, monkeypatch):
        """Case 1: denizz $30K NO Apr30, buys $600 YES Apr21.
        We have $500 NO Apr30. Hedge = 500 * (600/30000) = $10.
        (sizes chosen under 2026-04-21 override thresholds so classic hedge
        path still exercised.)"""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
            tracker_positions={
                "pos1": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_APR30",
                    "outcome": "No",
                    "cost_usd": 500.0,
                },
            },
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=600.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is True
        assert result["should_buy"] is True
        assert abs(result["hedge_usd"] - 10.0) < 0.1
        assert result["denizz_primary_usd"] == 30000.0
        assert result["our_primary_usd"] == 500.0

    def test_hedge_no_our_primary(self, monkeypatch):
        """Case 2: denizz hedges, but we have no primary -> SKIP.
        (player_invested < $1500 override threshold to exercise classic path.)"""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
            tracker_positions={},
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=600.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is True
        assert result["should_buy"] is False
        assert "no primary" in result["reason"]

    def test_hedge_primary_on_different_date_below_min(self, monkeypatch):
        """Case 3: our primary is $80 NO May31. hedge = 80*(500/30000)=$1.33 < $5 min -> SKIP."""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30, MARKET_MAY31],
            denizz_positions={
                ("0xCID_APR30", "No"): 20000.0,
                ("0xCID_MAY31", "No"): 10000.0,
            },
            tracker_positions={
                "pos1": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_MAY31",
                    "outcome": "No",
                    "cost_usd": 80.0,
                },
            },
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=500.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is True
        assert result["should_buy"] is False
        assert "min" in result["reason"]

    def test_same_side_not_hedge(self, monkeypatch):
        """Case 4: denizz NO Apr30 + buys NO Apr21 -> same side, not hedge."""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
        )
        # Buying NO -> opposite is YES -> we check denizz's YES on siblings
        # denizz has NO, not YES -> denizz_primary_usd = 0 -> not hedge
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="No",
            player_name="denizz",
            player_invested=2000.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is False

    def test_different_questions_not_timeseries(self, monkeypatch):
        """Case 5: 'enrichment' vs 'navigation' -> not time-series -> not hedge."""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_ENRICHMENT, MARKET_NAVIGATION],
            denizz_positions={("0xCID_NAV", "No"): 20000.0},
        )
        result = filters.detect_timeseries_hedge(
            event_slug="iran-umbrella",
            condition_id="0xCID_ENRICH",
            outcome="Yes",
            player_name="denizz",
            player_invested=2000.0,
            title="Iran agrees to end enrichment of uranium by March 31?",
        )
        assert result["is_hedge"] is False

    def test_same_side_both_yes(self, monkeypatch):
        """Case 6: denizz YES on sibling + buys YES -> same side, not hedge."""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "Yes"): 30000.0},
        )
        # Buying YES -> opposite is NO -> check denizz's NO on siblings -> 0
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=2000.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is False

    def test_our_position_opposite_to_denizz(self, monkeypatch):
        """Case 7: denizz primary NO, we hold YES -> our_primary_usd=0 -> SKIP.
        We don't sum our YES as 'primary to hedge' because denizz's primary is NO
        and we're looking for our positions matching denizz's primary direction.
        (player_invested < $1500 to exercise classic hedge path.)"""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
            tracker_positions={
                "pos1": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_APR30",
                    "outcome": "Yes",  # opposite to denizz's primary
                    "cost_usd": 100.0,
                },
            },
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=600.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is True
        assert result["should_buy"] is False
        assert result["our_primary_usd"] == 0.0

    def test_no_existing_positions(self, monkeypatch):
        """Case 8: first entry by denizz, no positions on siblings -> not hedge."""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={},  # no positions at all
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=2000.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is False

    def test_hedge_below_minimum(self, monkeypatch):
        """Case 9: our primary $30, hedge = 30*(500/30000)=$0.50 < $5 -> SKIP."""
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
            tracker_positions={
                "pos1": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_APR30",
                    "outcome": "No",
                    "cost_usd": 30.0,
                },
            },
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=500.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is True
        assert result["should_buy"] is False
        assert "min" in result["reason"]

    def test_multiple_primaries_sum(self, monkeypatch):
        """Case 11: denizz $10K+$20K+$5K NO on 3 dates. We $200+$300 NO.
        denizz_primary = 35K, our = 500, hedge = 500*(600/35000) = $8.57.
        (player_invested < $1500 override to exercise classic hedge path.)"""
        MARKET_JUN30 = {
            "conditionId": "0xCID_JUN30",
            "question": "Trump announces end of military operations against Iran by June 30th?",
        }
        _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30, MARKET_MAY31, MARKET_JUN30],
            denizz_positions={
                ("0xCID_APR30", "No"): 10000.0,
                ("0xCID_MAY31", "No"): 20000.0,
                ("0xCID_JUN30", "No"): 5000.0,
            },
            tracker_positions={
                "pos1": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_APR30",
                    "outcome": "No",
                    "cost_usd": 200.0,
                },
                "pos2": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_MAY31",
                    "outcome": "No",
                    "cost_usd": 300.0,
                },
            },
        )
        result = filters.detect_timeseries_hedge(
            event_slug="trump-announces-end-of-military-operations-against-iran-by",
            condition_id="0xCID_APR21",
            outcome="Yes",
            player_name="denizz",
            player_invested=600.0,
            title="Trump announces end of military operations against Iran by April 21st?",
        )
        assert result["is_hedge"] is True
        assert result["should_buy"] is True
        assert result["denizz_primary_usd"] == 35000.0
        assert result["our_primary_usd"] == 500.0
        expected_hedge = 500.0 * (600.0 / 35000.0)
        assert abs(result["hedge_usd"] - expected_hedge) < 0.1


# ---------------------------------------------------------------------------
# Integration: handle_buy routes hedge correctly
# ---------------------------------------------------------------------------

class TestHandleBuyHedgeIntegration:

    def test_handle_buy_executes_hedge(self, monkeypatch):
        """handle_buy should call entry_manager.execute_part1 with hedge tier.
        (cost_usd < $1500 to exercise classic hedge path post 2026-04-21 override.)"""
        entry_spy = _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
            tracker_positions={
                "pos1": {
                    "status": "open",
                    "event_slug": "trump-announces-end-of-military-operations-against-iran-by",
                    "condition_id": "0xCID_APR30",
                    "outcome": "No",
                    "cost_usd": 500.0,
                },
            },
        )
        ev = _make_event(cost_usd=600.0, outcome="Yes")
        main.handle_buy("denizz", ev)
        entry_spy.assert_called_once()
        call_kwargs = entry_spy.call_args
        # tier should be "hedge"
        assert call_kwargs[1].get("tier") == "hedge" or "hedge" in str(call_kwargs)

    def test_handle_buy_skips_hedge_no_primary(self, monkeypatch, capsys):
        """handle_buy should SKIP hedge when we have no primary.
        (cost_usd < $1500 to avoid conviction override.)"""
        entry_spy = _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={("0xCID_APR30", "No"): 30000.0},
            tracker_positions={},
        )
        ev = _make_event(cost_usd=600.0, outcome="Yes")
        main.handle_buy("denizz", ev)
        entry_spy.assert_not_called()

    def test_handle_buy_normal_when_not_hedge(self, monkeypatch):
        """When not a hedge, handle_buy should proceed to normal flow."""
        entry_spy = _setup_hedge_mocks(
            monkeypatch,
            gamma_markets=[MARKET_APR21, MARKET_APR30],
            denizz_positions={},  # no positions -> not hedge
            tracker_positions={},
        )
        # Need enough cost_usd to pass MIN_PLAYER_INVESTED
        ev = _make_event(cost_usd=600.0, outcome="Yes")
        main.handle_buy("denizz", ev)
        # Should reach normal check_signal path and execute
        entry_spy.assert_called_once()
