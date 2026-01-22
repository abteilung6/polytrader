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

        self._buffer.append(event)

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

        # Copy buffer and clear immediately (non-blocking)
        ticks_to_flush = self._buffer.copy()
        self._buffer.clear()
        self._last_flush_time = time.monotonic()

        # Convert MarketDataEvent → database format
        try:
            db_ticks = [_convert_event_to_db_format(event) for event in ticks_to_flush]
            count = await self._repository.bulk_create_ticks(db_ticks)
            logger.debug(
                "Flushed {count} ticks to database (buffer_size={buffer_size})",
                count=count,
                buffer_size=len(ticks_to_flush),
            )
        except Exception as e:
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
