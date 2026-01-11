"""Market discovery service implementation."""

import asyncio
import time
from typing import Protocol

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.common.ids import generate_correlation_id
from polytrader.events import MARKET_DISCOVERY, EventBus, MarketDiscoveryEvent
from polytrader.logging_config import logger
from polytrader.market_discovery.errors import (
    FatalDiscoveryError,
    RetryableDiscoveryError,
)
from polytrader.market_discovery.metrics import (
    record_cache_hit,
    record_cache_miss,
    record_discovery_attempt,
    record_discovery_failure,
    record_discovery_latency,
    record_windows_searched,
    update_cache_size_gauge,
    update_windows_checked_gauge,
)
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

        Per observability.mdc: Emits events with correlation_id and records metrics.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")

        Returns:
            Market slug if found, None if no active market exists
        """
        correlation_id = generate_correlation_id()
        start_time = time.monotonic()
        windows_checked = 0
        error_class: str | None = None
        error_reason: str | None = None

        # Check cache first
        cached = self._get_from_cache(pattern)
        if cached:
            record_cache_hit(pattern)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=cached,
            ).debug(
                "Using cached market: {market} for pattern: {pattern}",
                market=cached,
                pattern=pattern,
            )
            return cached

        record_cache_miss(pattern)

        try:
            market_pattern = MarketPattern.parse(pattern)
        except ValueError as e:
            logger.error("Invalid market pattern: {error}", error=e)
            return None

        # Calculate window boundaries
        current_end = market_pattern.get_current_window_end()
        now = int(time.time())

        # Log window calculation for debugging
        window_start = current_end - market_pattern.interval_seconds
        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            now=now,
            current_window_start=window_start,
            current_window_end=current_end,
            interval_seconds=market_pattern.interval_seconds,
        ).info(
            "🔍 Market discovery: pattern={pattern}, now={now}, "
            "current_window={start}..{end} (interval={interval}s)",
            pattern=pattern,
            now=now,
            start=window_start,
            end=current_end,
            interval=market_pattern.interval_seconds,
        )

        # Strategy: Always check the previous window first (most recently ended market),
        # as it's often still tradeable even after its window has ended.
        # Then check current window, then future markets, then older past markets.
        # This ensures we find the active market that just ended before checking future markets.

        # Calculate if we're past the current window's end time
        is_past_current_window = now >= current_end
        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            is_past_current_window=is_past_current_window,
            now=now,
            current_end=current_end,
            window_start=window_start,
        ).debug(
            "Window check: is_past_current_window={is_past} (now={now}, window={start}..{end})",
            is_past=is_past_current_window,
            now=now,
            start=window_start,
            end=current_end,
        )

        # 1. Always check the previous window first (most recently ended market)
        # This market may still be tradeable even after its window ended
        # Previous window ends at: current_window_start (which is current_end - interval)
        prev_end = window_start  # window_start is already current_end - interval
        prev_slug = market_pattern.generate_slug(prev_end)
        windows_checked += 1
        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            market_slug=prev_slug,
            prev_end=prev_end,
        ).debug(
            "🔍 Checking previous window (most recent): {market} (end={end})",
            market=prev_slug,
            end=prev_end,
        )
        try:
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=prev_slug,
                prev_end=prev_end,
            ).debug(
                "🔍 Checking previous window: {market} (end={end})",
                market=prev_slug,
                end=prev_end,
            )
            state = await self.get_market_state(prev_slug)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=prev_slug,
                state=state.value,
            ).info(
                "🔍 Previous window state: {market} = {state}",
                market=prev_slug,
                state=state.value,
            )
            if state == MarketState.ACTIVE:
                self._cache_result(pattern, prev_slug)
                latency_ms = (time.monotonic() - start_time) * 1000
                record_discovery_attempt(pattern, success=True)
                record_discovery_latency(pattern, latency_ms, success=True)
                record_windows_searched(pattern, windows_checked)
                update_windows_checked_gauge(pattern, windows_checked)
                update_cache_size_gauge(len(self._cache))
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=prev_slug,
                    latency_ms=latency_ms,
                    windows_checked=windows_checked,
                    search_strategy="previous_first",
                ).info(
                    "Found active market: {market} (previous window, most recent)",
                    market=prev_slug,
                )
                if self.bus:
                    event = MarketDiscoveryEvent(
                        correlation_id=correlation_id,
                        pattern=pattern,
                        discovered_market=prev_slug,
                        search_strategy="previous_first",
                        windows_checked=windows_checked,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                        error_class=None,
                    )
                    await self.bus.publish(MARKET_DISCOVERY, event)
                return prev_slug
        except (RetryableDiscoveryError, FatalDiscoveryError):
            # Continue search on errors
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=prev_slug,
            ).warning("🔍 Previous window error: {market}", market=prev_slug)
            pass

            # 2. Check current window (only if previous window is not ACTIVE)
            prev_end = current_end - market_pattern.interval_seconds
            prev_slug = market_pattern.generate_slug(prev_end)
            windows_checked += 1
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=prev_slug,
            ).debug(
                "Checking previous window market (most recent): {market} (end: {end})",
                market=prev_slug,
                end=prev_end,
            )
            try:
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=prev_slug,
                    prev_end=prev_end,
                ).debug(
                    "🔍 Checking previous window: {market} (end={end})",
                    market=prev_slug,
                    end=prev_end,
                )
                state = await self.get_market_state(prev_slug)
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=prev_slug,
                    state=state.value,
                ).info(
                    "🔍 Previous window state: {market} = {state}",
                    market=prev_slug,
                    state=state.value,
                )
                if state == MarketState.ACTIVE:
                    self._cache_result(pattern, prev_slug)
                    latency_ms = (time.monotonic() - start_time) * 1000
                    record_discovery_attempt(pattern, success=True)
                    record_discovery_latency(pattern, latency_ms, success=True)
                    record_windows_searched(pattern, windows_checked)
                    update_windows_checked_gauge(pattern, windows_checked)
                    update_cache_size_gauge(len(self._cache))
                    logger.bind(
                        correlation_id=correlation_id,
                        pattern=pattern,
                        market_slug=prev_slug,
                        latency_ms=latency_ms,
                        windows_checked=windows_checked,
                        search_strategy="previous_first",
                    ).info(
                        "Found active market: {market} (previous window, most recent)",
                        market=prev_slug,
                    )
                    if self.bus:
                        event = MarketDiscoveryEvent(
                            correlation_id=correlation_id,
                            pattern=pattern,
                            discovered_market=prev_slug,
                            search_strategy="previous_first",
                            windows_checked=windows_checked,
                            latency_ms=latency_ms,
                            success=True,
                            error=None,
                            error_class=None,
                        )
                        await self.bus.publish(MARKET_DISCOVERY, event)
                    return prev_slug
            except (RetryableDiscoveryError, FatalDiscoveryError):
                # Continue search on errors
                pass

        # 2. Check current window
        current_slug = market_pattern.generate_slug(current_end)
        windows_checked += 1
        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            market_slug=current_slug,
        ).debug(
            "Checking current window market: {market} (end: {end})",
            market=current_slug,
            end=current_end,
        )
        try:
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=current_slug,
                current_end=current_end,
            ).debug(
                "🔍 Checking current window: {market} (end={end})",
                market=current_slug,
                end=current_end,
            )
            state = await self.get_market_state(current_slug)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=current_slug,
                state=state.value,
            ).info(
                "🔍 Current window state: {market} = {state}",
                market=current_slug,
                state=state.value,
            )
        except RetryableDiscoveryError as e:
            error_class = "retryable"
            error_reason = "api_error"
            record_discovery_failure(pattern, error_reason, error_class)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                error_class=error_class,
            ).warning("Retryable error checking market: {error}", error=e)
            # Continue search, but note the error
            state = MarketState.NOT_FOUND
        except FatalDiscoveryError as e:
            error_class = "fatal"
            error_reason = "api_error"
            record_discovery_failure(pattern, error_reason, error_class)
            latency_ms = (time.monotonic() - start_time) * 1000
            record_discovery_attempt(pattern, success=False)
            record_discovery_latency(pattern, latency_ms, success=False)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                error_class=error_class,
            ).error("Fatal error checking market: {error}", error=e)
            if self.bus:
                event = MarketDiscoveryEvent(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    discovered_market=None,
                    search_strategy="current_first",
                    windows_checked=windows_checked,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(e),
                    error_class=error_class,
                )
                await self.bus.publish(MARKET_DISCOVERY, event)
            return None
        if state == MarketState.ACTIVE:
            self._cache_result(pattern, current_slug)
            latency_ms = (time.monotonic() - start_time) * 1000
            record_discovery_attempt(pattern, success=True)
            record_discovery_latency(pattern, latency_ms, success=True)
            record_windows_searched(pattern, windows_checked)
            update_windows_checked_gauge(pattern, windows_checked)
            update_cache_size_gauge(len(self._cache))
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=current_slug,
                latency_ms=latency_ms,
                windows_checked=windows_checked,
                search_strategy="current_first",
            ).info("Found active market: {market} (current window)", market=current_slug)
            if self.bus:
                event = MarketDiscoveryEvent(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    discovered_market=current_slug,
                    search_strategy="current_first",
                    windows_checked=windows_checked,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                    error_class=None,
                )
                await self.bus.publish(MARKET_DISCOVERY, event)
            return current_slug

        # 3. Search forward (future markets) - Polymarket creates markets in advance
        for i in range(1, self.max_windows_ahead + 1):
            future_end = current_end + (i * market_pattern.interval_seconds)
            future_slug = market_pattern.generate_slug(future_end)
            windows_checked += 1
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=future_slug,
            ).debug(
                "Checking future window {i}: {market} (end: {end})",
                i=i,
                market=future_slug,
                end=future_end,
            )
            try:
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=future_slug,
                    future_end=future_end,
                    i=i,
                ).debug(
                    "🔍 Checking future window {i}: {market} (end={end})",
                    i=i,
                    market=future_slug,
                    end=future_end,
                )
                state = await self.get_market_state(future_slug)
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=future_slug,
                    state=state.value,
                    i=i,
                ).info(
                    "🔍 Future window {i} state: {market} = {state}",
                    i=i,
                    market=future_slug,
                    state=state.value,
                )
            except (RetryableDiscoveryError, FatalDiscoveryError):
                # Continue search on errors
                state = MarketState.NOT_FOUND
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=future_slug,
                    i=i,
                ).warning(
                    "🔍 Future window {i} error: {market}",
                    i=i,
                    market=future_slug,
                )
            if state == MarketState.ACTIVE:
                self._cache_result(pattern, future_slug)
                latency_ms = (time.monotonic() - start_time) * 1000
                record_discovery_attempt(pattern, success=True)
                record_discovery_latency(pattern, latency_ms, success=True)
                record_windows_searched(pattern, windows_checked)
                update_windows_checked_gauge(pattern, windows_checked)
                update_cache_size_gauge(len(self._cache))
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=future_slug,
                    latency_ms=latency_ms,
                    windows_checked=windows_checked,
                    search_strategy="current_first",
                ).info(
                    "Found active market: {market} ({i} windows ahead)",
                    market=future_slug,
                    i=i,
                )
                if self.bus:
                    event = MarketDiscoveryEvent(
                        correlation_id=correlation_id,
                        pattern=pattern,
                        discovered_market=future_slug,
                        search_strategy="current_first",
                        windows_checked=windows_checked,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                        error_class=None,
                    )
                    await self.bus.publish(MARKET_DISCOVERY, event)
                return future_slug

        # 4. Search backward (older past markets) - only if no future markets found
        for i in range(1, self.max_windows_behind + 1):
            past_end = current_end - (i * market_pattern.interval_seconds)
            # Skip if market window has definitely passed (more than 1 interval past)
            if past_end + market_pattern.interval_seconds < now:
                continue
            past_slug = market_pattern.generate_slug(past_end)
            windows_checked += 1
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=past_slug,
            ).debug(
                "Checking past window {i}: {market} (end: {end})",
                i=i,
                market=past_slug,
                end=past_end,
            )
            try:
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    past_end=past_end,
                    i=i,
                ).debug(
                    "🔍 Checking past window {i}: {market} (end={end})",
                    i=i,
                    market=past_slug,
                    end=past_end,
                )
                state = await self.get_market_state(past_slug)
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    state=state.value,
                    i=i,
                ).info(
                    "🔍 Past window {i} state: {market} = {state}",
                    i=i,
                    market=past_slug,
                    state=state.value,
                )
            except (RetryableDiscoveryError, FatalDiscoveryError):
                # Continue search on errors
                state = MarketState.NOT_FOUND
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    i=i,
                ).warning(
                    "🔍 Past window {i} error: {market}",
                    i=i,
                    market=past_slug,
                )
            if state == MarketState.ACTIVE:
                self._cache_result(pattern, past_slug)
                latency_ms = (time.monotonic() - start_time) * 1000
                record_discovery_attempt(pattern, success=True)
                record_discovery_latency(pattern, latency_ms, success=True)
                record_windows_searched(pattern, windows_checked)
                update_windows_checked_gauge(pattern, windows_checked)
                update_cache_size_gauge(len(self._cache))
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    latency_ms=latency_ms,
                    windows_checked=windows_checked,
                    search_strategy="current_first",
                ).info(
                    "Found active market: {market} ({i} windows behind)",
                    market=past_slug,
                    i=i,
                )
                if self.bus:
                    event = MarketDiscoveryEvent(
                        correlation_id=correlation_id,
                        pattern=pattern,
                        discovered_market=past_slug,
                        search_strategy="current_first",
                        windows_checked=windows_checked,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                        error_class=None,
                    )
                    await self.bus.publish(MARKET_DISCOVERY, event)
                return past_slug

        latency_ms = (time.monotonic() - start_time) * 1000
        error_reason = "no_market_found"
        error_class = "retryable"  # May find market on retry
        record_discovery_attempt(pattern, success=False)
        record_discovery_failure(pattern, error_reason, error_class)
        record_discovery_latency(pattern, latency_ms, success=False)
        record_windows_searched(pattern, windows_checked)
        update_windows_checked_gauge(pattern, windows_checked)
        error_msg = f"No active market found after checking {windows_checked} windows"
        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            latency_ms=latency_ms,
            windows_checked=windows_checked,
            error_class=error_class,
        ).warning(
            "No active market found for pattern: {pattern} "
            "(checked {windows} windows, {latency_ms:.1f}ms)",
            pattern=pattern,
            windows=windows_checked,
            latency_ms=latency_ms,
        )

        # Emit discovery event
        if self.bus:
            event = MarketDiscoveryEvent(
                correlation_id=correlation_id,
                pattern=pattern,
                discovered_market=None,
                search_strategy="current_first",
                windows_checked=windows_checked,
                latency_ms=latency_ms,
                success=False,
                error=error_msg,
                error_class=error_class,
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

        Per observability.mdc §3: Classifies errors as retryable or fatal.

        Validation checks (in order):
        1. Market exists (NOT_FOUND if not)
        2. Market is resolved/closed (RESOLVED)
        3. Market has expired (EXPIRED)
        4. Market window has started (EXPIRED if not started yet)
        5. Market accepts orders (NO_ORDERBOOK if not)
        6. Market is active and tradeable (ACTIVE)

        Args:
            slug: Market slug to check

        Returns:
            MarketState enum indicating the market's state

        Raises:
            RetryableDiscoveryError: For network/rate limit errors
            FatalDiscoveryError: For auth/permanent errors
        """
        try:
            # Wrap synchronous call in asyncio.to_thread
            market = await asyncio.to_thread(self.gamma.get_market_by_slug, slug)
            if market is None:
                logger.bind(slug=slug).debug("🔍 Market not found: {slug}", slug=slug)
                return MarketState.NOT_FOUND

            now = int(time.time())
            logger.bind(
                slug=slug,
                active=market.active,
                acceptingOrders=market.acceptingOrders,
                closed=market.closed,
                endDate=market.endDate,
            ).debug(
                "🔍 Market API state: {slug} | active={active} acceptingOrders={accepting} "
                "closed={closed} endDate={endDate}",
                slug=slug,
                active=market.active,
                accepting=market.acceptingOrders,
                closed=market.closed,
                endDate=market.endDate,
            )

            # 1. Check if market is resolved/closed
            if market.is_resolved():
                logger.bind(slug=slug).debug("🔍 Market resolved: {slug}", slug=slug)
                return MarketState.RESOLVED

            # 2. Check if market window has started (extract from slug)
            # For recurring markets, the slug contains the end timestamp
            # Window start = end_timestamp - interval_seconds
            window_info = MarketPattern.extract_window_from_slug(slug)
            if window_info:
                window_start, window_end = window_info
                logger.bind(
                    slug=slug,
                    window_start=window_start,
                    window_end=window_end,
                    now=now,
                    has_started=now >= window_start,
                ).info(
                    "🔍 Window check: {slug} | window={start}..{end} | now={now} | "
                    "has_started={started}",
                    slug=slug,
                    start=window_start,
                    end=window_end,
                    now=now,
                    started=now >= window_start,
                )
                # If market window hasn't started yet, mark as EXPIRED (not tradeable)
                if now < window_start:
                    logger.bind(
                        slug=slug,
                        window_start=window_start,
                        now=now,
                        seconds_until_start=window_start - now,
                    ).info(
                        "🔍 Market window not started: {slug} | starts in {seconds}s",
                        slug=slug,
                        seconds=window_start - now,
                    )
                    return MarketState.EXPIRED

            # 3. Check if market has expired
            if market.is_expired():
                logger.bind(slug=slug, endDate=market.endDate).debug(
                    "🔍 Market expired: {slug} (endDate={endDate})",
                    slug=slug,
                    endDate=market.endDate,
                )
                return MarketState.EXPIRED

            # 4. Check if market accepts orders (has orderbook)
            if not market.acceptingOrders:
                logger.bind(slug=slug).debug("🔍 Market no orderbook: {slug}", slug=slug)
                return MarketState.NO_ORDERBOOK

            # 5. Market is active and tradeable
            if market.is_tradeable():
                logger.bind(
                    slug=slug,
                    active=market.active,
                    acceptingOrders=market.acceptingOrders,
                    closed=market.closed,
                ).info(
                    "🔍 Market ACTIVE: {slug} | active={active} acceptingOrders={accepting} "
                    "closed={closed}",
                    slug=slug,
                    active=market.active,
                    accepting=market.acceptingOrders,
                    closed=market.closed,
                )
                return MarketState.ACTIVE

            # Fallback: market exists but not in expected state
            # This shouldn't happen if API is consistent, but handle gracefully
            logger.bind(
                slug=slug,
                active=market.active,
                acceptingOrders=market.acceptingOrders,
                closed=market.closed,
            ).warning(
                "🔍 Market fallback to ACTIVE: {slug} | active={active} "
                "acceptingOrders={accepting} closed={closed}",
                slug=slug,
                active=market.active,
                accepting=market.acceptingOrders,
                closed=market.closed,
            )
            return MarketState.ACTIVE
        except Exception as e:
            # Classify errors per observability.mdc §3
            error_msg = str(e)
            error_type = type(e).__name__

            # Network/connection errors are retryable
            if (
                "Connection" in error_type
                or "Timeout" in error_type
                or "network" in error_msg.lower()
            ):
                raise RetryableDiscoveryError(
                    f"Network error checking market {slug}: {error_msg}"
                ) from e

            # Rate limit errors are retryable
            if "429" in error_msg or "rate limit" in error_msg.lower():
                raise RetryableDiscoveryError(
                    f"Rate limit checking market {slug}: {error_msg}"
                ) from e

            # 404 means market doesn't exist (not an error, just not found)
            if "404" in error_msg or "not found" in error_msg.lower():
                logger.bind(market_slug=slug).debug(
                    "Market {slug} not found: {error}", slug=slug, error=e
                )
                return MarketState.NOT_FOUND

            # Auth errors are fatal
            if "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower():
                raise FatalDiscoveryError(f"Auth error checking market {slug}: {error_msg}") from e

            # Other errors: default to retryable (conservative)
            logger.bind(market_slug=slug).debug(
                "Market {slug} check error: {error}", slug=slug, error=e
            )
            raise RetryableDiscoveryError(f"Error checking market {slug}: {error_msg}") from e

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
