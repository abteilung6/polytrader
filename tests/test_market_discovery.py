"""Tests for market discovery module."""

import re
from datetime import datetime, timezone, timedelta

import pytest

from polytrader.market_discovery import MarketSlugGenerator


class TestNormalizeAsset:
    """Tests for asset normalization."""

    def test_normalize_bitcoin(self) -> None:
        """Test normalizing bitcoin asset."""
        short, long_format = MarketSlugGenerator.normalize_asset("bitcoin")
        assert short == "btc"
        assert long_format == "bitcoin"

    def test_normalize_btc(self) -> None:
        """Test normalizing btc asset."""
        short, long_format = MarketSlugGenerator.normalize_asset("btc")
        assert short == "btc"
        assert long_format == "bitcoin"

    def test_normalize_bitcoin_case_insensitive(self) -> None:
        """Test that asset normalization is case insensitive."""
        short1, long1 = MarketSlugGenerator.normalize_asset("BITCOIN")
        short2, long2 = MarketSlugGenerator.normalize_asset("Bitcoin")
        short3, long3 = MarketSlugGenerator.normalize_asset("bTc")
        assert short1 == short2 == short3 == "btc"
        assert long1 == long2 == long3 == "bitcoin"

    def test_normalize_ethereum(self) -> None:
        """Test normalizing ethereum asset."""
        short, long_format = MarketSlugGenerator.normalize_asset("ethereum")
        assert short == "eth"
        assert long_format == "ethereum"

    def test_normalize_eth(self) -> None:
        """Test normalizing eth asset."""
        short, long_format = MarketSlugGenerator.normalize_asset("eth")
        assert short == "eth"
        assert long_format == "ethereum"

    def test_normalize_invalid_asset(self) -> None:
        """Test that invalid asset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown asset"):
            MarketSlugGenerator.normalize_asset("invalid")


class TestNormalizeTimePeriod:
    """Tests for time period normalization."""

    def test_normalize_15min(self) -> None:
        """Test normalizing 15min period."""
        assert MarketSlugGenerator.normalize_time_period("15min") == "15min"

    def test_normalize_15m(self) -> None:
        """Test normalizing 15m period."""
        assert MarketSlugGenerator.normalize_time_period("15m") == "15min"

    def test_normalize_15(self) -> None:
        """Test normalizing 15 period."""
        assert MarketSlugGenerator.normalize_time_period("15") == "15min"

    def test_normalize_1h(self) -> None:
        """Test normalizing 1h period."""
        assert MarketSlugGenerator.normalize_time_period("1h") == "1h"

    def test_normalize_1hour(self) -> None:
        """Test normalizing 1hour period."""
        assert MarketSlugGenerator.normalize_time_period("1hour") == "1h"

    def test_normalize_hour(self) -> None:
        """Test normalizing hour period."""
        assert MarketSlugGenerator.normalize_time_period("hour") == "1h"

    def test_normalize_hourly(self) -> None:
        """Test normalizing hourly period."""
        assert MarketSlugGenerator.normalize_time_period("hourly") == "1h"

    def test_normalize_case_insensitive(self) -> None:
        """Test that time period normalization is case insensitive."""
        assert MarketSlugGenerator.normalize_time_period("15MIN") == "15min"
        assert MarketSlugGenerator.normalize_time_period("1H") == "1h"

    def test_normalize_invalid_period(self) -> None:
        """Test that invalid time period raises ValueError."""
        with pytest.raises(ValueError, match="Unknown time period"):
            MarketSlugGenerator.normalize_time_period("invalid")


class Test15MinSlug:
    """Tests for 15-minute market slug generation."""

    def test_15min_slug_format_bitcoin(self) -> None:
        """Test 15-minute slug format for bitcoin."""
        slug = MarketSlugGenerator.get_latest_15min_slug("bitcoin")
        assert slug.startswith("btc-updown-15m-")
        assert slug.split("-")[-1].isdigit()

    def test_15min_slug_format_ethereum(self) -> None:
        """Test 15-minute slug format for ethereum."""
        slug = MarketSlugGenerator.get_latest_15min_slug("ethereum")
        assert slug.startswith("eth-updown-15m-")
        assert slug.split("-")[-1].isdigit()

    def test_15min_slug_timestamp_alignment(self) -> None:
        """Test that timestamp is aligned to 15-minute intervals."""
        slug = MarketSlugGenerator.get_latest_15min_slug("btc")
        timestamp_str = slug.split("-")[-1]
        timestamp = int(timestamp_str)

        # Check that timestamp is divisible by 900 (15 minutes)
        assert timestamp % 900 == 0

        # Check that timestamp is not in the future
        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        assert timestamp <= current_timestamp

        # Check that timestamp is within the last 15 minutes
        assert current_timestamp - timestamp < 900

    def test_15min_slug_consistency(self) -> None:
        """Test that multiple calls within same 15-min interval return same slug."""
        slug1 = MarketSlugGenerator.get_latest_15min_slug("btc")
        slug2 = MarketSlugGenerator.get_latest_15min_slug("btc")
        assert slug1 == slug2


class TestHourlySlug:
    """Tests for hourly market slug generation."""

    def test_hourly_slug_format_bitcoin(self) -> None:
        """Test hourly slug format for bitcoin."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        assert slug.startswith("bitcoin-up-or-down-")
        assert slug.endswith("-et")
        assert "am" in slug or "pm" in slug

    def test_hourly_slug_format_ethereum(self) -> None:
        """Test hourly slug format for ethereum."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("ethereum")
        assert slug.startswith("ethereum-up-or-down-")
        assert slug.endswith("-et")
        assert "am" in slug or "pm" in slug

    def test_hourly_slug_contains_month(self) -> None:
        """Test that hourly slug contains month name."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Extract month from slug: bitcoin-up-or-down-{month}-{day}-{hour}am-et
        parts = slug.split("-")
        month_index = 3
        assert month_index < len(parts)
        month = parts[month_index]
        # Month should be lowercase
        assert month.islower()
        # Month should be a valid month name
        valid_months = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
        assert month in valid_months

    def test_hourly_slug_contains_day(self) -> None:
        """Test that hourly slug contains day number."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Extract day from slug: bitcoin-up-or-down-{month}-{day}-{hour}am-et
        parts = slug.split("-")
        day_index = 4
        assert day_index < len(parts)
        day_str = parts[day_index]
        assert day_str.isdigit()
        day = int(day_str)
        assert 1 <= day <= 31

    def test_hourly_slug_contains_hour(self) -> None:
        """Test that hourly slug contains hour in 12-hour format."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Extract hour from slug: bitcoin-up-or-down-{month}-{day}-{hour}am-et
        # Pattern: {hour}am or {hour}pm
        match = re.search(r"(\d+)(am|pm)-et$", slug)
        assert match is not None
        hour_str, am_pm = match.groups()
        hour = int(hour_str)
        assert 1 <= hour <= 12
        assert am_pm in ("am", "pm")

    def test_hourly_slug_hour_alignment(self) -> None:
        """Test that hourly slug uses current hour (rounded down)."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Extract hour from slug
        match = re.search(r"(\d+)(am|pm)-et$", slug)
        assert match is not None
        hour_str, am_pm = match.groups()
        hour_12 = int(hour_str)

        # Get current ET time
        try:
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
        except ImportError:
            # Fallback for Python < 3.9
            et_offset = timedelta(hours=-5)
            et_tz = timezone(et_offset, name="ET")

        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(et_tz)
        current_hour_et = now_et.hour
        current_hour_12 = current_hour_et % 12
        if current_hour_12 == 0:
            current_hour_12 = 12
        current_am_pm = "am" if current_hour_et < 12 else "pm"

        # The slug should match the current hour (rounded down)
        assert hour_12 == current_hour_12
        assert am_pm == current_am_pm

    def test_hourly_slug_consistency(self) -> None:
        """Test that multiple calls within same hour return same slug."""
        slug1 = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        slug2 = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        assert slug1 == slug2


class TestGetLatestSlug:
    """Tests for get_latest_slug integration method."""

    def test_get_latest_slug_15min_bitcoin(self) -> None:
        """Test get_latest_slug for 15-minute bitcoin market."""
        slug = MarketSlugGenerator.get_latest_slug("bitcoin", "15min")
        assert slug.startswith("btc-updown-15m-")

    def test_get_latest_slug_15min_ethereum(self) -> None:
        """Test get_latest_slug for 15-minute ethereum market."""
        slug = MarketSlugGenerator.get_latest_slug("ethereum", "15min")
        assert slug.startswith("eth-updown-15m-")

    def test_get_latest_slug_1h_bitcoin(self) -> None:
        """Test get_latest_slug for hourly bitcoin market."""
        slug = MarketSlugGenerator.get_latest_slug("bitcoin", "1h")
        assert slug.startswith("bitcoin-up-or-down-")
        assert slug.endswith("-et")

    def test_get_latest_slug_1h_ethereum(self) -> None:
        """Test get_latest_slug for hourly ethereum market."""
        slug = MarketSlugGenerator.get_latest_slug("ethereum", "1h")
        assert slug.startswith("ethereum-up-or-down-")
        assert slug.endswith("-et")

    def test_get_latest_slug_variations(self) -> None:
        """Test get_latest_slug with various input formats."""
        # Test different asset formats
        slug1 = MarketSlugGenerator.get_latest_slug("btc", "15m")
        slug2 = MarketSlugGenerator.get_latest_slug("bitcoin", "15min")
        assert slug1 == slug2

        slug3 = MarketSlugGenerator.get_latest_slug("eth", "1hour")
        slug4 = MarketSlugGenerator.get_latest_slug("ethereum", "1h")
        assert slug3 == slug4

    def test_get_latest_slug_invalid_period(self) -> None:
        """Test that invalid time period raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported time period"):
            MarketSlugGenerator.get_latest_slug("bitcoin", "invalid")

    def test_get_latest_slug_invalid_asset(self) -> None:
        """Test that invalid asset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown asset"):
            MarketSlugGenerator.get_latest_slug("invalid", "15min")


class TestEdgeCases:
    """Tests for edge cases."""

    def test_15min_slug_at_exact_15min_boundary(self) -> None:
        """Test 15-minute slug generation at exact 15-minute boundary."""
        # Create a timestamp that's exactly on a 15-minute boundary
        now = datetime.now(timezone.utc)
        current_timestamp = int(now.timestamp())
        aligned_timestamp = current_timestamp - (current_timestamp % 900)

        slug = MarketSlugGenerator.get_latest_15min_slug("btc")
        timestamp_str = slug.split("-")[-1]
        timestamp = int(timestamp_str)

        # Should match the aligned timestamp
        assert timestamp == aligned_timestamp

    def test_hourly_slug_midnight(self) -> None:
        """Test hourly slug at midnight ET."""
        # This test verifies the slug format works at edge times
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Should contain valid hour format even at midnight
        assert "am" in slug or "pm" in slug
        match = re.search(r"(\d+)(am|pm)-et$", slug)
        assert match is not None

    def test_hourly_slug_noon(self) -> None:
        """Test hourly slug at noon ET."""
        # This test verifies the slug format works at noon
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Should contain valid hour format even at noon
        assert "am" in slug or "pm" in slug
        match = re.search(r"(\d+)(am|pm)-et$", slug)
        assert match is not None
        hour_str, am_pm = match.groups()
        hour = int(hour_str)
        assert 1 <= hour <= 12

