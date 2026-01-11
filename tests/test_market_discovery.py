"""Tests for market discovery service."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.market_discovery import MarketDiscoveryService, MarketPattern


def test_market_pattern_get_current_window_end_finds_current_market() -> None:
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


@pytest.mark.asyncio
async def test_market_discovery_finds_current_market_not_future() -> None:
    """Test that MarketDiscoveryService finds the current active market.

    This test verifies that when we're in the middle of a 15-minute window,
    the discovery service finds the market for the current window, not the
    next future window.
    """
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected current market
    now = int(time.time())
    current_window_start = (now // interval) * interval
    expected_end = current_window_start + interval
    expected_slug = f"btc-updown-15m-{expected_end}"

    # Mock GammaClient to return market for current window
    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    # Mock _market_exists to return True for current market
    with patch.object(discovery, "_market_exists", new_callable=AsyncMock) as mock_exists:
        # Return True for current market, False for others
        def market_exists_side_effect(slug: str) -> bool:
            return slug == expected_slug

        mock_exists.side_effect = market_exists_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the current market, not a future one
        assert result == expected_slug
        assert result is not None

        # Verify it checked the current window first
        assert mock_exists.called
        # Should have checked the current window slug
        call_args = [call[0][0] for call in mock_exists.call_args_list]
        assert expected_slug in call_args


@pytest.mark.asyncio
async def test_market_discovery_prioritizes_previous_window() -> None:
    """Test that MarketDiscoveryService prioritizes previous window (active market).

    Markets often remain active/tradeable even after their end time, so we should
    check the previous window first to find the currently active market.
    """
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval

    prev_slug = f"btc-updown-15m-{prev_end}"
    current_slug = f"btc-updown-15m-{current_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "_market_exists", new_callable=AsyncMock) as mock_exists:
        # Both previous and current exist, but previous should be returned first
        def market_exists_side_effect(slug: str) -> bool:
            return slug in (prev_slug, current_slug)

        mock_exists.side_effect = market_exists_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the previous market first (prioritized)
        assert result == prev_slug
        assert result is not None

        # Verify it checked previous window first
        call_args = [call[0][0] for call in mock_exists.call_args_list]
        assert call_args[0] == prev_slug, "Should check previous window first"
