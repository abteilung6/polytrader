"""Tests for START timestamp convention in market discovery.

Per Polymarket convention: Market slug suffix represents the window START timestamp,
not the window END timestamp.
"""

import time

from polytrader.market_discovery import MarketPattern


def test_slug_suffix_is_start_timestamp() -> None:
    """Test that slug suffix represents window start, not end."""
    pattern = MarketPattern.parse("btc-updown-15m")

    # Create a timestamp aligned to 15-minute boundary (window start)
    now = int(time.time())
    window_start = (now // 900) * 900

    # Generate slug with start timestamp
    slug = pattern.generate_slug(window_start)

    # Extract window from slug
    window_info = MarketPattern.extract_window_from_slug(slug)
    assert window_info is not None
    extracted_start, extracted_end = window_info

    # Extracted start should match the input start
    assert extracted_start == window_start
    # Extracted end should be start + interval
    assert extracted_end == window_start + 900


def test_start_timestamp_is_multiple_of_interval() -> None:
    """Test that window start timestamps are aligned to interval boundaries."""
    pattern = MarketPattern.parse("btc-updown-15m")

    # Get current window start
    window_start = pattern.get_current_window_start()

    # Should be multiple of 900 (15 minutes)
    assert window_start % 900 == 0

    # Should be <= current time
    now = int(time.time())
    assert window_start <= now
    assert (now - window_start) < 900


def test_get_current_window_start() -> None:
    """Test that get_current_window_start() returns correct start timestamp."""
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())

    current_start = pattern.get_current_window_start()

    # Should be aligned to 15-minute boundary
    assert current_start % 900 == 0

    # Should be <= now (current or past window)
    assert current_start <= now

    # Should be within one interval of now
    assert (now - current_start) < 900

    # Should match manual calculation
    expected_start = (now // 900) * 900
    assert current_start == expected_start


def test_get_next_window_start() -> None:
    """Test that get_next_window_start() returns next window start."""
    pattern = MarketPattern.parse("btc-updown-15m")

    current_start = pattern.get_current_window_start()
    next_start = pattern.get_next_window_start()

    # Next should be exactly one interval ahead
    assert next_start == current_start + 900


def test_extract_window_from_slug_start_convention() -> None:
    """Test that extract_window_from_slug treats suffix as start timestamp."""
    # Example: btc-updown-15m-1768121100
    # If suffix is start timestamp: 1768121100 = window start
    # Window end = 1768121100 + 900 = 1768122000

    slug = "btc-updown-15m-1768121100"
    window_info = MarketPattern.extract_window_from_slug(slug)

    assert window_info is not None
    start_ts, end_ts = window_info

    # Start should be the suffix
    assert start_ts == 1768121100

    # End should be start + 900 (15 minutes)
    assert end_ts == 1768121100 + 900
    assert end_ts == 1768122000


def test_generate_and_extract_roundtrip() -> None:
    """Test that generate_slug and extract_window_from_slug are consistent."""
    pattern = MarketPattern.parse("btc-updown-15m")

    # Generate slug from window start
    window_start = (int(time.time()) // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Extract window back
    window_info = MarketPattern.extract_window_from_slug(slug)
    assert window_info is not None
    extracted_start, extracted_end = window_info

    # Should match original
    assert extracted_start == window_start
    assert extracted_end == window_start + 900


def test_multiple_intervals() -> None:
    """Test START convention works for different interval sizes."""
    # 15-minute markets
    pattern_15m = MarketPattern.parse("btc-updown-15m")
    start_15m = pattern_15m.get_current_window_start()
    assert start_15m % 900 == 0

    # 1-hour markets
    pattern_1h = MarketPattern.parse("eth-updown-1h")
    start_1h = pattern_1h.get_current_window_start()
    assert start_1h % 3600 == 0

    # 1-day markets
    pattern_1d = MarketPattern.parse("btc-updown-1d")
    start_1d = pattern_1d.get_current_window_start()
    assert start_1d % 86400 == 0
