"""Unit tests for MarketPattern."""

import time

import pytest

from polytrader.market_discovery import MarketPattern


def test_market_pattern_parse_valid_patterns() -> None:
    """Test parsing valid market patterns."""
    # 15 minute pattern
    pattern = MarketPattern.parse("btc-updown-15m")
    assert pattern.underlying == "btc"
    assert pattern.template == "updown"
    assert pattern.interval_seconds == 15 * 60
    assert pattern.pattern_str == "btc-updown-15m"

    # 1 hour pattern
    pattern = MarketPattern.parse("eth-updown-1h")
    assert pattern.underlying == "eth"
    assert pattern.template == "updown"
    assert pattern.interval_seconds == 3600
    assert pattern.pattern_str == "eth-updown-1h"

    # 1 day pattern
    pattern = MarketPattern.parse("btc-updown-1d")
    assert pattern.interval_seconds == 86400
    assert pattern.pattern_str == "btc-updown-1d"


def test_market_pattern_parse_invalid_patterns() -> None:
    """Test parsing invalid market patterns raises ValueError."""
    with pytest.raises(ValueError, match="Invalid market pattern"):
        MarketPattern.parse("invalid")

    with pytest.raises(ValueError, match="Invalid interval unit"):
        MarketPattern.parse("btc-updown-15x")  # Invalid unit

    with pytest.raises(ValueError, match="Invalid market pattern"):
        MarketPattern.parse("btc-updown")  # Missing interval


def test_market_pattern_parse_case_insensitive() -> None:
    """Test that pattern parsing is case insensitive."""
    pattern1 = MarketPattern.parse("BTC-UPDOWN-15M")
    pattern2 = MarketPattern.parse("btc-updown-15m")

    assert pattern1.underlying == pattern2.underlying
    assert pattern1.template == pattern2.template
    assert pattern1.interval_seconds == pattern2.interval_seconds


def test_market_pattern_generate_slug() -> None:
    """Test market slug generation."""
    pattern = MarketPattern.parse("btc-updown-15m")
    timestamp = 1768120200

    slug = pattern.generate_slug(timestamp)
    assert slug == "btc-updown-15m-1768120200"


def test_market_pattern_get_current_window_end() -> None:
    """Test that get_current_window_end finds the current active market, not future.

    This test verifies the fix where we round down to current interval start,
    then add interval to get the end, ensuring we find the currently active
    market rather than the next future market.
    """
    pattern = MarketPattern.parse("btc-updown-15m")
    interval = 15 * 60  # 15 minutes in seconds

    # Get current time and calculate what the current market should be
    now = int(time.time())
    current_window_start = (now // interval) * interval
    expected_window_end = current_window_start + interval

    # The method should return the end of the current active market
    actual_window_end = pattern.get_current_window_end()

    # Should be within the current interval (not the next one)
    assert actual_window_end == expected_window_end
    assert actual_window_end > now
    assert (actual_window_end - now) <= interval
    assert actual_window_end % interval == 0

    # Verify it's not the next interval (which would be wrong)
    next_interval_end = expected_window_end + interval
    assert actual_window_end < next_interval_end


def test_market_pattern_get_current_window_end_different_intervals() -> None:
    """Test get_current_window_end with different interval sizes."""
    # 30 minute pattern
    pattern_30m = MarketPattern.parse("btc-updown-30m")
    end_30m = pattern_30m.get_current_window_end()
    assert end_30m % (30 * 60) == 0

    # 1 hour pattern
    pattern_1h = MarketPattern.parse("btc-updown-1h")
    end_1h = pattern_1h.get_current_window_end()
    assert end_1h % 3600 == 0

    # 1 day pattern
    pattern_1d = MarketPattern.parse("btc-updown-1d")
    end_1d = pattern_1d.get_current_window_end()
    assert end_1d % 86400 == 0


def test_market_pattern_get_next_window_end() -> None:
    """Test get_next_window_end returns next window after current."""
    pattern = MarketPattern.parse("btc-updown-15m")
    interval = 15 * 60

    current_end = pattern.get_current_window_end()
    next_end = pattern.get_next_window_end()

    assert next_end == current_end + interval
    assert next_end > current_end


def test_market_pattern_window_alignment() -> None:
    """Test that windows align to interval boundaries."""
    pattern = MarketPattern.parse("btc-updown-15m")
    interval = 15 * 60

    # Get multiple windows and verify alignment
    current = pattern.get_current_window_end()
    next_window = pattern.get_next_window_end()

    # Both should be aligned to interval boundaries
    assert current % interval == 0
    assert next_window % interval == 0
    assert (next_window - current) == interval
