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
        # Round down to current interval boundary, then add interval to get end
        # This finds the market that's currently active (not future)
        window_start = (now // self.interval_seconds) * self.interval_seconds
        window_end = window_start + self.interval_seconds
        return window_end

    def get_next_window_end(self) -> int:
        """Get the end timestamp of the next market window.

        Returns:
            Unix timestamp (seconds) for the end of the next window
        """
        return self.get_current_window_end() + self.interval_seconds
