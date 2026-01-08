"""Market discovery service for finding active recurring markets."""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

from polytrader.gamma import GammaClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketPattern:
    """Parsed market pattern.

    Attributes:
        underlying: Market underlying (e.g., "btc")
        template: Market template type (e.g., "updown")
        interval_seconds: Interval duration in seconds (e.g., 900 for 15m)
        pattern_str: Original pattern string
    """

    underlying: str
    template: str
    interval_seconds: int
    pattern_str: str

    @classmethod
    def parse(cls, pattern: str) -> "MarketPattern":
        """Parse a market pattern string.

        Examples:
            "btc-updown-15m" -> MarketPattern(
                underlying="btc", template="updown", interval_seconds=900
            )
            "eth-updown-1h" -> MarketPattern(
                underlying="eth", template="updown", interval_seconds=3600
            )

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")

        Returns:
            Parsed MarketPattern

        Raises:
            ValueError: If pattern format is invalid
        """
        # Pattern: {underlying}-{template}-{interval}
        # Interval can be: 15m, 30m, 1h, 4h, 1d, etc.
        pattern_lower = pattern.lower()

        # First check if pattern matches general format (with any unit character)
        general_match = re.match(r"^([a-z0-9]+)-([a-z0-9]+)-(\d+)([a-z])$", pattern_lower)
        if not general_match:
            raise ValueError(
                f"Invalid market pattern: {pattern}. "
                "Expected format: <underlying>-<template>-<interval><unit> "
                "(e.g., btc-updown-15m)"
            )

        underlying, template, interval_str, unit = general_match.groups()

        # Check if unit is valid
        unit_multipliers = {"m": 60, "h": 3600, "d": 86400}
        if unit not in unit_multipliers:
            raise ValueError(f"Invalid interval unit: {unit}. Must be m, h, or d")

        interval = int(interval_str)

        interval_seconds = interval * unit_multipliers[unit]

        return cls(
            underlying=underlying,
            template=template,
            interval_seconds=interval_seconds,
            pattern_str=pattern,
        )

    def generate_slug(self, end_timestamp: int) -> str:
        """Generate market slug for a given end timestamp.

        Args:
            end_timestamp: Unix timestamp (seconds) for the end of the market window

        Returns:
            Market slug (e.g., "btc-updown-15m-1767886200")
        """
        return f"{self.pattern_str}-{end_timestamp}"

    def get_current_window_end(self) -> int:
        """Get the end timestamp of the current market window.

        Returns:
            Unix timestamp (seconds) for the end of the current window
        """
        now = int(time.time())
        # Round up to the next interval boundary
        window_end = ((now // self.interval_seconds) + 1) * self.interval_seconds
        return window_end

    def get_next_window_end(self) -> int:
        """Get the end timestamp of the next market window.

        Returns:
            Unix timestamp (seconds) for the end of the next window
        """
        return self.get_current_window_end() + self.interval_seconds


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

    def __init__(self, gamma_client: GammaClient | None = None) -> None:
        self.gamma = gamma_client or GammaClient()
        self._cache: dict[str, tuple[str, float]] = {}  # pattern -> (slug, expiry_time)
        self._cache_ttl = 60.0  # Cache for 60 seconds

    async def get_current_market(self, pattern: str) -> str | None:
        """Get the current active market slug for a pattern.

        Tries multiple candidate slugs in case of market creation delays.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")

        Returns:
            Market slug if found, None if no active market exists
        """
        # Check cache first
        cached = self._get_from_cache(pattern)
        if cached:
            return cached

        try:
            market_pattern = MarketPattern.parse(pattern)
        except ValueError as e:
            logger.error(f"Invalid market pattern: {e}")
            return None

        # Try current window
        current_end = market_pattern.get_current_window_end()
        current_slug = market_pattern.generate_slug(current_end)

        if await self._market_exists(current_slug):
            self._cache_result(pattern, current_slug)
            return current_slug

        # Try previous window (in case we're at the boundary)
        prev_end = current_end - market_pattern.interval_seconds
        prev_slug = market_pattern.generate_slug(prev_end)

        if await self._market_exists(prev_slug):
            self._cache_result(pattern, prev_slug)
            return prev_slug

        # Try next window (in case market not yet created)
        next_end = current_end + market_pattern.interval_seconds
        next_slug = market_pattern.generate_slug(next_end)

        if await self._market_exists(next_slug):
            self._cache_result(pattern, next_slug)
            return next_slug

        logger.warning(f"No active market found for pattern: {pattern}")
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
            logger.error(f"Invalid market pattern: {e}")
            return None

        next_end = market_pattern.get_next_window_end()
        next_slug = market_pattern.generate_slug(next_end)

        # Validate that market exists (or will exist soon)
        if await self._market_exists(next_slug):
            return next_slug

        return None

    async def _market_exists(self, slug: str) -> bool:
        """Check if a market exists and is active.

        Args:
            slug: Market slug to check

        Returns:
            True if market exists, False otherwise
        """
        try:
            # Wrap synchronous call in asyncio.to_thread
            market = await asyncio.to_thread(self.gamma.get_market_by_slug, slug)
            # If we can get the market, it exists
            return market is not None
        except Exception as e:
            # 404 or other error means market doesn't exist
            logger.debug(f"Market {slug} not found: {e}")
            return False

    def _get_from_cache(self, pattern: str) -> str | None:
        """Get cached result if still valid.

        Args:
            pattern: Market pattern

        Returns:
            Cached slug if valid, None otherwise
        """
        if pattern not in self._cache:
            return None

        slug, expiry = self._cache[pattern]
        if time.time() < expiry:
            return slug

        # Cache expired
        del self._cache[pattern]
        return None

    def _cache_result(self, pattern: str, slug: str) -> None:
        """Cache a discovery result.

        Args:
            pattern: Market pattern
            slug: Market slug
        """
        expiry = time.time() + self._cache_ttl
        self._cache[pattern] = (slug, expiry)
