"""Tests for market discovery module."""

import re

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

    def test_normalize_case_insensitive(self) -> None:
        """Test that asset normalization is case insensitive."""
        short1, long1 = MarketSlugGenerator.normalize_asset("BITCOIN")
        short2, long2 = MarketSlugGenerator.normalize_asset("bTc")
        assert short1 == short2 == "btc"
        assert long1 == long2 == "bitcoin"

    def test_normalize_invalid_asset(self) -> None:
        """Test that invalid asset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown asset"):
            MarketSlugGenerator.normalize_asset("invalid")


class TestNormalizeTimePeriod:
    """Tests for time period normalization."""

    def test_normalize_15m(self) -> None:
        """Test normalizing 15m period."""
        assert MarketSlugGenerator.normalize_time_period("15m") == "15min"

    def test_normalize_1h(self) -> None:
        """Test normalizing 1h period."""
        assert MarketSlugGenerator.normalize_time_period("1h") == "1h"

    def test_normalize_case_insensitive(self) -> None:
        """Test that time period normalization is case insensitive."""
        assert MarketSlugGenerator.normalize_time_period("15M") == "15min"
        assert MarketSlugGenerator.normalize_time_period("1H") == "1h"

    def test_normalize_invalid_period(self) -> None:
        """Test that invalid time period raises ValueError."""
        with pytest.raises(ValueError, match="Unknown time period"):
            MarketSlugGenerator.normalize_time_period("invalid")


class Test15MinSlug:
    """Tests for 15-minute market slug generation."""

    def test_15min_slug_format(self) -> None:
        """Test 15-minute slug format."""
        btc_slug = MarketSlugGenerator.get_latest_15min_slug("bitcoin")
        eth_slug = MarketSlugGenerator.get_latest_15min_slug("ethereum")

        assert btc_slug.startswith("btc-updown-15m-")
        assert eth_slug.startswith("eth-updown-15m-")
        assert btc_slug.split("-")[-1].isdigit()
        assert eth_slug.split("-")[-1].isdigit()

    def test_15min_slug_timestamp_alignment(self) -> None:
        """Test that timestamp is aligned to 15-minute intervals."""
        slug = MarketSlugGenerator.get_latest_15min_slug("btc")
        timestamp_str = slug.split("-")[-1]
        timestamp = int(timestamp_str)

        # Check that timestamp is divisible by 900 (15 minutes)
        assert timestamp % 900 == 0

    def test_15min_slug_consistency(self) -> None:
        """Test that multiple calls within same interval return same slug."""
        slug1 = MarketSlugGenerator.get_latest_15min_slug("btc")
        slug2 = MarketSlugGenerator.get_latest_15min_slug("btc")
        assert slug1 == slug2


class TestHourlySlug:
    """Tests for hourly market slug generation."""

    def test_hourly_slug_format(self) -> None:
        """Test hourly slug format."""
        btc_slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        eth_slug = MarketSlugGenerator.get_latest_hourly_slug("ethereum")

        assert btc_slug.startswith("bitcoin-up-or-down-")
        assert eth_slug.startswith("ethereum-up-or-down-")
        assert btc_slug.endswith("-et")
        assert eth_slug.endswith("-et")
        assert "am" in btc_slug or "pm" in btc_slug
        assert "am" in eth_slug or "pm" in eth_slug

    def test_hourly_slug_contains_valid_hour(self) -> None:
        """Test that hourly slug contains valid hour format."""
        slug = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        # Pattern: {hour}am or {hour}pm
        match = re.search(r"(\d+)(am|pm)-et$", slug)
        assert match is not None
        hour_str, am_pm = match.groups()
        hour = int(hour_str)
        assert 1 <= hour <= 12
        assert am_pm in ("am", "pm")

    def test_hourly_slug_consistency(self) -> None:
        """Test that multiple calls within same hour return same slug."""
        slug1 = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        slug2 = MarketSlugGenerator.get_latest_hourly_slug("bitcoin")
        assert slug1 == slug2


class TestGetLatestSlug:
    """Tests for get_latest_slug integration method."""

    def test_get_latest_slug_15m(self) -> None:
        """Test get_latest_slug for 15-minute markets."""
        btc_slug = MarketSlugGenerator.get_latest_slug("bitcoin", "15m")
        eth_slug = MarketSlugGenerator.get_latest_slug("ethereum", "15m")

        assert btc_slug.startswith("btc-updown-15m-")
        assert eth_slug.startswith("eth-updown-15m-")

    def test_get_latest_slug_1h(self) -> None:
        """Test get_latest_slug for hourly markets."""
        btc_slug = MarketSlugGenerator.get_latest_slug("bitcoin", "1h")
        eth_slug = MarketSlugGenerator.get_latest_slug("ethereum", "1h")

        assert btc_slug.startswith("bitcoin-up-or-down-")
        assert eth_slug.startswith("ethereum-up-or-down-")
        assert btc_slug.endswith("-et")
        assert eth_slug.endswith("-et")

    def test_get_latest_slug_asset_variations(self) -> None:
        """Test get_latest_slug with different asset formats."""
        slug1 = MarketSlugGenerator.get_latest_slug("btc", "15m")
        slug2 = MarketSlugGenerator.get_latest_slug("bitcoin", "15m")
        assert slug1 == slug2

    def test_get_latest_slug_invalid_period(self) -> None:
        """Test that invalid time period raises ValueError."""
        with pytest.raises(ValueError, match="Unknown time period"):
            MarketSlugGenerator.get_latest_slug("bitcoin", "invalid")

    def test_get_latest_slug_invalid_asset(self) -> None:
        """Test that invalid asset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown asset"):
            MarketSlugGenerator.get_latest_slug("invalid", "15m")
