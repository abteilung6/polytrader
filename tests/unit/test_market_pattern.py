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
    """Test generating market slugs from start timestamps."""
    pattern = MarketPattern.parse("btc-updown-15m")
    start_timestamp = 1767886200
    slug = pattern.generate_slug(start_timestamp)
    assert slug == "btc-updown-15m-1767886200"


def test_market_pattern_get_current_window_start() -> None:
    """Test getting current window start timestamp."""
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = pattern.get_current_window_start()

    # Window start should be <= now (current or past window)
    assert window_start <= now
    assert (now - window_start) < pattern.interval_seconds
    assert window_start % pattern.interval_seconds == 0


def test_market_pattern_get_next_window_start() -> None:
    """Test getting next window start timestamp."""
    pattern = MarketPattern.parse("btc-updown-15m")
    current = pattern.get_current_window_start()
    next_window = pattern.get_next_window_start()

    assert next_window == current + pattern.interval_seconds
