"""Execution throttling: Order/cancel rate limiting.

Per flows.mdc §8: Execution applies throttling (non-risk).
This is execution-level throttling, not risk checks.
"""

import time
from collections import defaultdict


class ExecutionThrottle:
    """Execution-level throttling (order/cancel rate limits).

    Per flows.mdc §8: Execution throttling is separate from risk checks.
    This enforces "how fast can we trade" not "can we trade".

    Attributes:
        _order_timestamps: Dictionary mapping client_order_id → list of timestamps
        _cancel_timestamps: Dictionary mapping client_order_id → list of timestamps
        _max_orders_per_second: Maximum orders per second
        _max_cancels_per_second: Maximum cancels per second
    """

    def __init__(
        self,
        max_orders_per_second: float = 10.0,
        max_cancels_per_second: float = 20.0,
    ) -> None:
        """Initialize execution throttle.

        Args:
            max_orders_per_second: Maximum orders per second (default 10)
            max_cancels_per_second: Maximum cancels per second (default 20)
        """
        self._order_timestamps: dict[str, list[float]] = defaultdict(list)
        self._cancel_timestamps: dict[str, list[float]] = defaultdict(list)
        self._max_orders_per_second = max_orders_per_second
        self._max_cancels_per_second = max_cancels_per_second

    def check_order_throttle(self, client_order_id: str) -> bool:
        """Check if order submission is allowed by throttle.

        Args:
            client_order_id: Idempotency key

        Returns:
            True if allowed, False if throttled
        """
        now = time.monotonic()
        timestamps = self._order_timestamps[client_order_id]

        # Remove timestamps older than 1 second
        timestamps[:] = [ts for ts in timestamps if now - ts < 1.0]

        # Check if we're at the limit
        if len(timestamps) >= self._max_orders_per_second:
            return False

        # Record this submission
        timestamps.append(now)
        return True

    def check_cancel_throttle(self, client_order_id: str) -> bool:
        """Check if cancel is allowed by throttle.

        Args:
            client_order_id: Idempotency key

        Returns:
            True if allowed, False if throttled
        """
        now = time.monotonic()
        timestamps = self._cancel_timestamps[client_order_id]

        # Remove timestamps older than 1 second
        timestamps[:] = [ts for ts in timestamps if now - ts < 1.0]

        # Check if we're at the limit
        if len(timestamps) >= self._max_cancels_per_second:
            return False

        # Record this cancel
        timestamps.append(now)
        return True

    def reset(self) -> None:
        """Reset throttle state (for testing)."""
        self._order_timestamps.clear()
        self._cancel_timestamps.clear()
