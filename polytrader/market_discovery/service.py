"""Market discovery service implementation."""

import asyncio
import time
from datetime import UTC, datetime, timedelta, timezone
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
        max_windows_ahead: int = 48,  # 12 hours for 15m markets (handles early market closures)
        max_windows_behind: int = 4,  # 1 hour for 15m markets
        bus: EventBus | None = None,  # Optional event bus for observability
    ) -> None:
        """Initialize market discovery service.

        Args:
            gamma_client: Gamma API client (optional)
            max_windows_ahead: Maximum number of windows to search ahead (default: 48 = 12h for 15m)
            max_windows_behind: Maximum number of windows to search behind (default: 4 = 1h for 15m)
            bus: Event bus for emitting discovery events (optional)
        """
        if gamma_client is None:
            self.gamma = GammaClient()
        else:
            self.gamma = gamma_client
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

        # Calculate window boundaries (START convention)
        current_start = market_pattern.get_current_window_start()
        now = int(time.time())
        window_start = current_start
        current_end = window_start + market_pattern.interval_seconds
        # Log timezone and time information
        now_dt_utc = datetime.fromtimestamp(now, tz=UTC)
        now_dt_local = datetime.fromtimestamp(now)
        # ET is UTC-5 (EST) or UTC-4 (EDT) - use UTC-5 as default for logging
        et_offset = timedelta(hours=-5)
        now_dt_et = datetime.fromtimestamp(now, tz=timezone(et_offset))
        current_window_start_dt_utc = datetime.fromtimestamp(window_start, tz=UTC)
        current_window_end_dt_utc = datetime.fromtimestamp(current_end, tz=UTC)
        current_window_start_dt_et = datetime.fromtimestamp(window_start, tz=timezone(et_offset))
        current_window_end_dt_et = datetime.fromtimestamp(current_end, tz=timezone(et_offset))

        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            now=now,
            now_utc=now_dt_utc.isoformat(),
            now_local=now_dt_local.isoformat(),
            now_et=now_dt_et.isoformat(),
            current_window_start=window_start,
            current_window_end=current_end,
            current_window_start_utc=current_window_start_dt_utc.isoformat(),
            current_window_end_utc=current_window_end_dt_utc.isoformat(),
            current_window_start_et=current_window_start_dt_et.isoformat(),
            current_window_end_et=current_window_end_dt_et.isoformat(),
            interval_seconds=market_pattern.interval_seconds,
        ).info(
            "🔍 Market discovery: pattern={pattern}, now={now} "
            "({utc} UTC / {et} ET / {local} local), "
            "current_window={start_utc}..{end_utc} UTC "
            "({start_et}..{end_et} ET) (interval={interval}s)",
            pattern=pattern,
            now=now,
            utc=now_dt_utc.isoformat(),
            et=now_dt_et.isoformat(),
            local=now_dt_local.isoformat(),
            start_utc=current_window_start_dt_utc.isoformat(),
            end_utc=current_window_end_dt_utc.isoformat(),
            start_et=current_window_start_dt_et.isoformat(),
            end_et=current_window_end_dt_et.isoformat(),
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
        # Previous window starts at: current_start - interval
        prev_start = window_start - market_pattern.interval_seconds
        prev_slug = market_pattern.generate_slug(prev_start)
        windows_checked += 1
        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            market_slug=prev_slug,
            prev_start=prev_start,
        ).debug(
            "🔍 Checking previous window (most recent): {market} (start={start})",
            market=prev_slug,
            start=prev_start,
        )
        try:
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=prev_slug,
                prev_start=prev_start,
            ).debug(
                "🔍 Checking previous window: {market} (start={start})",
                market=prev_slug,
                start=prev_start,
            )
            state = await self.get_market_state(prev_slug)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=prev_slug,
                state=state.value,
            ).debug(
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

        # 2. Check current window
        current_slug = market_pattern.generate_slug(current_start)
        windows_checked += 1

        # Calculate current window times for logging
        current_window_start_dt = datetime.fromtimestamp(window_start, tz=UTC)
        current_window_end_dt = datetime.fromtimestamp(current_end, tz=UTC)
        current_window_is_active = window_start <= now < current_end

        logger.bind(
            correlation_id=correlation_id,
            pattern=pattern,
            market_slug=current_slug,
            window_start=window_start,
            window_end=current_end,
            window_start_utc=current_window_start_dt.isoformat(),
            window_end_utc=current_window_end_dt.isoformat(),
            now=now,
            now_utc=now_dt_utc.isoformat(),
            window_is_active=current_window_is_active,
        ).debug(
            "🔍 Checking current window market: {market} "
            "(window: {start_utc}..{end_utc} UTC, now: {now_utc} UTC, is_active: {is_active})",
            market=current_slug,
            start_utc=current_window_start_dt.isoformat(),
            end_utc=current_window_end_dt.isoformat(),
            now_utc=now_dt_utc.isoformat(),
            is_active=current_window_is_active,
        )
        try:
            state = await self.get_market_state(current_slug)
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=current_slug,
                state=state.value,
                window_start_utc=current_window_start_dt.isoformat(),
                window_end_utc=current_window_end_dt.isoformat(),
                now_utc=now_dt_utc.isoformat(),
            ).debug(
                "🔍 Current window state: {market} = {state} "
                "(window: {start_utc}..{end_utc} UTC, now: {now_utc} UTC)",
                market=current_slug,
                state=state.value,
                start_utc=current_window_start_dt.isoformat(),
                end_utc=current_window_end_dt.isoformat(),
                now_utc=now_dt_utc.isoformat(),
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

        # 3. Search backward with grace period (recently closed markets)
        # Check 2-3 windows back for markets that just closed but might still accept orders
        # Grace period: markets that closed within the last 2-3 minutes may still be tradeable
        grace_period_seconds = 180  # 3 minutes grace period
        max_backward_windows = 3  # Check up to 3 windows back

        for i in range(1, max_backward_windows + 1):
            past_start = window_start - (i * market_pattern.interval_seconds)
            past_slug = market_pattern.generate_slug(past_start)
            windows_checked += 1

            # Extract window info to check if market just closed
            window_info = MarketPattern.extract_window_from_slug(past_slug)
            if window_info:
                past_window_start, past_window_end = window_info
                seconds_since_close = now - past_window_end
                within_grace_period = 0 <= seconds_since_close <= grace_period_seconds

                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    i=i,
                    past_window_start=past_window_start,
                    past_window_end=past_window_end,
                    seconds_since_close=seconds_since_close,
                    within_grace_period=within_grace_period,
                ).debug(
                    "🔍 Checking backward window {i} (grace period): {market} | "
                    "closed {seconds}s ago, within_grace={grace}",
                    i=i,
                    market=past_slug,
                    seconds=seconds_since_close,
                    grace=within_grace_period,
                )

            try:
                state = await self.get_market_state(past_slug)
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    state=state.value,
                    i=i,
                    seconds_since_close=seconds_since_close if window_info else None,
                ).debug(
                    "🔍 Backward window {i} state: {market} = {state} (closed {seconds}s ago)",
                    i=i,
                    market=past_slug,
                    state=state.value,
                    seconds=seconds_since_close if window_info else "unknown",
                )

                if state == MarketState.ACTIVE:
                    # Found an active market in backward search - use it immediately
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
                        seconds_since_close=seconds_since_close if window_info else None,
                        search_strategy="backward_grace_period",
                    ).info(
                        "✅ Found active market (backward search, grace period): {market} "
                        "(closed {seconds}s ago)",
                        market=past_slug,
                        seconds=seconds_since_close if window_info else "unknown",
                    )
                    if self.bus:
                        event = MarketDiscoveryEvent(
                            correlation_id=correlation_id,
                            pattern=pattern,
                            discovered_market=past_slug,
                            search_strategy="backward_grace_period",
                            windows_checked=windows_checked,
                            latency_ms=latency_ms,
                            success=True,
                            error=None,
                            error_class=None,
                        )
                        await self.bus.publish(MARKET_DISCOVERY, event)
                    return past_slug
            except (RetryableDiscoveryError, FatalDiscoveryError):
                # Continue search on errors
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=past_slug,
                    i=i,
                ).warning(
                    "🔍 Backward window {i} error: {market}",
                    i=i,
                    market=past_slug,
                )
                pass

        # 4. Search forward (future markets) - Polymarket creates markets in advance
        # IMPORTANT: Prioritize markets whose windows have already started.
        # If no market's window has started, use the one whose window starts soonest.
        # Early exit: If we find an active market whose window is currently active,
        # return immediately.
        active_market_window_started: str | None = None  # Markets whose windows are active
        active_market_window_not_started: str | None = None  # Markets whose windows haven't started
        earliest_window_start: int | None = None  # For non-active: earliest start time
        latest_active_window_start: int | None = None  # For active: latest start (most recent)

        # Search forward, but prioritize closer windows first
        # Check first 10 windows (2.5 hours for 15m) before expanding search
        priority_search_limit = min(10, self.max_windows_ahead)

        for i in range(1, self.max_windows_ahead + 1):
            future_start = current_start + (i * market_pattern.interval_seconds)
            future_slug = market_pattern.generate_slug(future_start)
            windows_checked += 1
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=future_slug,
            ).debug(
                "Checking future window {i}: {market} (start: {start})",
                i=i,
                market=future_slug,
                start=future_start,
            )
            try:
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=future_slug,
                    future_start=future_start,
                    i=i,
                ).debug(
                    "🔍 Checking future window {i}: {market} (start={start})",
                    i=i,
                    market=future_slug,
                    start=future_start,
                )
                state = await self.get_market_state(future_slug)
                logger.bind(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    market_slug=future_slug,
                    state=state.value,
                    i=i,
                ).debug(
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
                # Check if this market's window is currently active (started and not ended)
                # PREFER actual dates from market metadata over calculated windows
                future_window_start: int | None = None
                future_window_end: int | None = None

                # Try to get actual dates from market (API includes startDate/endDate)
                try:
                    market = await asyncio.to_thread(self.gamma.get_market_by_slug, future_slug)
                    if market and market.startDate and market.endDate:
                        try:
                            start_dt_str = market.startDate.replace("Z", "+00:00")
                            end_dt_str = market.endDate.replace("Z", "+00:00")
                            start_dt = datetime.fromisoformat(start_dt_str)
                            end_dt = datetime.fromisoformat(end_dt_str)
                            if start_dt.tzinfo is None:
                                start_dt = start_dt.replace(tzinfo=UTC)
                            if end_dt.tzinfo is None:
                                end_dt = end_dt.replace(tzinfo=UTC)
                            future_window_start = int(start_dt.timestamp())
                            future_window_end = int(end_dt.timestamp())
                        except (ValueError, AttributeError):
                            pass
                except Exception:
                    pass

                # Fall back to calculated window if actual dates not available
                if future_window_start is None or future_window_end is None:
                    window_info = MarketPattern.extract_window_from_slug(future_slug)
                    if window_info:
                        future_window_start, future_window_end = window_info

                window_is_active = False
                window_start_dt_utc = None
                window_end_dt_utc = None
                seconds_until_start = None
                if future_window_start is not None and future_window_end is not None:
                    window_start_dt_utc = datetime.fromtimestamp(future_window_start, tz=UTC)
                    window_end_dt_utc = datetime.fromtimestamp(future_window_end, tz=UTC)
                    seconds_until_start = future_window_start - now
                    # Window is active if: started <= now < ended
                    window_is_active = future_window_start <= now < future_window_end

                    # Sanity check: if actual dates say window is active, but calculated window
                    # is far in the future, the actual dates might be wrong (market creation time).
                    # In this case, use calculated window to determine if it's actually active.
                    calculated_window_info = MarketPattern.extract_window_from_slug(future_slug)
                    if calculated_window_info and window_is_active:
                        calc_start, calc_end = calculated_window_info
                        hours_until_calc = (calc_start - now) / 3600.0
                        if hours_until_calc > 2:
                            # Actual dates say it's active, but calculated window is >2h away
                            # This suggests actual dates are wrong (market creation time,
                            # not window start). Use calculated window instead for activity.
                            calc_start_dt = datetime.fromtimestamp(calc_start, tz=UTC)
                            logger.bind(
                                correlation_id=correlation_id,
                                pattern=pattern,
                                market_slug=future_slug,
                                actual_start=window_start_dt_utc.isoformat(),
                                calc_start=calc_start_dt.isoformat(),
                                hours_until_calc=hours_until_calc,
                            ).debug(
                                "⚠️ Actual dates suggest active window, but calculated window "
                                "is {hours:.1f}h in future. Using calculated window instead.",
                                hours=hours_until_calc,
                            )
                            future_window_start = calc_start
                            future_window_end = calc_end
                            window_start_dt_utc = datetime.fromtimestamp(
                                future_window_start, tz=UTC
                            )
                            window_end_dt_utc = datetime.fromtimestamp(future_window_end, tz=UTC)
                            seconds_until_start = future_window_start - now
                            window_is_active = future_window_start <= now < future_window_end

                    logger.bind(
                        correlation_id=correlation_id,
                        pattern=pattern,
                        market_slug=future_slug,
                        i=i,
                        window_start=future_window_start,
                        window_end=future_window_end,
                        window_start_utc=(
                            window_start_dt_utc.isoformat() if window_start_dt_utc else None
                        ),
                        window_end_utc=(
                            window_end_dt_utc.isoformat() if window_end_dt_utc else None
                        ),
                        now=now,
                        now_utc=now_dt_utc.isoformat(),
                        window_is_active=window_is_active,
                        seconds_until_start=seconds_until_start,
                        minutes_until_start=(
                            seconds_until_start / 60 if seconds_until_start else None
                        ),
                    ).debug(
                        "🔍 Market {market} (window {i} ahead): "
                        "window={start_utc}..{end_utc} UTC, "
                        "now={now_utc} UTC, "
                        "is_active={is_active}, "
                        "starts_in={mins:.1f}min",
                        market=future_slug,
                        i=i,
                        start_utc=(
                            window_start_dt_utc.isoformat() if window_start_dt_utc else "unknown"
                        ),
                        end_utc=(window_end_dt_utc.isoformat() if window_end_dt_utc else "unknown"),
                        now_utc=now_dt_utc.isoformat(),
                        is_active=window_is_active,
                        mins=seconds_until_start / 60 if seconds_until_start else 0,
                    )

                if window_is_active:
                    # Window is currently active - use this immediately (highest priority)
                    # IMPORTANT: Prefer the market with the EARLIEST window_start that's still
                    # active. This ensures we select the current market, not a future one.
                    # (Multiple markets can have active windows if they started earlier)
                    should_use = False
                    if active_market_window_started is None:
                        should_use = True
                    elif future_window_start is not None and latest_active_window_start is not None:
                        # Prefer the market with the EARLIEST window_start (current market)
                        # This ensures we don't select a market 12 hours in the future
                        if future_window_start < latest_active_window_start:
                            should_use = True
                    elif future_window_start is not None:
                        # First active market found
                        should_use = True

                    if should_use:
                        active_market_window_started = future_slug
                        if future_window_start is not None:
                            # Track the EARLIEST active window (current market)
                            if (
                                latest_active_window_start is None
                                or future_window_start < latest_active_window_start
                            ):
                                latest_active_window_start = future_window_start
                        logger.bind(
                            correlation_id=correlation_id,
                            pattern=pattern,
                            market_slug=future_slug,
                            i=i,
                        ).info(
                            "✅ Found active market (window currently active): {market} "
                            "({i} windows ahead) - using as current market",
                            market=future_slug,
                            i=i,
                        )
                        # Early exit: If we found an active market with an active window,
                        # and it's within the first 10 windows (priority search),
                        # return immediately. This optimizes for the common case where
                        # the current market is found quickly.
                        if i <= priority_search_limit:
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
                                search_strategy="forward_early_exit",
                            ).info(
                                "Found active market (early exit): {market}",
                                market=future_slug,
                            )
                            if self.bus:
                                event = MarketDiscoveryEvent(
                                    correlation_id=correlation_id,
                                    pattern=pattern,
                                    discovered_market=future_slug,
                                    search_strategy="forward_early_exit",
                                    windows_checked=windows_checked,
                                    latency_ms=latency_ms,
                                    success=True,
                                    error=None,
                                    error_class=None,
                                )
                                await self.bus.publish(MARKET_DISCOVERY, event)
                            return future_slug
                elif (
                    future_window_start is not None
                    and future_window_end is not None
                    and now >= future_window_end
                ):
                    # Window has ended - skip this market entirely
                    # Don't consider it as a fallback
                    logger.bind(
                        correlation_id=correlation_id,
                        pattern=pattern,
                        market_slug=future_slug,
                        i=i,
                        window_end=future_window_end,
                        now=now,
                        seconds_since_end=now - future_window_end if future_window_end else 0,
                    ).debug(
                        "⏭️  Skipping market (window ended): {market} "
                        "({i} windows ahead, ended {secs:.0f}s ago)",
                        market=future_slug,
                        i=i,
                        secs=now - future_window_end if future_window_end else 0,
                    )
                else:
                    # Window hasn't started but market is active - remember as fallback
                    # Use the market whose window starts SOONEST (smallest seconds_until_start)
                    # This ensures we select the market closest to being active,
                    # not the earliest absolute time
                    if future_window_start is not None:
                        seconds_until_start = future_window_start - now
                        # Compare seconds_until_start (time until window starts)
                        # instead of absolute window_start.
                        # We want the market whose window starts soonest relative to now
                        current_best_seconds_until_start = None
                        if active_market_window_not_started and earliest_window_start:
                            current_best_seconds_until_start = earliest_window_start - now
                        is_better = (
                            active_market_window_not_started is None
                            or current_best_seconds_until_start is None
                            or seconds_until_start < current_best_seconds_until_start
                        )

                        logger.bind(
                            correlation_id=correlation_id,
                            pattern=pattern,
                            market_slug=future_slug,
                            i=i,
                            window_start=future_window_start,
                            window_start_utc=(
                                window_start_dt_utc.isoformat() if window_start_dt_utc else None
                            ),
                            seconds_until_start=seconds_until_start,
                            minutes_until_start=(
                                seconds_until_start / 60 if seconds_until_start else None
                            ),
                            current_best=active_market_window_not_started,
                            current_best_start=earliest_window_start,
                            current_best_seconds_until_start=current_best_seconds_until_start,
                            is_better=is_better,
                        ).debug(
                            "🔍 Market {market} (window {i} ahead, not active): "
                            "window starts at {start_utc} UTC ({mins:.1f}min from now), "
                            "current_best={best} ({best_mins}min from now), is_better={better}",
                            market=future_slug,
                            i=i,
                            start_utc=(
                                window_start_dt_utc.isoformat()
                                if window_start_dt_utc
                                else "unknown"
                            ),
                            mins=seconds_until_start / 60 if seconds_until_start else 0,
                            best=active_market_window_not_started or "none",
                            best_mins=(
                                f"{current_best_seconds_until_start / 60:.1f}"
                                if current_best_seconds_until_start is not None
                                else "unknown"
                            ),
                            better=is_better,
                        )

                        if is_better and future_window_start is not None:
                            active_market_window_not_started = future_slug
                            earliest_window_start = future_window_start
                            logger.bind(
                                correlation_id=correlation_id,
                                pattern=pattern,
                                market_slug=future_slug,
                                i=i,
                                window_start=window_start,
                                seconds_until_start=seconds_until_start,
                            ).debug(
                                "✅ Selected as best fallback: {market} (starts in {mins:.1f}min)",
                                market=future_slug,
                                mins=seconds_until_start / 60,
                            )

        # Prioritize markets whose windows are currently active
        if active_market_window_started:
            # Use market with active window immediately
            window_info = MarketPattern.extract_window_from_slug(active_market_window_started)
            window_start_dt_utc = None
            window_end_dt_utc = None
            if window_info:
                window_start, window_end = window_info
                window_start_dt_utc = datetime.fromtimestamp(window_start, tz=UTC)
                window_end_dt_utc = datetime.fromtimestamp(window_end, tz=UTC)

            self._cache_result(pattern, active_market_window_started)
            latency_ms = (time.monotonic() - start_time) * 1000
            record_discovery_attempt(pattern, success=True)
            record_discovery_latency(pattern, latency_ms, success=True)
            record_windows_searched(pattern, windows_checked)
            update_windows_checked_gauge(pattern, windows_checked)
            update_cache_size_gauge(len(self._cache))
            logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=active_market_window_started,
                latency_ms=latency_ms,
                windows_checked=windows_checked,
                window_start_utc=(window_start_dt_utc.isoformat() if window_start_dt_utc else None),
                window_end_utc=(window_end_dt_utc.isoformat() if window_end_dt_utc else None),
                now_utc=now_dt_utc.isoformat(),
                search_strategy="forward_active_window",
            ).info(
                "✅ Selected market (window currently active): {market} "
                "(window: {start_utc}..{end_utc} UTC, now: {now_utc} UTC)",
                market=active_market_window_started,
                start_utc=window_start_dt_utc.isoformat() if window_start_dt_utc else "unknown",
                end_utc=window_end_dt_utc.isoformat() if window_end_dt_utc else "unknown",
                now_utc=now_dt_utc.isoformat(),
            )
            if self.bus:
                event = MarketDiscoveryEvent(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    discovered_market=active_market_window_started,
                    search_strategy="forward_active_window",
                    windows_checked=windows_checked,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                    error_class=None,
                )
                await self.bus.publish(MARKET_DISCOVERY, event)
            return active_market_window_started

        # If we found an active market whose window hasn't started, use it as fallback
        if active_market_window_not_started:
            # Calculate how long until the window starts
            window_info = MarketPattern.extract_window_from_slug(active_market_window_not_started)
            seconds_until_start = None
            window_start_dt_utc = None
            if window_info:
                window_start, window_end = window_info
                window_start_dt_utc = datetime.fromtimestamp(window_start, tz=UTC)
                window_end_dt_utc = datetime.fromtimestamp(window_end, tz=UTC)
                seconds_until_start = window_start - now
                minutes_until_start = seconds_until_start / 60

            self._cache_result(pattern, active_market_window_not_started)
            latency_ms = (time.monotonic() - start_time) * 1000
            record_discovery_attempt(pattern, success=True)
            record_discovery_latency(pattern, latency_ms, success=True)
            record_windows_searched(pattern, windows_checked)
            update_windows_checked_gauge(pattern, windows_checked)
            update_cache_size_gauge(len(self._cache))

            # Log warning if window is far in the future
            log_binding = logger.bind(
                correlation_id=correlation_id,
                pattern=pattern,
                market_slug=active_market_window_not_started,
                latency_ms=latency_ms,
                windows_checked=windows_checked,
                window_start=window_info[0] if window_info else None,
                window_end=window_info[1] if window_info else None,
                window_start_utc=(window_start_dt_utc.isoformat() if window_start_dt_utc else None),
                window_end_utc=(window_end_dt_utc.isoformat() if window_end_dt_utc else None),
                now=now,
                now_utc=now_dt_utc.isoformat(),
                seconds_until_start=seconds_until_start,
                minutes_until_start=minutes_until_start if seconds_until_start else None,
                hours_until_start=((minutes_until_start / 60) if seconds_until_start else None),
                search_strategy="current_first",
            )

            if seconds_until_start and seconds_until_start > 3600:  # > 1 hour
                log_binding.warning(
                    "✅ Selected market (window starts in {mins:.1f}min / {hours:.2f}h): "
                    "{market} (window: {start_utc}..{end_utc} UTC, now: {now_utc} UTC)",
                    mins=minutes_until_start,
                    hours=minutes_until_start / 60,
                    market=active_market_window_not_started,
                    start_utc=window_start_dt_utc.isoformat() if window_start_dt_utc else "unknown",
                    end_utc=window_end_dt_utc.isoformat() if window_end_dt_utc else "unknown",
                    now_utc=now_dt_utc.isoformat(),
                )
            else:
                log_binding.info(
                    "✅ Selected market (window starts in {mins:.1f}min): {market} "
                    "(window: {start_utc}..{end_utc} UTC, now: {now_utc} UTC)",
                    mins=minutes_until_start if seconds_until_start else 0,
                    market=active_market_window_not_started,
                    start_utc=window_start_dt_utc.isoformat() if window_start_dt_utc else "unknown",
                    end_utc=window_end_dt_utc.isoformat() if window_end_dt_utc else "unknown",
                    now_utc=now_dt_utc.isoformat(),
                )
            if self.bus:
                event = MarketDiscoveryEvent(
                    correlation_id=correlation_id,
                    pattern=pattern,
                    discovered_market=active_market_window_not_started,
                    search_strategy="current_first",
                    windows_checked=windows_checked,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                    error_class=None,
                )
                await self.bus.publish(MARKET_DISCOVERY, event)
            return active_market_window_not_started

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

        next_start = market_pattern.get_next_window_start()
        next_slug = market_pattern.generate_slug(next_start)

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
            # API response includes startDate and endDate directly
            market = await asyncio.to_thread(self.gamma.get_market_by_slug, slug)
            if market is None:
                logger.bind(slug=slug).debug("🔍 Market not found: {slug}", slug=slug)
                return MarketState.NOT_FOUND

            now = int(time.time())
            now_dt = datetime.fromtimestamp(now, tz=UTC)
            logger.bind(
                slug=slug,
                active=market.active,
                acceptingOrders=market.acceptingOrders,
                closed=market.closed,
                startDate=market.startDate,
                endDate=market.endDate,
            ).debug(
                "🔍 Market API state: {slug} | active={active} acceptingOrders={accepting} "
                "closed={closed} startDate={startDate} endDate={endDate}",
                slug=slug,
                active=market.active,
                accepting=market.acceptingOrders,
                closed=market.closed,
                startDate=market.startDate,
                endDate=market.endDate,
            )

            # 1. Check if market is resolved/closed
            # IMPORTANT: Only mark as RESOLVED if market is closed AND not accepting orders.
            # Markets may be marked as "closed" by the API but still accept orders
            # for a grace period. If a market is still accepting orders,
            # it should be considered tradeable.
            if market.is_resolved() and not market.acceptingOrders:
                logger.bind(
                    slug=slug,
                    closed=market.closed,
                    acceptingOrders=market.acceptingOrders,
                ).debug(
                    "🔍 Market resolved (closed and not accepting orders): {slug} | "
                    "closed={closed} acceptingOrders={accepting}",
                    slug=slug,
                    closed=market.closed,
                    accepting=market.acceptingOrders,
                )
                return MarketState.RESOLVED
            elif market.is_resolved() and market.acceptingOrders:
                # Market is marked as closed but still accepting orders - treat as active
                # This can happen during grace periods or if API marks markets closed early
                logger.bind(
                    slug=slug,
                    closed=market.closed,
                    acceptingOrders=market.acceptingOrders,
                ).warning(
                    "🔍 Market marked as closed but still accepting orders: {slug} | "
                    "closed={closed} acceptingOrders={accepting} - treating as potentially active",
                    slug=slug,
                    closed=market.closed,
                    accepting=market.acceptingOrders,
                )
                # Continue to check other conditions (window, expiry, etc.)

            # 2. Check if market window has started
            # PREFER actual startDate/endDate from API/website over calculated windows
            # Fall back to calculated windows if actual dates not available
            window_start: int | None = None
            window_end: int | None = None
            window_source = "calculated"  # Track source for logging

            # Try to use actual dates from market metadata
            if market.startDate and market.endDate:
                try:
                    # Parse ISO 8601 datetime strings
                    start_dt_str = market.startDate.replace("Z", "+00:00")
                    end_dt_str = market.endDate.replace("Z", "+00:00")
                    start_dt = datetime.fromisoformat(start_dt_str)
                    end_dt = datetime.fromisoformat(end_dt_str)
                    # Ensure UTC timezone
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=UTC)
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=UTC)
                    window_start = int(start_dt.timestamp())
                    window_end = int(end_dt.timestamp())
                    window_source = "actual"
                except (ValueError, AttributeError):
                    # Fall back to calculated if parsing fails
                    pass

            # Fall back to calculated window from slug
            if window_start is None or window_end is None:
                window_info = MarketPattern.extract_window_from_slug(slug)
                if window_info:
                    window_start, window_end = window_info
                    window_source = "calculated"

            if window_start is not None and window_end is not None:
                logger.bind(
                    slug=slug,
                    window_start=window_start,
                    window_end=window_end,
                    window_start_utc=datetime.fromtimestamp(window_start, tz=UTC).isoformat(),
                    window_end_utc=datetime.fromtimestamp(window_end, tz=UTC).isoformat(),
                    now=now,
                    now_utc=now_dt.isoformat(),
                    has_started=now >= window_start,
                    has_ended=now >= window_end,
                    acceptingOrders=market.acceptingOrders,
                    window_source=window_source,
                ).debug(
                    "🔍 Window check ({source}): {slug} | window={start_utc}..{end_utc} UTC | "
                    "now={now_utc} UTC | has_started={started} has_ended={ended} "
                    "acceptingOrders={accepting}",
                    source=window_source,
                    slug=slug,
                    start_utc=datetime.fromtimestamp(window_start, tz=UTC).isoformat(),
                    end_utc=datetime.fromtimestamp(window_end, tz=UTC).isoformat(),
                    now_utc=now_dt.isoformat(),
                    started=now >= window_start,
                    ended=now >= window_end,
                    accepting=market.acceptingOrders,
                )
                # If market window hasn't started yet, only mark as EXPIRED if not accepting orders
                # Markets that accept orders before their window starts should be considered active
                if now < window_start:
                    if not market.acceptingOrders:
                        start_utc_str = datetime.fromtimestamp(window_start, tz=UTC).isoformat()
                        now_utc_str = now_dt.isoformat()
                        logger.bind(
                            slug=slug,
                            window_start=window_start,
                            window_start_utc=start_utc_str,
                            now=now,
                            now_utc=now_utc_str,
                            seconds_until_start=window_start - now,
                        ).info(
                            "🔍 Market window not started and not accepting orders: {slug} | "
                            "starts in {seconds}s ({start_utc} UTC, now: {now_utc} UTC)",
                            slug=slug,
                            seconds=window_start - now,
                            start_utc=start_utc_str,
                            now_utc=now_utc_str,
                        )
                        return MarketState.EXPIRED
                    else:
                        # Window hasn't started but market is accepting orders - allow it
                        start_utc_str = datetime.fromtimestamp(window_start, tz=UTC).isoformat()
                        now_utc_str = now_dt.isoformat()
                        logger.bind(
                            slug=slug,
                            window_start=window_start,
                            window_start_utc=start_utc_str,
                            now=now,
                            now_utc=now_utc_str,
                            seconds_until_start=window_start - now,
                            acceptingOrders=market.acceptingOrders,
                        ).info(
                            "🔍 Market window not started but accepting orders: {slug} | "
                            "starts in {seconds}s ({start_utc} UTC, now: {now_utc} UTC) - "
                            "treating as active",
                            slug=slug,
                            seconds=window_start - now,
                            start_utc=start_utc_str,
                            now_utc=now_utc_str,
                        )
                        # Continue to check other conditions (expiry, etc.) but allow this market
                elif now >= window_end:
                    # Window has ended - mark as expired/resolved if not accepting orders
                    if not market.acceptingOrders:
                        logger.bind(
                            slug=slug,
                            window_end=window_end,
                            window_end_utc=datetime.fromtimestamp(window_end, tz=UTC).isoformat(),
                            now=now,
                            now_utc=now_dt.isoformat(),
                            seconds_since_end=now - window_end,
                        ).info(
                            "🔍 Market window ended and not accepting orders: {slug} | "
                            "ended {seconds}s ago ({end_utc} UTC, now: {now_utc} UTC)",
                            slug=slug,
                            seconds=now - window_end,
                            end_utc=datetime.fromtimestamp(window_end, tz=UTC).isoformat(),
                            now_utc=now_dt.isoformat(),
                        )
                        return MarketState.EXPIRED
                    else:
                        # Window ended but market still accepting orders (grace period)
                        logger.bind(
                            slug=slug,
                            window_end=window_end,
                            window_end_utc=datetime.fromtimestamp(window_end, tz=UTC).isoformat(),
                            now=now,
                            now_utc=now_dt.isoformat(),
                            seconds_since_end=now - window_end,
                            acceptingOrders=market.acceptingOrders,
                        ).info(
                            "🔍 Market window ended but still accepting orders: {slug} | "
                            "ended {seconds}s ago ({end_utc} UTC, now: {now_utc} UTC) - "
                            "treating as active (grace period)",
                            slug=slug,
                            seconds=now - window_end,
                            end_utc=datetime.fromtimestamp(window_end, tz=UTC).isoformat(),
                            now_utc=now_dt.isoformat(),
                        )
                        # Continue to check other conditions but allow this market

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
            # If market is accepting orders, consider it active (regardless of closed flag,
            # since we already handled closed+not-accepting-orders case earlier)
            if market.acceptingOrders:
                logger.bind(
                    slug=slug,
                    active=market.active,
                    acceptingOrders=market.acceptingOrders,
                    closed=market.closed,
                ).debug(
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
                current_start = market_pattern.get_current_window_start()
                prev_start = current_start - market_pattern.interval_seconds

                # Cached market should be either current or previous window
                if cached_timestamp not in (current_start, prev_start):
                    # Cached market is from wrong window, invalidate cache
                    logger.debug(
                        "Invalidating cache: cached market {cached} not in current window "
                        "(current: {current}, prev: {prev})",
                        cached=slug,
                        current=f"{pattern}-{current_start}",
                        prev=f"{pattern}-{prev_start}",
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
