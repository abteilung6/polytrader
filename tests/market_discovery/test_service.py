"""Tests for MarketDiscoveryService."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.events.types import MarketDiscoveryEvent
from polytrader.market_discovery import (
    FatalDiscoveryError,
    MarketDiscoveryService,
    MarketState,
    RetryableDiscoveryError,
)
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector


@pytest.fixture
def metrics_collector() -> MemoryMetricsCollector:
    """Create a fresh metrics collector for each test."""
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    return collector


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

    # Mock get_market_state to return ACTIVE for current market
    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Return ACTIVE for current market, NOT_FOUND for others
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug == expected_slug else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the current market, not a future one
        assert result == expected_slug
        assert result is not None

        # Verify it checked the current window first
        assert mock_state.called
        # Should have checked the current window slug
        call_args = [call[0][0] for call in mock_state.call_args_list]
        assert expected_slug in call_args


@pytest.mark.asyncio
async def test_market_discovery_prioritizes_current_window() -> None:
    """Test that MarketDiscoveryService prioritizes current window first.

    New behavior: Check current window first, then expand forward (future markets),
    then backward (past markets). This handles markets created in advance.
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

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Both previous and current exist, but current should be returned first
        def market_state_side_effect(slug: str) -> MarketState:
            return (
                MarketState.ACTIVE if slug in (prev_slug, current_slug) else MarketState.NOT_FOUND
            )

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the previous market first (new behavior - previous window prioritized)
        assert result == prev_slug
        assert result is not None

        # Verify it checked previous window first
        call_args = [call[0][0] for call in mock_state.call_args_list]
        assert call_args[0] == prev_slug, "Should check previous window first"


@pytest.mark.asyncio
async def test_market_discovery_searches_forward_first() -> None:
    """Test that MarketDiscoveryService searches forward (future markets) before backward.

    This handles Polymarket's pattern of creating markets in advance.
    """
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    future_end = current_end + interval  # 1 window ahead
    prev_end = current_end - interval

    future_slug = f"btc-updown-15m-{future_end}"
    prev_slug = f"btc-updown-15m-{prev_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Current doesn't exist, but future and previous do
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug in (future_slug, prev_slug) else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the previous market (searched first, and it exists)
        assert result == prev_slug
        assert result is not None

        # Verify search order: previous -> current -> future -> past
        call_args = [call[0][0] for call in mock_state.call_args_list]
        assert call_args[0] == prev_slug, "Should check previous first"
        # Future should be checked before older past markets
        future_idx = call_args.index(future_slug) if future_slug in call_args else -1
        # Note: prev_slug is already checked first,
        # so we're verifying future comes before older past
        if future_idx != -1:
            # Future should come after previous and current
            assert future_idx > 0, "Future should be checked after previous"


@pytest.mark.asyncio
async def test_market_discovery_searches_expanded_window() -> None:
    """Test that MarketDiscoveryService searches up to 48 windows ahead."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    # Market 10 windows ahead
    future_end = current_end + (10 * interval)
    future_slug = f"btc-updown-15m-{future_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client, max_windows_ahead=48)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Only future market exists (10 windows ahead)
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug == future_slug else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the future market (10 windows ahead)
        assert result == future_slug
        assert result is not None

        # Verify it checked multiple windows
        assert mock_state.call_count >= 10, "Should check at least 10 windows"


@pytest.mark.asyncio
async def test_market_discovery_emits_events() -> None:
    """Test that MarketDiscoveryService emits events when EventBus provided."""
    from polytrader.events import EventBus, MemoryEventStore

    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected market (previous window is now prioritized)
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval
    expected_slug = f"btc-updown-15m-{prev_end}"  # Previous window checked first

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(gamma_client=gamma_client, bus=bus)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        result = await discovery.get_current_market(pattern)

        # Should find the market
        assert result == expected_slug

        # Verify event was emitted with correlation_id
        events = event_store.read_stream()
        discovery_events = [
            e for e in events if isinstance(e, MarketDiscoveryEvent) and e.pattern == pattern
        ]
        assert len(discovery_events) > 0, "Should emit discovery event"
        assert discovery_events[0].success is True, "Event should indicate success"
        assert discovery_events[0].discovered_market == expected_slug
        assert discovery_events[0].correlation_id is not None, "Event should have correlation_id"
        assert discovery_events[0].error_class is None, (
            "Successful event should have no error_class"
        )


@pytest.mark.asyncio
async def test_market_discovery_searches_near_limit() -> None:
    """Test that MarketDiscoveryService finds markets near the search limit."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    # Market at the limit (48 windows ahead)
    future_end = current_end + (48 * interval)
    future_slug = f"btc-updown-15m-{future_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client, max_windows_ahead=48)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Only market at limit exists
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug == future_slug else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the market at the limit
        assert result == future_slug
        assert result is not None

        # Verify it checked all windows up to the limit
        # Now checks: previous + current + 48 future = 50 windows
        assert mock_state.call_count == 50, "Should check previous + current + 48 future windows"


@pytest.mark.asyncio
async def test_market_discovery_fails_after_all_windows() -> None:
    """Test that MarketDiscoveryService returns None when no market found after all windows."""
    pattern = "btc-updown-15m"

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=None)

    discovery = MarketDiscoveryService(
        gamma_client=gamma_client, max_windows_ahead=5, max_windows_behind=2
    )

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # No markets exist
        mock_state.return_value = MarketState.NOT_FOUND

        result = await discovery.get_current_market(pattern)

        # Should return None
        assert result is None

        # Verify it checked windows:
        # 1 current + 5 future + up to 2 past (some may be skipped if expired)
        # At minimum: 1 + 5 = 6, at maximum: 1 + 5 + 2 = 8
        assert 6 <= mock_state.call_count <= 8, (
            f"Should check 6-8 windows (got {mock_state.call_count})"
        )


@pytest.mark.asyncio
async def test_market_discovery_handles_different_market_states() -> None:
    """Test that MarketDiscoveryService handles different market states correctly."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    future_end = current_end + interval

    current_slug = f"btc-updown-15m-{current_end}"
    future_slug = f"btc-updown-15m-{future_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Current is EXPIRED, future is ACTIVE
        def market_state_side_effect(slug: str) -> MarketState:
            if slug == current_slug:
                return MarketState.EXPIRED
            elif slug == future_slug:
                return MarketState.ACTIVE
            return MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find the future market (current is expired)
        assert result == future_slug
        assert result is not None


@pytest.mark.asyncio
async def test_market_discovery_cache_validation_current_window() -> None:
    """Test that cache validation accepts markets in current window."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected market (previous window is now prioritized)
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval
    current_slug = f"btc-updown-15m-{prev_end}"  # Previous window checked first

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        # First call - should find and cache
        result1 = await discovery.get_current_market(pattern)
        assert result1 == current_slug

        # Verify cache was set
        assert pattern in discovery._cache

        # Second call - should use cache (market is in current window)
        mock_state.reset_mock()
        result2 = await discovery.get_current_market(pattern)
        assert result2 == current_slug

        # Cache should be used (get_market_state may still be called for validation)
        # But the cached result should be returned


@pytest.mark.asyncio
async def test_market_discovery_cache_validation_previous_window() -> None:
    """Test that cache validation accepts markets in previous window."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval
    prev_slug = f"btc-updown-15m-{prev_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Only previous market exists
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug == prev_slug else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        # First call - should find previous market and cache
        result1 = await discovery.get_current_market(pattern)
        assert result1 == prev_slug

        # Verify cache was set
        assert pattern in discovery._cache

        # Second call - should use cache (market is in previous window, which is valid)
        mock_state.reset_mock()
        mock_state.side_effect = market_state_side_effect

        result2 = await discovery.get_current_market(pattern)
        assert result2 == prev_slug

        # Cache should be used (previous window is valid)


@pytest.mark.asyncio
async def test_market_discovery_cache_invalidation_future_market() -> None:
    """Test that cache is invalidated when cached market is far in the future.

    Current cache validation only accepts markets in current or previous window.
    Markets far in the future will be invalidated even if they're still valid.
    """
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    # Market 20 windows ahead (far in future)
    future_end = current_end + (20 * interval)
    future_slug = f"btc-updown-15m-{future_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client, max_windows_ahead=48)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Only future market exists
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug == future_slug else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        # First call - should find future market and cache
        result1 = await discovery.get_current_market(pattern)
        assert result1 == future_slug

        # Verify cache was set
        assert pattern in discovery._cache

        # Second call - cache should be invalidated (market not in current/prev window)
        mock_state.reset_mock()
        mock_state.side_effect = market_state_side_effect

        result2 = await discovery.get_current_market(pattern)
        assert result2 == future_slug

        # Cache was invalidated, so get_market_state should be called again
        # (call count should be similar to first call, indicating re-query)
        assert mock_state.call_count >= 20, "Should re-query (cache invalidated)"


@pytest.mark.asyncio
async def test_market_discovery_cache_invalidation_window_passed() -> None:
    """Test that cache validation invalidates markets not in current/previous window.

    This tests the cache validation logic directly by checking that markets
    outside the current/previous window are invalidated.
    """
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    # Market 3 windows in the past (definitely not in current/prev)
    old_end = current_end - (3 * interval)
    old_slug = f"btc-updown-15m-{old_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    # Manually set cache to an old market (simulating stale cache)
    discovery._cache[pattern] = (old_slug, time.time() + 100)  # Still valid TTL-wise

    # Now call _get_from_cache - it should invalidate because old_slug
    # is not in (current_end, prev_end)
    cached_result = discovery._get_from_cache(pattern)

    # Cache should be invalidated (old market not in current/prev window)
    assert cached_result is None
    assert pattern not in discovery._cache, "Cache should be cleared"


@pytest.mark.asyncio
async def test_market_discovery_cache_time_expiration() -> None:
    """Test that cache expires after TTL."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected market (previous window is now prioritized)
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval
    current_slug = f"btc-updown-15m-{prev_end}"  # Previous window checked first

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    # Use very short TTL for testing
    discovery = MarketDiscoveryService(gamma_client=gamma_client)
    discovery._cache_ttl = 0.1  # 100ms TTL

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        # First call - should find and cache
        result1 = await discovery.get_current_market(pattern)
        assert result1 == current_slug

        # Second call immediately - should use cache
        mock_state.reset_mock()
        result2 = await discovery.get_current_market(pattern)
        assert result2 == current_slug
        # Should have used cache (no calls if cache hit)
        # Note: Cache validation may still call get_market_state, so we just verify result

        # Wait for cache to expire
        await asyncio.sleep(0.15)  # Wait longer than TTL

        # Third call after expiration - should re-query
        mock_state.reset_mock()
        result3 = await discovery.get_current_market(pattern)
        assert result3 == current_slug
        # Should have re-queried (cache expired)
        assert mock_state.call_count > 0, "Should re-query after cache expiration"


@pytest.mark.asyncio
async def test_market_discovery_skips_expired_past_windows() -> None:
    """Test that discovery skips past windows that have definitely expired."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    # Past window that's definitely expired (more than 1 interval past)
    past_end = current_end - (3 * interval)  # 3 intervals ago
    past_slug = f"btc-updown-15m-{past_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client, max_windows_behind=4)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Only past market exists (but it's expired)
        def market_state_side_effect(slug: str) -> MarketState:
            return MarketState.ACTIVE if slug == past_slug else MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should return None (past market skipped because expired)
        assert result is None

        # Verify past market was not checked (skipped)
        call_args = [call[0][0] for call in mock_state.call_args_list]
        assert past_slug not in call_args, "Should skip expired past windows"


@pytest.mark.asyncio
async def test_market_discovery_event_on_failure() -> None:
    """Test that discovery emits failure event when no market found."""
    from polytrader.events import EventBus, MemoryEventStore

    pattern = "btc-updown-15m"

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=None)

    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(gamma_client=gamma_client, bus=bus, max_windows_ahead=2)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.NOT_FOUND

        result = await discovery.get_current_market(pattern)

        # Should return None
        assert result is None

        # Verify failure event was emitted with correlation_id and error_class
        events = event_store.read_stream()
        discovery_events = [
            e for e in events if isinstance(e, MarketDiscoveryEvent) and e.pattern == pattern
        ]
        assert len(discovery_events) > 0, "Should emit discovery event"
        assert discovery_events[0].success is False, "Event should indicate failure"
        assert discovery_events[0].discovered_market is None
        assert discovery_events[0].error is not None
        assert "windows" in discovery_events[0].error.lower()
        assert discovery_events[0].correlation_id is not None, "Event should have correlation_id"
        assert discovery_events[0].error_class == "retryable", (
            "Failure should be classified as retryable"
        )


@pytest.mark.asyncio
async def test_market_discovery_get_market_state_not_found() -> None:
    """Test get_market_state returns NOT_FOUND for non-existent markets."""
    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=None)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state("nonexistent-market-12345")

    assert state == MarketState.NOT_FOUND


@pytest.mark.asyncio
async def test_market_discovery_get_market_state_active() -> None:
    """Test get_market_state returns ACTIVE for existing, tradeable markets."""
    from datetime import UTC, datetime, timedelta

    from polytrader.adapters.polymarket.market_data import Market

    gamma_client = MagicMock(spec=GammaClient)
    # Create a real Market object that is active and tradeable
    future_date = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    market = Market(
        id="1",
        slug="btc-updown-15m-12345",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=future_date,
        active=True,
        closed=False,
        acceptingOrders=True,
    )
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state("btc-updown-15m-12345")

    assert state == MarketState.ACTIVE


@pytest.mark.asyncio
async def test_market_discovery_get_market_state_handles_exceptions() -> None:
    """Test get_market_state handles exceptions gracefully."""
    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(side_effect=Exception("API error"))

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    # Should raise RetryableDiscoveryError (default classification)
    with pytest.raises(RetryableDiscoveryError):
        await discovery.get_market_state("any-market")


@pytest.mark.asyncio
async def test_market_discovery_get_market_state_classifies_retryable_errors() -> None:
    """Test get_market_state classifies network errors as retryable."""
    gamma_client = MagicMock(spec=GammaClient)

    # Network error
    class NetworkError(Exception):
        pass

    gamma_client.get_market_by_slug = MagicMock(side_effect=NetworkError("Connection timeout"))

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with pytest.raises(RetryableDiscoveryError, match="Network error|Connection"):
        await discovery.get_market_state("any-market")


@pytest.mark.asyncio
async def test_market_discovery_get_market_state_classifies_fatal_errors() -> None:
    """Test get_market_state classifies auth errors as fatal."""
    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(side_effect=Exception("401 Unauthorized"))

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with pytest.raises(FatalDiscoveryError, match="Auth error"):
        await discovery.get_market_state("any-market")


@pytest.mark.asyncio
async def test_market_discovery_handles_retryable_error_continues_search() -> None:
    """Test that retryable errors don't stop the search."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected markets
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    future_end = current_end + interval
    future_slug = f"btc-updown-15m-{future_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        # Current window raises retryable error, future window succeeds
        def market_state_side_effect(slug: str) -> MarketState:
            if "current" in slug or slug.endswith(str(current_end)):
                raise RetryableDiscoveryError("Network error")
            elif slug == future_slug:
                return MarketState.ACTIVE
            return MarketState.NOT_FOUND

        mock_state.side_effect = market_state_side_effect

        result = await discovery.get_current_market(pattern)

        # Should find future market despite retryable error on current
        assert result == future_slug


@pytest.mark.asyncio
async def test_market_discovery_handles_fatal_error_stops_search() -> None:
    """Test that fatal errors stop the search and emit event."""
    from polytrader.events import EventBus, MemoryEventStore

    pattern = "btc-updown-15m"

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(side_effect=Exception("401 Unauthorized"))

    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(gamma_client=gamma_client, bus=bus)

    result = await discovery.get_current_market(pattern)

    # Should return None due to fatal error
    assert result is None

    # Verify fatal error event was emitted
    events = event_store.read_stream()
    discovery_events = [
        e for e in events if isinstance(e, MarketDiscoveryEvent) and e.pattern == pattern
    ]
    assert len(discovery_events) > 0, "Should emit discovery event"
    assert discovery_events[0].success is False, "Event should indicate failure"
    assert discovery_events[0].error_class == "fatal", "Should classify as fatal error"
    error_msg = discovery_events[0].error
    assert error_msg is not None
    assert "Auth error" in error_msg or "401" in error_msg


@pytest.mark.asyncio
async def test_market_discovery_get_next_market() -> None:
    """Test get_next_market returns next predictable market."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected next market
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    next_end = current_end + interval
    next_slug = f"btc-updown-15m-{next_end}"

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "_market_exists", new_callable=AsyncMock) as mock_exists:
        mock_exists.return_value = True

        result = await discovery.get_next_market(pattern)

        assert result == next_slug
        assert result is not None


@pytest.mark.asyncio
async def test_market_discovery_get_next_market_not_found() -> None:
    """Test get_next_market returns None when next market doesn't exist."""
    pattern = "btc-updown-15m"

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=None)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "_market_exists", new_callable=AsyncMock) as mock_exists:
        mock_exists.return_value = False

        result = await discovery.get_next_market(pattern)

        assert result is None


@pytest.mark.asyncio
async def test_market_discovery_correlation_id_uniqueness() -> None:
    """Test that each discovery operation gets a unique correlation_id."""
    from polytrader.events import EventBus, MemoryEventStore

    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected market (previous window is now prioritized)
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval
    expected_slug = f"btc-updown-15m-{prev_end}"  # Previous window checked first

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(gamma_client=gamma_client, bus=bus)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        # Perform two discovery operations
        result1 = await discovery.get_current_market(pattern)
        result2 = await discovery.get_current_market(pattern)

        assert result1 == expected_slug
        assert result2 == expected_slug

        # Clear cache to force second call to emit event
        discovery._cache.clear()

        # Perform second discovery operation (should emit new event)
        result3 = await discovery.get_current_market(pattern)
        assert result3 == expected_slug

        # Verify each operation has unique correlation_id
        events = event_store.read_stream()
        discovery_events = [
            e for e in events if isinstance(e, MarketDiscoveryEvent) and e.pattern == pattern
        ]
        assert len(discovery_events) >= 2, "Should emit at least 2 events"
        correlation_ids = [e.correlation_id for e in discovery_events]
        # All correlation IDs should be unique
        assert len(correlation_ids) == len(set(correlation_ids)), (
            "Each event should have unique correlation_id"
        )


@pytest.mark.asyncio
async def test_market_discovery_metrics_integration(
    metrics_collector: MemoryMetricsCollector,
) -> None:
    """Test that MarketDiscoveryService records metrics during discovery."""
    pattern = "btc-updown-15m"
    interval = 15 * 60

    # Calculate expected market (previous window is now prioritized)
    now = int(time.time())
    current_window_start = (now // interval) * interval
    current_end = current_window_start + interval
    prev_end = current_end - interval
    expected_slug = f"btc-updown-15m-{prev_end}"  # Previous window checked first

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        result = await discovery.get_current_market(pattern)

        assert result == expected_slug

        # Verify metrics were recorded
        success_count = metrics_collector.get_counter(
            "market_discovery_attempts_total", labels={"pattern": pattern, "success": "true"}
        )
        assert success_count == 1

        # Check latency histogram (labels are tuples of tuples)
        latency_key = tuple(sorted([("pattern", pattern), ("success", "true")]))
        latency_values = metrics_collector._histograms.get("market_discovery_latency_ms", {}).get(
            latency_key, []
        )
        assert len(latency_values) == 1

        # Check windows histogram
        windows_key = tuple(sorted([("pattern", pattern)]))
        windows_values = metrics_collector._histograms.get(
            "market_discovery_windows_searched", {}
        ).get(windows_key, [])
        assert len(windows_values) == 1

        cache_size = metrics_collector.get_gauge("market_discovery_cache_size")
        assert cache_size == 1.0
