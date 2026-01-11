"""Market discovery service implementation."""

import asyncio
import time
from typing import Protocol

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.events import MARKET_DISCOVERY, EventBus, MarketDiscoveryEvent
from polytrader.logging_config import logger
from polytrader.market_discovery.patterns import MarketPattern
from polytrader.market_discovery.state import MarketState


class IMarketDiscoveryService(Protocol):
    """Protocol for market discovery services."""

    async def get_current_market(self, pattern: str) -> str | None:
        """Get the current active market slug for a pattern.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")

        Returns:
            Market slug if found, None if no active market exists
        """
        ...

    async def get_next_market(self, pattern: str) -> str | None:
        """Get the next market slug that will become active.

        Args:
            pattern: Market pattern

        Returns:
            Next market slug if predictable, None otherwise
        """
        ...


class MarketDiscoveryService:
    """Service for discovering active markets from patterns."""

    def __init__(
        self,
        gamma_client: GammaClient | None = None,
        max_windows_ahead: int = 48,  # 12 hours for 15m markets
        max_windows_behind: int = 4,  # 1 hour for 15m markets
        bus: EventBus | None = None,  # Optional event bus for observability
    ) -> None:
        """Initialize market discovery service.

        Args:
            gamma_client: Gamma API client (optional)
            max_windows_ahead: Maximum number of windows to search ahead (default: 48)
            max_windows_behind: Maximum number of windows to search behind (default: 4)
            bus: Event bus for emitting discovery events (optional)
        """
        self.gamma = gamma_client or GammaClient()
        self._cache: dict[str, tuple[str, float]] = {}  # pattern -> (slug, expiry_time)
        self._cache_ttl = 30.0  # Cache for 30 seconds (shorter for faster market transitions)
        self.max_windows_ahead = max_windows_ahead
        self.max_windows_behind = max_windows_behind
        self.bus = bus

    async def get_current_market(self, pattern: str) -> str | None:
        """Get the current active market slug for a pattern.

        Uses adaptive search strategy: checks current window first, then expands
        forward (future markets) before checking past windows.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")

        Returns:
            Market slug if found, None if no active market exists
        """
        start_time = time.monotonic()
        windows_checked = 0

        # Check cache first
        cached = self._get_from_cache(pattern)
        if cached:
            logger.debug(
                "Using cached market: {market} for pattern: {pattern}",
                market=cached,
                pattern=pattern,
            )
            return cached

        try:
            market_pattern = MarketPattern.parse(pattern)
        except ValueError as e:
            logger.error("Invalid market pattern: {error}", error=e)
            return None

        # Calculate window boundaries
        current_end = market_pattern.get_current_window_end()
        now = int(time.time())

        # Strategy: Check current window first, then expand forward (future markets)
        # This handles markets created in advance (Polymarket pattern)

        # 1. Check current window first
        current_slug = market_pattern.generate_slug(current_end)
        windows_checked += 1
        logger.debug(
            "Checking current window market: {market} (end: {end})",
            market=current_slug,
            end=current_end,
        )
        state = await self.get_market_state(current_slug)
        if state == MarketState.ACTIVE:
            logger.info("Found active market: {market} (current window)", market=current_slug)
            self._cache_result(pattern, current_slug)
            latency_ms = (time.monotonic() - start_time) * 1000
            if self.bus:
                event = MarketDiscoveryEvent(
                    pattern=pattern,
                    discovered_market=current_slug,
                    search_strategy="current_first",
                    windows_checked=windows_checked,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                )
                await self.bus.publish(MARKET_DISCOVERY, event)
            return current_slug

        # 2. Search forward (future markets) - Polymarket creates markets in advance
        for i in range(1, self.max_windows_ahead + 1):
            future_end = current_end + (i * market_pattern.interval_seconds)
            future_slug = market_pattern.generate_slug(future_end)
            windows_checked += 1
            logger.debug(
                "Checking future window {i}: {market} (end: {end})",
                i=i,
                market=future_slug,
                end=future_end,
            )
            state = await self.get_market_state(future_slug)
            if state == MarketState.ACTIVE:
                logger.info(
                    "Found active market: {market} ({i} windows ahead)",
                    market=future_slug,
                    i=i,
                )
                self._cache_result(pattern, future_slug)
                latency_ms = (time.monotonic() - start_time) * 1000
                if self.bus:
                    event = MarketDiscoveryEvent(
                        pattern=pattern,
                        discovered_market=future_slug,
                        search_strategy="current_first",
                        windows_checked=windows_checked,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                    )
                    await self.bus.publish(MARKET_DISCOVERY, event)
                return future_slug

        # 3. Search backward (past markets) - only if no future markets found
        for i in range(1, self.max_windows_behind + 1):
            past_end = current_end - (i * market_pattern.interval_seconds)
            # Skip if market window has definitely passed (more than 1 interval past)
            if past_end + market_pattern.interval_seconds < now:
                continue
            past_slug = market_pattern.generate_slug(past_end)
            windows_checked += 1
            logger.debug(
                "Checking past window {i}: {market} (end: {end})",
                i=i,
                market=past_slug,
                end=past_end,
            )
            state = await self.get_market_state(past_slug)
            if state == MarketState.ACTIVE:
                logger.info(
                    "Found active market: {market} ({i} windows behind)",
                    market=past_slug,
                    i=i,
                )
                self._cache_result(pattern, past_slug)
                latency_ms = (time.monotonic() - start_time) * 1000
                if self.bus:
                    event = MarketDiscoveryEvent(
                        pattern=pattern,
                        discovered_market=past_slug,
                        search_strategy="current_first",
                        windows_checked=windows_checked,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                    )
                    await self.bus.publish(MARKET_DISCOVERY, event)
                return past_slug

        latency_ms = (time.monotonic() - start_time) * 1000
        logger.warning(
            "No active market found for pattern: {pattern} "
            "(checked {windows} windows, {latency_ms:.1f}ms)",
            pattern=pattern,
            windows=windows_checked,
            latency_ms=latency_ms,
        )

        # Emit discovery event
        if self.bus:
            event = MarketDiscoveryEvent(
                pattern=pattern,
                discovered_market=None,
                search_strategy="current_first",
                windows_checked=windows_checked,
                latency_ms=latency_ms,
                success=False,
                error=f"No active market found after checking {windows_checked} windows",
            )
            await self.bus.publish(MARKET_DISCOVERY, event)

        return None

    async def get_next_market(self, pattern: str) -> str | None:
        """Get the next market slug that will become active.

        Args:
            pattern: Market pattern

        Returns:
            Next market slug if predictable, None otherwise
        """
        try:
            market_pattern = MarketPattern.parse(pattern)
        except ValueError as e:
            logger.error("Invalid market pattern: {error}", error=e)
            return None

        next_end = market_pattern.get_next_window_end()
        next_slug = market_pattern.generate_slug(next_end)

        # Validate that market exists (or will exist soon)
        if await self._market_exists(next_slug):
            return next_slug

        return None

    async def get_market_state(self, slug: str) -> MarketState:
        """Get the actual state of a market.

        Checks if market exists and is tradeable. This is more comprehensive
        than _market_exists() as it validates market state.

        Args:
            slug: Market slug to check

        Returns:
            MarketState enum indicating the market's state
        """
        try:
            # Wrap synchronous call in asyncio.to_thread
            market = await asyncio.to_thread(self.gamma.get_market_by_slug, slug)
            if market is None:
                return MarketState.NOT_FOUND

            # For now, if market exists in Gamma API, consider it active
            # TODO: Add more validation:
            # - Check if market end_time has passed (EXPIRED)
            # - Check if market is resolved (RESOLVED)
            # - Check if orderbook exists via CLOB API (NO_ORDERBOOK)
            # This requires additional API calls or market metadata

            return MarketState.ACTIVE
        except Exception as e:
            # 404 or other error means market doesn't exist
            logger.debug("Market {slug} not found: {error}", slug=slug, error=e)
            return MarketState.NOT_FOUND

    async def _market_exists(self, slug: str) -> bool:
        """Check if a market exists and is active.

        Deprecated: Use get_market_state() instead for more comprehensive checks.

        Args:
            slug: Market slug to check

        Returns:
            True if market exists and is active, False otherwise
        """
        state = await self.get_market_state(slug)
        return state == MarketState.ACTIVE

    def _get_from_cache(self, pattern: str) -> str | None:
        """Get cached result if still valid.

        Also validates that the cached market is still in the correct time window.
        This prevents using stale markets when markets transition.

        Args:
            pattern: Market pattern

        Returns:
            Cached slug if valid, None otherwise
        """
        if pattern not in self._cache:
            return None

        slug, expiry = self._cache[pattern]
        if time.time() >= expiry:
            # Cache expired
            del self._cache[pattern]
            return None

        # Additional validation: check if cached market is still in the correct window
        try:
            market_pattern = MarketPattern.parse(pattern)
            # Extract timestamp from slug (last part after final dash)
            if "-" in slug:
                cached_timestamp = int(slug.split("-")[-1])
                # Calculate what the current market should be
                current_end = market_pattern.get_current_window_end()
                prev_end = current_end - market_pattern.interval_seconds

                # Cached market should be either current or previous window
                if cached_timestamp not in (current_end, prev_end):
                    # Cached market is from wrong window, invalidate cache
                    logger.debug(
                        "Invalidating cache: cached market {cached} not in current window "
                        "(current: {current}, prev: {prev})",
                        cached=slug,
                        current=f"{pattern}-{current_end}",
                        prev=f"{pattern}-{prev_end}",
                    )
                    del self._cache[pattern]
                    return None
        except (ValueError, IndexError):
            # If we can't parse, just use the cache (fallback)
            pass

        return slug

    def _cache_result(self, pattern: str, slug: str) -> None:
        """Cache a discovery result.

        Args:
            pattern: Market pattern
            slug: Market slug
        """
        expiry = time.time() + self._cache_ttl
        self._cache[pattern] = (slug, expiry)
