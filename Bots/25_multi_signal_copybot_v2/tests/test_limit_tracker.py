"""Tests for limit_tracker A/B logging module."""
import csv
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

import limit_tracker


@pytest.fixture(autouse=True)
def clean_csv(tmp_path, monkeypatch):
    """Redirect CSV output to a temp file and clean up."""
    csv_path = str(tmp_path / "limit_ab_log.csv")
    monkeypatch.setattr(limit_tracker, "CSV_PATH", csv_path)
    yield csv_path


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.reader(f))


@patch("limit_tracker.time.sleep", return_value=None)
@patch("limit_tracker.filters.get_orderbook_prices")
def test_log_entry_creates_csv(mock_prices, mock_sleep, clean_csv):
    """log_entry should create CSV with a BUY row."""
    mock_prices.return_value = (0.48, 0.50)  # bid, ask

    # Run _track_buy directly (synchronous) instead of spawning thread
    limit_tracker._track_buy("tok1", "Test Market Buy", 0.50, 100, 50.0)

    rows = _read_csv(clean_csv)
    assert len(rows) == 2  # header + 1 data row
    assert rows[0] == limit_tracker.CSV_HEADER
    assert rows[1][2] == "BUY"


@patch("limit_tracker.time.sleep", return_value=None)
@patch("limit_tracker.filters.get_orderbook_prices")
def test_log_exit_creates_csv(mock_prices, mock_sleep, clean_csv):
    """log_exit should create CSV with a SELL row."""
    mock_prices.return_value = (0.60, 0.62)

    limit_tracker._track_sell("tok2", "Test Market Sell", 0.60, 80, 48.0)

    rows = _read_csv(clean_csv)
    assert len(rows) == 2
    assert rows[1][2] == "SELL"


@patch("limit_tracker.time.sleep", return_value=None)
@patch("limit_tracker.filters.get_orderbook_prices")
def test_would_fill_true(mock_prices, mock_sleep, clean_csv):
    """If ask drops below limit price (2% under entry), would_fill=True."""
    # Entry at 0.50, limit = 0.49. Ask drops to 0.48 on 3rd check.
    responses = [(0.48, 0.51)] * 2 + [(0.47, 0.48)] + [(0.47, 0.49)] * 17
    mock_prices.side_effect = responses

    limit_tracker._track_buy("tok3", "Fill Test", 0.50, 100, 50.0)

    rows = _read_csv(clean_csv)
    data = rows[1]
    assert data[8] == "True"  # would_fill
    assert float(data[9]) > 0  # fill_minute > 0


@patch("limit_tracker.time.sleep", return_value=None)
@patch("limit_tracker.filters.get_orderbook_prices")
def test_would_fill_false(mock_prices, mock_sleep, clean_csv):
    """If ask never drops to limit, would_fill=False."""
    # Entry at 0.50, limit = 0.49. Ask stays at 0.51 throughout.
    mock_prices.return_value = (0.49, 0.51)

    limit_tracker._track_buy("tok4", "No Fill Test", 0.50, 100, 50.0)

    rows = _read_csv(clean_csv)
    data = rows[1]
    assert data[8] == "False"  # would_fill
    assert float(data[9]) == 0  # fill_minute = 0


@patch("limit_tracker.time.sleep", return_value=None)
@patch("limit_tracker.filters.get_orderbook_prices")
def test_api_error_doesnt_crash(mock_prices, mock_sleep, clean_csv):
    """If get_orderbook_prices returns None every time, should not crash."""
    mock_prices.return_value = None

    # Should not raise
    limit_tracker._track_buy("tok5", "Error Test", 0.50, 100, 50.0)

    rows = _read_csv(clean_csv)
    assert len(rows) == 2  # still writes a row with fallback values
    data = rows[1]
    assert data[8] == "False"  # would_fill = False (no data)
