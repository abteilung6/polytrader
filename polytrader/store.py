import asyncio
import concurrent.futures
import threading
from collections import deque
from typing import TYPE_CHECKING, Protocol

from polytrader.events.types import MarketDataEvent
from polytrader.types import Outcome

if TYPE_CHECKING:
    from polytrader.db.models import MarketTickRecord
    from polytrader.db.repository import MarketTickRepository


class IMarketDataStore(Protocol):
    """Protocol for market data store implementations."""

    def add(self, event: MarketDataEvent) -> None:
        """Add a market data event to the store."""
        ...

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get the latest market data event for a market/outcome."""
        ...

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history of market data events for a market/outcome."""
        ...

    def get_all_markets(self) -> list[tuple[str, Outcome]]:
        """Get all market/outcome pairs that have data in the store.

        Returns:
            List of (market_slug, outcome) tuples
        """
        ...


class MemoryMarketDataStore(IMarketDataStore):
    """In-memory store for market data events.

    Stores MarketDataEvent instances keyed by market_slug and outcome.
    Provides efficient access to latest market data for portfolio construction.
    """

    def __init__(self, window: int = 3000) -> None:
        """Initialize the market data store.

        Args:
            window: Maximum number of events to keep per market/outcome
        """
        self.window = window
        self._events: dict[tuple[str, Outcome], deque[MarketDataEvent]] = {}

    def add(self, event: MarketDataEvent) -> None:
        """Add a market data event to the store.

        Args:
            event: Market data event to store
        """
        key = (event.market_slug, event.outcome)
        self._events.setdefault(key, deque(maxlen=self.window)).append(event)

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get the latest market data event for a market/outcome.

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            Latest market data event, or None if no events exist
        """
        key = (market_slug, outcome)
        d = self._events.get(key)
        return d[-1] if d else None

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history of market data events for a market/outcome.

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            List of market data events (oldest first)
        """
        key = (market_slug, outcome)
        return list(self._events.get(key, []))

    def get_all_markets(self) -> list[tuple[str, Outcome]]:
        """Get all market/outcome pairs that have data in the store.

        Returns:
            List of (market_slug, outcome) tuples
        """
        return list(self._events.keys())


class CompositeMarketDataStore(IMarketDataStore):
    """Composite store that writes to multiple stores and reads from the primary store.

    Per architecture: Enables dual-write pattern (memory + PostgreSQL) for validation
    and gradual migration. Writes go to all stores, reads come from primary (fast path).

    Example:
        >>> memory_store = MemoryMarketDataStore()
        >>> postgres_store = PostgreSQLMarketTickStore(...)
        >>> composite = CompositeMarketDataStore(memory_store, postgres_store)
        >>> composite.add(event)  # Writes to both
        >>> latest = composite.latest("market", "UP")  # Reads from memory (fast)
    """

    def __init__(self, primary: IMarketDataStore, *secondary: IMarketDataStore) -> None:
        """Initialize composite store.

        Args:
            primary: Primary store (used for reads, must be fast)
            secondary: Additional stores (used for writes only)
        """
        self._primary = primary
        self._secondary = list(secondary)

    def add(self, event: MarketDataEvent) -> None:
        """Add event to all stores (primary + secondary).

        Args:
            event: Market data event to add
        """
        # Write to primary (fast, in-memory)
        self._primary.add(event)

        # Write to secondary stores (persistence)
        for store in self._secondary:
            try:
                store.add(event)
            except Exception:
                # Log but don't fail - persistence failures shouldn't block trading
                from polytrader.logging_config import logger

                logger.exception(
                    "Error writing to secondary store: {store_type}",
                    store_type=type(store).__name__,
                )

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get latest tick from primary store (fast path).

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            Latest MarketDataEvent from primary store, or None
        """
        return self._primary.latest(market_slug, outcome)

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history from primary store (fast path).

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            List of MarketDataEvent from primary store
        """
        return self._primary.history(market_slug, outcome)

    def get_all_markets(self) -> list[tuple[str, Outcome]]:
        """Get all markets from primary store (fast path).

        Returns:
            List of (market_slug, outcome) tuples from primary store
        """
        return self._primary.get_all_markets()

    async def flush(self) -> None:
        """Flush all stores that support flushing.

        This should be called before shutdown to ensure all data is persisted.
        """
        # Flush primary if it supports flushing
        if hasattr(self._primary, "flush"):
            await self._primary.flush()

        # Flush secondary stores
        for store in self._secondary:
            if hasattr(store, "flush"):
                try:
                    await store.flush()
                except Exception:
                    from polytrader.logging_config import logger

                    logger.exception(
                        "Error flushing secondary store: {store_type}",
                        store_type=type(store).__name__,
                    )

    async def close(self) -> None:
        """Close all stores that support closing.

        This should be called before shutdown to ensure all data is persisted.
        """
        # Close primary if it supports closing
        if hasattr(self._primary, "close"):
            await self._primary.close()

        # Close secondary stores
        for store in self._secondary:
            if hasattr(store, "close"):
                try:
                    await store.close()
                except Exception:
                    from polytrader.logging_config import logger

                    logger.exception(
                        "Error closing secondary store: {store_type}",
                        store_type=type(store).__name__,
                    )


class PostgreSQLMarketTickStore(IMarketDataStore):
    """PostgreSQL-backed market data store.

    Implements IMarketDataStore protocol:
    - add(): Sync, non-blocking (schedules async write via BufferedTickWriter)
    - latest(): Sync, queries database (uses thread pool for async bridge)
    - history(): Sync, queries database (uses thread pool for async bridge)
    - get_all_markets(): Sync, queries database (uses thread pool for async bridge)

    Per architecture: Separates write path (async, buffered) from read path (sync, direct query).
    Write path uses BufferedTickWriter for high-performance bulk inserts.
    Read path bridges async database queries to sync interface using thread pool executor.

    Example:
        >>> from polytrader.db.repository import MarketTickRepository
        >>> async with Session() as session:
        ...     repo = MarketTickRepository(session)
        ...     store = PostgreSQLMarketTickStore(repo, batch_size=100, flush_interval=0.5)
        ...     store.add(market_data_event)  # Non-blocking
        ...     latest = store.latest("btc-updown-15m", "UP")  # Sync query
        ...     await store.close()  # Flush and close
    """

    def __init__(
        self,
        repository: "MarketTickRepository",
        batch_size: int = 1000,
        flush_interval: float = 1.0,
    ) -> None:
        """Initialize PostgreSQL store.

        Args:
            repository: MarketTickRepository instance for database operations
            batch_size: Buffer size for bulk inserts (default: 1000)
            flush_interval: Flush interval in seconds (default: 1.0)
        """
        from polytrader.db.tick_writer import BufferedTickWriter

        self._repository = repository
        self._writer = BufferedTickWriter(
            repository=repository,
            batch_size=batch_size,
            flush_interval=flush_interval,
        )
        self._closed = False
        self._background_loop: asyncio.AbstractEventLoop | None = None
        self._background_thread: threading.Thread | None = None
        # Engine is set by factory after creation (for cleanup)
        # Import at runtime since it's used in __init__
        from sqlalchemy.ext.asyncio import AsyncEngine

        self._engine: AsyncEngine | None = None

    def add(self, event: MarketDataEvent) -> None:
        """Add market data event (non-blocking, buffered).

        Args:
            event: MarketDataEvent to add to store

        Note:
            This method is sync (per IMarketDataStore protocol) but schedules
            async work non-blocking. If called from async context, uses asyncio.create_task.
            If called from sync context, uses a background thread with persistent event loop.
        """
        if self._closed:
            return

        # Schedule async write (non-blocking)
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()
            # In async context: schedule task
            asyncio.create_task(self._writer.add(event))
        except RuntimeError:
            # No running loop: use background thread with persistent event loop
            if self._background_loop is None or self._background_loop.is_closed():
                # Create background thread with persistent event loop
                loop_ready = threading.Event()

                def run_background_loop() -> None:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    self._background_loop = loop
                    loop_ready.set()
                    loop.run_forever()

                self._background_thread = threading.Thread(target=run_background_loop, daemon=True)
                self._background_thread.start()
                # Wait for loop to be created
                loop_ready.wait(timeout=1.0)

            # Schedule coroutine in background loop
            if self._background_loop is not None and not self._background_loop.is_closed():
                asyncio.run_coroutine_threadsafe(self._writer.add(event), self._background_loop)

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get latest tick (sync, queries database).

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            Latest MarketDataEvent, or None if no ticks exist
        """

        async def _fetch_latest() -> MarketDataEvent | None:
            record = await self._repository.get_latest(market_slug, outcome)
            if record is None:
                return None
            return _convert_record_to_event(record)

        # Bridge async query to sync interface
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()

            # If in async context, run in thread with new event loop
            def run_in_thread() -> MarketDataEvent | None:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(_fetch_latest())
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(_fetch_latest())

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history (sync, queries database).

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            List of MarketDataEvent objects (oldest first)
        """

        async def _fetch_history() -> list[MarketDataEvent]:
            records = await self._repository.get_history(
                market_slug=market_slug,
                outcome=outcome,
            )
            return [_convert_record_to_event(record) for record in records]

        # Bridge async query to sync interface
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()

            # If in async context, run in thread with new event loop
            def run_in_thread() -> list[MarketDataEvent]:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(_fetch_history())
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(_fetch_history())

    def get_all_markets(self) -> list[tuple[str, Outcome]]:
        """Get all market/outcome pairs that have data in the store.

        Returns:
            List of (market_slug, outcome) tuples
        """

        async def _fetch_markets() -> list[tuple[str, Outcome]]:
            from typing import cast

            pairs = await self._repository.get_markets()
            # Convert outcome string to Outcome type
            # Repository returns tuple[str, str], but outcome is always "UP" or "DOWN"
            return [(market, cast(Outcome, outcome)) for market, outcome in pairs]

        # Bridge async query to sync interface
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()

            # If in async context, run in thread with new event loop
            def run_in_thread() -> list[tuple[str, Outcome]]:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(_fetch_markets())
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(_fetch_markets())

    async def flush(self) -> None:
        """Flush buffer (call before shutdown).

        This ensures all buffered ticks are written to database.
        """
        await self._writer.flush()

    async def close(self) -> None:
        """Close writer and flush remaining ticks.

        This should be called before shutdown to ensure all ticks are persisted.
        """
        if self._closed:
            return
        self._closed = True

        # Close writer (this will cancel the periodic flush task)
        # If we're in the background loop, close directly
        # Otherwise, schedule close in the background loop
        if self._background_loop is not None and not self._background_loop.is_closed():
            try:
                # Check if we're in the background loop
                if asyncio.get_running_loop() is self._background_loop:
                    # We're in the background loop, close directly
                    await self._writer.close()
                else:
                    # We're in a different loop, schedule close in background loop
                    future = asyncio.run_coroutine_threadsafe(
                        self._writer.close(), self._background_loop
                    )
                    # Wait for close to complete (with timeout)
                    try:
                        future.result(timeout=2.0)
                    except Exception:
                        # If close fails, log but continue
                        from polytrader.logging_config import logger

                        logger.exception("Error closing writer in background loop")
            except RuntimeError:
                # No running loop, schedule in background loop
                future = asyncio.run_coroutine_threadsafe(
                    self._writer.close(), self._background_loop
                )
                try:
                    future.result(timeout=2.0)
                except Exception:
                    from polytrader.logging_config import logger

                    logger.exception("Error closing writer in background loop")
        else:
            # No background loop, close directly
            await self._writer.close()

        # Stop background thread if it exists
        if self._background_loop is not None and not self._background_loop.is_closed():
            self._background_loop.call_soon_threadsafe(self._background_loop.stop)
            if self._background_thread is not None:
                self._background_thread.join(timeout=1.0)

        # Dispose of database engine if it exists
        if self._engine is not None:
            await self._engine.dispose()


def _convert_record_to_event(record: "MarketTickRecord") -> MarketDataEvent:  # noqa: F821
    """Convert MarketTickRecord to MarketDataEvent.

    Args:
        record: MarketTickRecord from database

    Returns:
        MarketDataEvent object

    Note:
        - Converts Decimal prices to float
        - Converts datetime to ISO string
        - Uses record.event_id as event_id (or tick_id if event_id is None)
    """
    from polytrader.events.types import EventSource

    # Convert Decimal to float for MarketDataEvent
    best_bid = float(record.best_bid)
    best_ask = float(record.best_ask)

    # Convert datetime to ISO string
    ts_wall = record.ts_wall.isoformat()

    # Use event_id if available, otherwise use tick_id
    event_id = str(record.event_id) if record.event_id else str(record.tick_id)

    return MarketDataEvent(
        event_id=event_id,
        ts_wall=ts_wall,
        ts_mono=record.ts_mono,
        correlation_id="",  # Not stored in market_ticks table
        run_id=record.run_id,
        schema_version="1.0",  # Default
        source=EventSource.MDP,
        market_slug=record.market_slug,
        outcome=record.outcome,  # Already a string ("UP" or "DOWN")
        best_bid=best_bid,
        best_ask=best_ask,
    )
