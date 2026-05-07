"""Unit tests for variant.py — A/B mode hot-reload and buy-filter."""
import os
import time
from unittest.mock import patch, MagicMock

import pytest

import config
import variant


@pytest.fixture(autouse=True)
def _reset_variant_cache():
    """Reset module-level cache between tests."""
    variant._cache_value = None
    variant._cache_source = "init"
    variant._cache_ts = 0.0
    variant._last_logged_value = None
    yield
    # cleanup any stray flag file
    project_dir = os.path.dirname(os.path.abspath(variant.__file__))
    p = os.path.join(project_dir, config.VARIANT_FILE)
    if os.path.exists(p):
        os.remove(p)


def _flag_path() -> str:
    project_dir = os.path.dirname(os.path.abspath(variant.__file__))
    return os.path.join(project_dir, config.VARIANT_FILE)


# ---------- get_active_variant ----------

class TestGetActiveVariant:
    def test_no_file_uses_config_default(self):
        with patch.object(config, "BOT_VARIANT", "A"):
            assert variant.get_active_variant(force_reload=True) == "A"

    def test_no_file_config_b(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            assert variant.get_active_variant(force_reload=True) == "B"

    def test_file_overrides_config(self):
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("B")
        with patch.object(config, "BOT_VARIANT", "A"):
            assert variant.get_active_variant(force_reload=True) == "B"

    def test_file_lowercase_accepted(self):
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("b")
        with patch.object(config, "BOT_VARIANT", "A"):
            assert variant.get_active_variant(force_reload=True) == "B"

    def test_invalid_file_falls_back_to_config(self):
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("xyz")
        with patch.object(config, "BOT_VARIANT", "A"):
            assert variant.get_active_variant(force_reload=True) == "A"

    def test_empty_file_falls_back_to_config(self):
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("")
        with patch.object(config, "BOT_VARIANT", "B"):
            assert variant.get_active_variant(force_reload=True) == "B"

    def test_invalid_config_default_safe_to_a(self):
        with patch.object(config, "BOT_VARIANT", "garbage"):
            assert variant.get_active_variant(force_reload=True) == "A"

    def test_cache_respected_within_interval(self):
        # First call: file says B
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("B")
        v1 = variant.get_active_variant(force_reload=True)
        assert v1 == "B"
        # Now flip the file to A but call WITHOUT force_reload — cache wins
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("A")
        v2 = variant.get_active_variant(force_reload=False)
        assert v2 == "B", "should still be B because of cache"

    def test_cache_invalidated_by_force_reload(self):
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("B")
        assert variant.get_active_variant(force_reload=True) == "B"
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("A")
        assert variant.get_active_variant(force_reload=True) == "A"

    def test_cache_invalidated_by_time(self):
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("B")
        assert variant.get_active_variant(force_reload=True) == "B"
        # Manually age the cache past the interval
        variant._cache_ts = time.time() - (config.VARIANT_RELOAD_INTERVAL_SEC + 5)
        with open(_flag_path(), "w", encoding="utf-8") as f:
            f.write("A")
        assert variant.get_active_variant(force_reload=False) == "A"


# ---------- should_skip_buy_for_variant ----------

class TestShouldSkipBuy:
    def test_variant_a_never_skips(self):
        with patch.object(config, "BOT_VARIANT", "A"):
            variant.get_active_variant(force_reload=True)
            for ask in (0.01, 0.05, 0.30, 0.45, 0.50, 0.85, 0.99, 1.00):
                skip, reason = variant.should_skip_buy_for_variant(
                    "tok123", "title", live_ask=ask)
                assert skip is False, f"variant A unexpectedly skipped at ask={ask}"
                assert reason == ""

    def test_variant_b_skips_below_floor(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            for ask in (0.01, 0.10, 0.20, 0.30, 0.4499):
                skip, reason = variant.should_skip_buy_for_variant(
                    "tok", "test market", live_ask=ask)
                assert skip is True, f"variant B should skip at ask={ask}"
                assert "outside" in reason or "SKIP" in reason

    def test_variant_b_skips_above_ceil(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            # default ceil 0.99 — anything strictly above is skipped
            skip, _ = variant.should_skip_buy_for_variant(
                "tok", "x", live_ask=0.999)
            assert skip is True

    def test_variant_b_passes_in_band(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            for ask in (0.45, 0.50, 0.70, 0.85, 0.95, 0.99):
                skip, reason = variant.should_skip_buy_for_variant(
                    "tok", "x", live_ask=ask)
                assert skip is False, f"variant B unexpectedly skipped at ask={ask}"
                assert reason == ""

    def test_variant_b_inclusive_floor_boundary(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            skip, _ = variant.should_skip_buy_for_variant(
                "tok", "x", live_ask=0.45)
            assert skip is False, "0.45 boundary should pass (inclusive)"

    def test_variant_b_inclusive_ceil_boundary(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            skip, _ = variant.should_skip_buy_for_variant(
                "tok", "x", live_ask=0.99)
            assert skip is False, "0.99 boundary should pass (inclusive)"

    def test_variant_b_failsafe_when_ask_unavailable(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            with patch.object(variant, "_get_live_ask", return_value=None):
                skip, reason = variant.should_skip_buy_for_variant(
                    "tok123", "stuck market")
                assert skip is True
                assert "unavailable" in reason or "fail-safe" in reason

    def test_variant_b_fetches_live_ask_when_not_passed(self):
        with patch.object(config, "BOT_VARIANT", "B"):
            variant.get_active_variant(force_reload=True)
            with patch.object(variant, "_get_live_ask", return_value=0.60) as mock_fetch:
                skip, _ = variant.should_skip_buy_for_variant("tok123", "x")
                assert skip is False
                mock_fetch.assert_called_once_with("tok123")


# ---------- get_variant_status ----------

class TestVariantStatus:
    def test_status_keys_present(self):
        with patch.object(config, "BOT_VARIANT", "A"):
            variant.get_active_variant(force_reload=True)
            status = variant.get_variant_status()
            for k in ("active", "source", "config_default", "file_status",
                      "floor", "ceil", "cached_for_sec"):
                assert k in status, f"missing key {k} in status"

    def test_status_floor_ceil_match_config(self):
        status = variant.get_variant_status()
        assert status["floor"] == config.VARIANT_B_PRICE_FLOOR
        assert status["ceil"] == config.VARIANT_B_PRICE_CEIL


# ---------- Regression: variant A keeps legacy behaviour ----------

class TestVariantANoRegression:
    def test_variant_a_status_active_a(self):
        with patch.object(config, "BOT_VARIANT", "A"):
            variant.get_active_variant(force_reload=True)
            assert variant.get_variant_status()["active"] == "A"

    def test_variant_a_with_extreme_prices(self):
        """Sanity: variant A passes prices that would fail variant B."""
        with patch.object(config, "BOT_VARIANT", "A"):
            variant.get_active_variant(force_reload=True)
            for ask in (0.01, 0.07, 0.34, 0.50):
                skip, _ = variant.should_skip_buy_for_variant(
                    "tok", "x", live_ask=ask)
                assert skip is False
