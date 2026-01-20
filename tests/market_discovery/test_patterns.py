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
    """Test market slug generation with START timestamp."""
    pattern = MarketPattern.parse("btc-updown-15m")
    start_timestamp = 1768120200

    slug = pattern.generate_slug(start_timestamp)
    assert slug == "btc-updown-15m-1768120200"


def test_market_pattern_get_current_window_start() -> None:
    """Test that get_current_window_start finds the current active market window.

    The method should round down to the current interval boundary,
    giving us the start of the currently active window.
    """
    pattern = MarketPattern.parse("btc-updown-15m")
    interval = 15 * 60  # 15 minutes in seconds

    # Get current time and calculate what the current market should be
    now = int(time.time())
    expected_window_start = (now // interval) * interval

    # The method should return the start of the current active market
    actual_window_start = pattern.get_current_window_start()

    # Should match expected calculation
    assert actual_window_start == expected_window_start
    # Should be <= now (current or past window)
    assert actual_window_start <= now
    # Should be within one interval of now
    assert (now - actual_window_start) < interval
    # Should be aligned to interval boundary
    assert actual_window_start % interval == 0


def test_market_pattern_get_current_window_start_different_intervals() -> None:
    """Test get_current_window_start with different interval sizes."""
    # 30 minute pattern
    pattern_30m = MarketPattern.parse("btc-updown-30m")
    start_30m = pattern_30m.get_current_window_start()
    assert start_30m % (30 * 60) == 0

    # 1 hour pattern
    pattern_1h = MarketPattern.parse("btc-updown-1h")
    start_1h = pattern_1h.get_current_window_start()
    assert start_1h % 3600 == 0

    # 1 day pattern
    pattern_1d = MarketPattern.parse("btc-updown-1d")
    start_1d = pattern_1d.get_current_window_start()
    assert start_1d % 86400 == 0


def test_market_pattern_get_next_window_start() -> None:
    """Test get_next_window_start returns next window after current."""
    pattern = MarketPattern.parse("btc-updown-15m")
    interval = 15 * 60

    current_start = pattern.get_current_window_start()
    next_start = pattern.get_next_window_start()

    assert next_start == current_start + interval
    assert next_start > current_start


def test_market_pattern_window_alignment() -> None:
    """Test that windows align to interval boundaries."""
    pattern = MarketPattern.parse("btc-updown-15m")
    interval = 15 * 60

    # Get multiple windows and verify alignment
    current = pattern.get_current_window_start()
    next_window = pattern.get_next_window_start()

    # Both should be aligned to interval boundaries
    assert current % interval == 0
    assert next_window % interval == 0
    assert (next_window - current) == interval
