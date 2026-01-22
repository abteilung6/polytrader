"""Buffered writer for high-performance market tick ingestion.

Per proposal: Buffers ticks in memory and flushes to database when:
- Buffer reaches batch_size (default: 1000)
- Time since last flush >= flush_interval (default: 1.0s)

This reduces transaction overhead from O(n) to O(n/1000).
"""

import asyncio
import time
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from polytrader.events.types import MarketDataEvent
from polytrader.logging_config import logger
from polytrader.obs.metrics import (
    increment_tick_flush_errors,
    record_tick_flush,
    record_tick_write_latency_ms,
    set_tick_buffer_capacity,
    set_tick_buffer_size,
)

if TYPE_CHECKING:
    from polytrader.db.repository import IMarketTickRepository


class BufferedTickWriter:
    """Buffered writer for high-performance market tick ingestion.

    Batches ticks in memory and flushes to database when:
    - Buffer reaches batch_size (default: 1000)
    - Time since last flush >= flush_interval (default: 1.0s)

    Per proposal: Reduces transaction overhead from O(n) to O(n/1000).

    Example:
        >>> from polytrader.db.repository import MarketTickRepository
        >>> async with Session() as session:
        ...     repo = MarketTickRepository(session)
        ...     writer = BufferedTickWriter(repo, batch_size=100, flush_interval=0.5)
        ...     await writer.add(market_data_event)
        ...     await writer.flush()  # Force flush
        ...     await writer.close()  # Flush and close
    """

    def __init__(
        self,
        repository: "IMarketTickRepository",
        batch_size: int = 1000,
        flush_interval: float = 1.0,
    ) -> None:
        """Initialize buffered writer.

        Args:
            repository: MarketTickRepository instance for database operations
            batch_size: Flush when buffer reaches this size (default: 1000)
            flush_interval: Flush after this many seconds (default: 1.0s)
        """
        self._repository = repository
        self._batch_size = batch_size
        self._flush_interval = flush_interval

        self._buffer: list[MarketDataEvent] = []
        self._last_flush_time = time.monotonic()
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False

        # Set buffer capacity metric
        set_tick_buffer_capacity(batch_size)

    async def add(self, event: MarketDataEvent) -> None:
        """Add tick to buffer. Auto-flushes if threshold reached.

        Args:
            event: MarketDataEvent to add to buffer

        Note:
            This method is non-blocking (doesn't wait for flush to complete).
            Flushes happen asynchronously in background.
        """
        if self._closed:
            logger.warning("BufferedTickWriter is closed, ignoring add() call")
            return

        # Measure write latency (time to buffer)
        start_time = time.perf_counter()
        self._buffer.append(event)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Record metrics (non-blocking)
        try:
            record_tick_write_latency_ms(latency_ms)
            set_tick_buffer_size(len(self._buffer))
        except Exception:
            # Don't let metrics errors break the critical path
            pass

        # Check if we should flush based on size
        if len(self._buffer) >= self._batch_size:
            await self.flush()

        # Start flush task if not already running
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush())

    async def flush(self) -> None:
        """Force flush buffer to database.

        Converts MarketDataEvent objects to database format and bulk inserts.
        Errors are logged but don't raise exceptions (non-blocking behavior).
        """
        if not self._buffer:
            return

        # Measure flush latency
        start_time = time.perf_counter()

        # Copy buffer and clear immediately (non-blocking)
        ticks_to_flush = self._buffer.copy()
        self._buffer.clear()
        self._last_flush_time = time.monotonic()

        # Update buffer size metric
        try:
            set_tick_buffer_size(len(self._buffer))
        except Exception:
            pass

        # Convert MarketDataEvent → database format
        try:
            db_ticks = [_convert_event_to_db_format(event) for event in ticks_to_flush]
            count = await self._repository.bulk_create_ticks(db_ticks)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Record successful flush metrics
            try:
                record_tick_flush(count=count, latency_ms=latency_ms)
            except Exception:
                pass

            logger.debug(
                "Flushed {count} ticks to database (buffer_size={buffer_size})",
                count=count,
                buffer_size=len(ticks_to_flush),
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            error_class = _classify_db_error(e)

            # Record error metrics
            try:
                increment_tick_flush_errors(error_class)
            except Exception:
                pass

            logger.exception(
                "Error flushing ticks to database: {error}",
                error=str(e),
                error_type=type(e).__name__,
                tick_count=len(ticks_to_flush),
            )
            # Don't raise - non-blocking behavior

    async def close(self) -> None:
        """Flush remaining ticks and close writer.

        This should be called before shutdown to ensure all ticks are persisted.
        """
        if self._closed:
            return

        self._closed = True

        # Cancel flush task if running
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining ticks
        await self.flush()

        logger.debug("BufferedTickWriter closed")

    async def _periodic_flush(self) -> None:
        """Periodic flush task (runs in background).

        Flushes buffer if flush_interval has elapsed since last flush.
        """
        try:
            while not self._closed:
                await asyncio.sleep(self._flush_interval)

                # Check if we should flush (time threshold)
                elapsed = time.monotonic() - self._last_flush_time
                if elapsed >= self._flush_interval and self._buffer:
                    await self.flush()
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            return
        except Exception as e:
            logger.exception(
                "Error in periodic flush task: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )


def _classify_db_error(error: Exception) -> str:
    """Classify database error as retryable or fatal.

    Per observability.mdc §3: Errors must be classified.

    Args:
        error: Exception to classify

    Returns:
        Error classification ("retryable", "fatal", or "unknown")
    """
    error_type = type(error).__name__
    error_msg = str(error).lower()

    # Network/connection errors are retryable
    if (
        "Connection" in error_type
        or "Timeout" in error_type
        or "network" in error_msg
        or "connection" in error_msg
        or "timeout" in error_msg
    ):
        return "retryable"

    # SQLAlchemy operational errors (connection issues) are retryable
    if "OperationalError" in error_type or "InterfaceError" in error_type:
        return "retryable"

    # Constraint violations are fatal (data issue, won't succeed on retry)
    if "IntegrityError" in error_type or "constraint" in error_msg:
        return "fatal"

    # Programming errors (SQL syntax) are fatal
    if "ProgrammingError" in error_type:
        return "fatal"

    # Default to unknown for unclassified errors
    return "unknown"


def _convert_event_to_db_format(event: MarketDataEvent) -> dict[str, Any]:
    """Convert MarketDataEvent to database row format.

    Args:
        event: MarketDataEvent to convert

    Returns:
        Dictionary with database column names and values

    Note:
        - Converts float prices to Decimal for NUMERIC columns
        - Computes mid, spread, spread_bps from best_bid/best_ask
        - Parses ISO timestamp string to datetime
    """
    # Parse ISO timestamp string to datetime
    ts_wall = datetime.fromisoformat(event.ts_wall.replace("Z", "+00:00"))

    # Convert float prices to Decimal (for NUMERIC columns)
    best_bid = Decimal(str(event.best_bid))
    best_ask = Decimal(str(event.best_ask))

    # Compute mid, spread, spread_bps (stored for query efficiency)
    mid = (best_bid + best_ask) / Decimal("2")
    spread = best_ask - best_bid
    spread_bps = spread * Decimal("10000")

    return {
        "tick_id": UUID(event.event_id),
        "ts_wall": ts_wall,
        "ts_mono": event.ts_mono,
        "market_slug": event.market_slug,
        "outcome": event.outcome,  # Outcome is already a string (Literal["UP", "DOWN"])
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread": spread,
        "spread_bps": spread_bps,
        "event_id": UUID(event.event_id),  # Reference to events table
        "run_id": event.run_id,
    }
