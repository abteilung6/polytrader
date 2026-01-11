"""Tests for Polymarket slug convention understanding.

These tests verify our implementation matches Polymarket's convention:
- Slug suffix = end timestamp (not start)
- Window start = end_ts - interval_seconds
- end_ts must be multiple of interval
"""

import time

from polytrader.market_discovery.patterns import MarketPattern


def test_slug_suffix_is_end_timestamp() -> None:
    """Test that slug suffix represents the end timestamp, not start.

    Per Polymarket convention: The slug suffix is the end timestamp.
    For a 15-minute window ending at 09:15:00 UTC:
    - end_ts = timestamp for 09:15:00 UTC
    - start_ts = end_ts - 900 = timestamp for 09:00:00 UTC

    Note: Using a known valid timestamp that aligns to 15-minute boundaries.
    """
    from datetime import UTC, datetime

    # Use a timestamp that we know is a 15-minute boundary
    # 2026-01-11 09:15:00 UTC
    end_date = datetime(2026, 1, 11, 9, 15, 0, tzinfo=UTC)
    end_ts = int(end_date.timestamp())

    pattern = MarketPattern.parse("btc-updown-15m")
    slug = pattern.generate_slug(end_ts)

    assert slug == f"btc-updown-15m-{end_ts}"

    # Verify end timestamp
    end_time = time.gmtime(end_ts)
    assert end_time.tm_hour == 9
    assert end_time.tm_min == 15
    assert end_time.tm_sec == 0

    # Verify start timestamp
    start_ts = end_ts - 900
    start_time = time.gmtime(start_ts)
    assert start_time.tm_hour == 9
    assert start_time.tm_min == 0
    assert start_time.tm_sec == 0


def test_end_timestamp_is_multiple_of_interval() -> None:
    """Test that end timestamp is always a multiple of interval_seconds."""
    pattern = MarketPattern.parse("btc-updown-15m")
    end_ts = pattern.get_current_window_end()

    # For 15m markets, end_ts should be multiple of 900
    assert end_ts % 900 == 0, f"end_ts {end_ts} should be multiple of 900"

    # Verify window calculation
    start_ts = end_ts - 900
    assert start_ts % 900 == 0, f"start_ts {start_ts} should also align to 15m boundaries"


def test_window_calculation_matches_convention() -> None:
    """Test that window calculation matches Polymarket convention.

    Convention: window_start = end_ts - interval_seconds
    """
    pattern = MarketPattern.parse("btc-updown-15m")
    end_ts = pattern.get_current_window_end()
    start_ts = end_ts - pattern.interval_seconds

    # Verify the relationship
    assert end_ts - start_ts == pattern.interval_seconds
    assert start_ts == (end_ts // pattern.interval_seconds - 1) * pattern.interval_seconds


def test_extract_window_from_slug() -> None:
    """Test extracting window timestamps from slug."""
    from datetime import UTC, datetime

    # Use a known valid timestamp (15-minute boundary)
    end_date = datetime(2026, 1, 11, 9, 15, 0, tzinfo=UTC)
    end_ts = int(end_date.timestamp())
    slug = f"btc-updown-15m-{end_ts}"

    result = MarketPattern.extract_window_from_slug(slug)

    assert result is not None
    start_ts, extracted_end_ts = result

    # Verify end timestamp
    assert extracted_end_ts == end_ts
    end_time = time.gmtime(extracted_end_ts)
    assert end_time.tm_hour == 9
    assert end_time.tm_min == 15

    # Verify start timestamp
    expected_start_ts = end_ts - 900
    assert start_ts == expected_start_ts
    start_time = time.gmtime(start_ts)
    assert start_time.tm_hour == 9
    assert start_time.tm_min == 0

    # Verify relationship
    assert extracted_end_ts - start_ts == 900  # 15 minutes


def test_extract_window_from_slug_invalid() -> None:
    """Test extracting window from invalid slug."""
    # Invalid format
    assert MarketPattern.extract_window_from_slug("invalid") is None
    assert MarketPattern.extract_window_from_slug("btc-updown-15m") is None
    assert MarketPattern.extract_window_from_slug("btc-updown-15m-invalid") is None


def test_generate_slug_matches_api_response() -> None:
    """Test that generated slug matches what we'd expect from API.

    Given:
    - endDate: "2026-01-11T09:15:00Z"
    - eventStartTime: "2026-01-11T09:00:00Z"

    Expected slug: btc-updown-15m-{end_timestamp}

    The slug suffix should match the endDate timestamp exactly.
    """
    from datetime import UTC, datetime

    # Parse endDate from API response
    end_date_str = "2026-01-11T09:15:00Z"
    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
    end_ts = int(end_date.timestamp())

    # Generate slug
    pattern = MarketPattern.parse("btc-updown-15m")
    slug = pattern.generate_slug(end_ts)

    # Verify slug format
    assert slug == f"btc-updown-15m-{end_ts}"

    # Verify end timestamp represents 09:15:00 UTC
    end_date_check = datetime.fromtimestamp(end_ts, tz=UTC)
    assert end_date_check.hour == 9
    assert end_date_check.minute == 15
    assert end_date_check.second == 0

    # Verify window start
    start_ts = end_ts - 900
    start_date = datetime.fromtimestamp(start_ts, tz=UTC)
    assert start_date.hour == 9
    assert start_date.minute == 0
    assert start_date.second == 0


def test_current_window_calculation() -> None:
    """Test that get_current_window_end() returns correct end timestamp.

    The end timestamp should:
    1. Be a multiple of interval_seconds
    2. Represent the end of the currently active window
    3. Match Polymarket's slug convention
    """
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    current_end = pattern.get_current_window_end()

    # Verify it's a multiple of 900
    assert current_end % 900 == 0

    # Verify it's in the future (or very recent past)
    assert current_end >= now - 900, "Window end should be current or very recent"

    # Verify window start
    window_start = current_end - 900
    assert window_start <= now, "Window start should be in the past or now"
    assert window_start % 900 == 0, "Window start should align to 15m boundaries"


def test_next_window_calculation() -> None:
    """Test that get_next_window_end() returns next window end."""
    pattern = MarketPattern.parse("btc-updown-15m")
    current_end = pattern.get_current_window_end()
    next_end = pattern.get_next_window_end()

    # Verify relationship
    assert next_end == current_end + 900
    assert next_end % 900 == 0

    # Verify it's in the future
    now = int(time.time())
    assert next_end > now


def test_slug_generation_for_different_intervals() -> None:
    """Test slug generation works for different intervals."""
    # 1 hour market
    pattern_1h = MarketPattern.parse("eth-updown-1h")
    end_ts_1h = 1768125600  # Multiple of 3600
    slug_1h = pattern_1h.generate_slug(end_ts_1h)
    assert slug_1h == "eth-updown-1h-1768125600"

    # Verify window
    start_ts_1h = end_ts_1h - 3600
    assert end_ts_1h - start_ts_1h == 3600

    # 1 day market
    pattern_1d = MarketPattern.parse("sol-range-1d")
    end_ts_1d = 1768204800  # Multiple of 86400
    slug_1d = pattern_1d.generate_slug(end_ts_1d)
    assert slug_1d == "sol-range-1d-1768204800"

    # Verify window
    start_ts_1d = end_ts_1d - 86400
    assert end_ts_1d - start_ts_1d == 86400
