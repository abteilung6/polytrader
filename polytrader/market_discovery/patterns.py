"""Market pattern parsing and window calculation."""

import re
import time
from dataclasses import dataclass


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

    def generate_slug(self, start_timestamp: int) -> str:
        """Generate market slug for a given start timestamp.

        Per Polymarket convention: The slug suffix is the Unix timestamp of the
        **start** of the measurement window.

        Example:
            start_ts = 1768121100 (2026-01-11 09:00:00 UTC)
            → slug = "btc-updown-15m-1768121100"
            → window: 09:00:00 UTC - 09:15:00 UTC

        Args:
            start_timestamp: Unix timestamp (seconds) for the start of the market window.
                Must be a multiple of interval_seconds (e.g., 900 for 15m markets).

        Returns:
            Market slug (e.g., "btc-updown-15m-1768121100")
        """
        return f"{self.pattern_str}-{start_timestamp}"

    def get_current_window_start(self) -> int:
        """Get the start timestamp of the current market window.

        Per Polymarket convention: The slug suffix is the start timestamp.
        This method calculates the start of the currently active window.

        Calculation:
            window_start = (now // interval_seconds) * interval_seconds

        Example (15m market, now = 09:10:00 UTC):
            window_start = 09:00:00 UTC
            → slug suffix = 09:00:00 UTC timestamp
            → window: 09:00:00 UTC - 09:15:00 UTC

        Returns:
            Unix timestamp (seconds) for the start of the current window.
            Always a multiple of interval_seconds.
        """
        now = int(time.time())
        # Round down to current interval boundary
        # This finds the market that's currently active (not future)
        window_start = (now // self.interval_seconds) * self.interval_seconds

        # Debug logging
        from polytrader.logging_config import logger

        logger.bind(
            now=now,
            interval=self.interval_seconds,
            window_start=window_start,
        ).debug(
            "🔍 get_current_window_start: now={now}, interval={interval}, window_start={start}",
            now=now,
            interval=self.interval_seconds,
            start=window_start,
        )

        return window_start

    def get_next_window_start(self) -> int:
        """Get the start timestamp of the next market window.

        Per Polymarket convention: The slug suffix is the start timestamp.
        This method calculates the start of the next window (one interval ahead).

        Returns:
            Unix timestamp (seconds) for the start of the next window.
            Always a multiple of interval_seconds.
        """
        return self.get_current_window_start() + self.interval_seconds

    @staticmethod
    def extract_window_from_slug(slug: str) -> tuple[int, int] | None:
        """Extract window start and end timestamps from a market slug.

        Per Polymarket convention: The slug suffix is the start timestamp.
        Window end = start_timestamp + interval_seconds.

        Example:
            slug = "btc-updown-15m-{start_ts}"
            → start_ts = timestamp for window start (e.g., 09:00:00 UTC)
            → end_ts = start_ts + interval_seconds (e.g., 09:15:00 UTC for 15m)

        Args:
            slug: Market slug (e.g., "btc-updown-15m-1768121100")

        Returns:
            Tuple of (start_timestamp, end_timestamp) if valid, None otherwise
        """
        try:
            parts = slug.split("-")
            if len(parts) < 4:
                return None

            # Extract interval from pattern (e.g., "15m" from "btc-updown-15m")
            pattern_parts = parts[:-1]  # Everything except the timestamp
            pattern = "-".join(pattern_parts)

            # Parse pattern to get interval
            parsed = MarketPattern.parse(pattern)
            interval_seconds = parsed.interval_seconds

            # Extract start timestamp (last part)
            start_ts = int(parts[-1])

            # Calculate end timestamp
            end_ts = start_ts + interval_seconds

            return (start_ts, end_ts)
        except (ValueError, IndexError):
            return None
