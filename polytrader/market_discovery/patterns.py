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

    def generate_slug(self, end_timestamp: int) -> str:
        """Generate market slug for a given end timestamp.

        Per Polymarket convention: The slug suffix is the Unix timestamp of the
        **end** of the measurement window, not the start.

        Example:
            end_ts = 1768122000 (2026-01-11 09:15:00 UTC)
            → slug = "btc-updown-15m-1768122000"
            → window: 09:00:00 UTC - 09:15:00 UTC

        Args:
            end_timestamp: Unix timestamp (seconds) for the end of the market window.
                Must be a multiple of interval_seconds (e.g., 900 for 15m markets).

        Returns:
            Market slug (e.g., "btc-updown-15m-1768122000")
        """
        return f"{self.pattern_str}-{end_timestamp}"

    def get_current_window_end(self) -> int:
        """Get the end timestamp of the current market window.

        Per Polymarket convention: The slug suffix is the end timestamp.
        This method calculates the end of the currently active window.

        Calculation:
            window_start = (now // interval_seconds) * interval_seconds
            window_end = window_start + interval_seconds

        Example (15m market, now = 09:10:00 UTC):
            window_start = 09:00:00 UTC
            window_end = 09:15:00 UTC
            → slug suffix = 09:15:00 UTC timestamp

        Returns:
            Unix timestamp (seconds) for the end of the current window.
            Always a multiple of interval_seconds.
        """
        now = int(time.time())
        # Round down to current interval boundary, then add interval to get end
        # This finds the market that's currently active (not future)
        window_start = (now // self.interval_seconds) * self.interval_seconds
        window_end = window_start + self.interval_seconds
        return window_end

    def get_next_window_end(self) -> int:
        """Get the end timestamp of the next market window.

        Per Polymarket convention: The slug suffix is the end timestamp.
        This method calculates the end of the next window (one interval ahead).

        Returns:
            Unix timestamp (seconds) for the end of the next window.
            Always a multiple of interval_seconds.
        """
        return self.get_current_window_end() + self.interval_seconds

    @staticmethod
    def extract_window_from_slug(slug: str) -> tuple[int, int] | None:
        """Extract window start and end timestamps from a market slug.

        Per Polymarket convention: The slug suffix is the end timestamp.
        Window start = end_timestamp - interval_seconds.

        Example:
            slug = "btc-updown-15m-{end_ts}"
            → end_ts = timestamp for window end (e.g., 09:15:00 UTC)
            → start_ts = end_ts - interval_seconds (e.g., 09:00:00 UTC for 15m)

        Args:
            slug: Market slug (e.g., "btc-updown-15m-1768122000")

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

            # Extract end timestamp (last part)
            end_ts = int(parts[-1])

            # Calculate start timestamp
            start_ts = end_ts - interval_seconds

            return (start_ts, end_ts)
        except (ValueError, IndexError):
            return None
