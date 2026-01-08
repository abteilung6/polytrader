import time

import pytest

from polytrader.market_discovery import MarketPattern


def test_market_pattern_parse_valid() -> None:
    """Test parsing valid market patterns."""
    pattern = MarketPattern.parse("btc-updown-15m")
    assert pattern.underlying == "btc"
    assert pattern.template == "updown"
    assert pattern.interval_seconds == 15 * 60
    assert pattern.pattern_str == "btc-updown-15m"

    pattern = MarketPattern.parse("eth-updown-1h")
    assert pattern.underlying == "eth"
    assert pattern.template == "updown"
    assert pattern.interval_seconds == 3600
    assert pattern.pattern_str == "eth-updown-1h"

    pattern = MarketPattern.parse("btc-updown-1d")
    assert pattern.underlying == "btc"
    assert pattern.template == "updown"
    assert pattern.interval_seconds == 86400
    assert pattern.pattern_str == "btc-updown-1d"

    pattern = MarketPattern.parse("BTC-UPDOWN-15M")
    assert pattern.underlying == "btc"
    assert pattern.template == "updown"
    assert pattern.interval_seconds == 15 * 60


def test_market_pattern_parse_invalid() -> None:
    """Test parsing invalid market patterns."""
    with pytest.raises(ValueError, match="Invalid market pattern"):
        MarketPattern.parse("invalid")

    with pytest.raises(ValueError, match="Invalid market pattern"):
        MarketPattern.parse("btc-updown")

    with pytest.raises(ValueError, match="Invalid market pattern"):
        MarketPattern.parse("btc-updown-15")

    with pytest.raises(ValueError, match="Invalid interval unit"):
        MarketPattern.parse("btc-updown-15x")


def test_market_pattern_generate_slug() -> None:
    """Test generating market slugs from timestamps."""
    pattern = MarketPattern.parse("btc-updown-15m")
    timestamp = 1767886200
    slug = pattern.generate_slug(timestamp)
    assert slug == "btc-updown-15m-1767886200"


def test_market_pattern_get_current_window_end() -> None:
    """Test getting current window end timestamp."""
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_end = pattern.get_current_window_end()

    assert window_end > now
    assert (window_end - now) <= pattern.interval_seconds
    assert window_end % pattern.interval_seconds == 0


def test_market_pattern_get_next_window_end() -> None:
    """Test getting next window end timestamp."""
    pattern = MarketPattern.parse("btc-updown-15m")
    current = pattern.get_current_window_end()
    next_window = pattern.get_next_window_end()

    assert next_window == current + pattern.interval_seconds
