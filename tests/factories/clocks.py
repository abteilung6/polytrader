"""Factories for creating Clock objects in tests.

Per unit_testing_techinical.mdc §2: All time MUST be injected via Clock interface.

Note: Clock is a Protocol defined in polytrader.risk.policies with only monotonic() method.
"""

from unittest.mock import MagicMock

from polytrader.risk.policies import Clock


class FixedClock:
    """Deterministic clock for testing.

    Implements Clock protocol (monotonic() method only).
    """

    def __init__(self, base_monotonic: float = 1000.0) -> None:
        """Initialize with fixed monotonic time.

        Args:
            base_monotonic: Base monotonic time value
        """
        self._base_monotonic = base_monotonic
        self._monotonic_offset = 0.0

    def monotonic(self) -> float:
        """Get monotonic time (deterministic for testing)."""
        return self._base_monotonic + self._monotonic_offset

    def advance(self, seconds: float) -> None:
        """Advance time for testing.

        Args:
            seconds: Number of seconds to advance
        """
        self._monotonic_offset += seconds


def create_mock_clock(
    base_monotonic: float = 1000.0,
) -> MagicMock:
    """Create mock clock for testing.

    Args:
        base_monotonic: Base monotonic time value

    Returns:
        MagicMock implementing Clock protocol
    """
    clock = MagicMock(spec=Clock)
    clock.monotonic.return_value = base_monotonic
    return clock


def create_fixed_clock(
    base_monotonic: float = 1000.0,
) -> FixedClock:
    """Create FixedClock for deterministic testing.

    Args:
        base_monotonic: Base monotonic time value

    Returns:
        FixedClock instance
    """
    return FixedClock(base_monotonic=base_monotonic)
