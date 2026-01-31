"""Event sink for asynchronous event persistence to PostgreSQL.

Per architecture.mdc §G: Event sink must not affect trading components.
Subscribes to EventBus and writes events in batches to PostgreSQL.

This module provides:
- EventSink: Subscribes to all event topics and persists events asynchronously
- SimpleCircuitBreaker: Circuit breaker for database failures
- Batch writing with retry logic and graceful error handling
"""

import asyncio
import random
from datetime import datetime
from enum import Enum

from polytrader.events.bus import EventBus, Topic
from polytrader.events.stores import PostgreSQLEventStore
from polytrader.events.types import Event
from polytrader.logging_config import logger

# All event topics that EventSink should subscribe to
# These are the topics that publish Event instances
_EVENT_TOPICS = [
    "MARKET_DATA",
    "PROPOSALS",
    "ORDERS",
    "MARKET_CHANGE",
    "SYSTEM_LIFECYCLE",
    "RISK_CHECKS",
    "APPROVED_PROPOSALS",
    "ORDER_CREATED",
    "ORDER_SUBMITTED",
    "ORDER_ACKS",
    "ORDER_REJECTS",
    "FILLS",
    "ORDER_CANCELS",
    "SUBMIT_ORDER_COMMANDS",
    "CANCEL_ORDER_COMMANDS",
    "EXECUTION_REQUESTS",
    "EXECUTION_RESPONSES",
    "EXECUTION_ERRORS",
    "MARKET_DISCOVERY",
    "SIGNALS",
    "TARGETS",
    "USER_STREAM_ACKS",
    "USER_STREAM_REJECTS",
    "USER_STREAM_FILLS",
    "USER_STREAM_CANCELS",
    "RECONCILE",
    "CIRCUIT_BREAKER",
    "POSITION_UPDATES",
    "PNL_UPDATES",
    "STRATEGY_CLOSED_TRADES",
    "CANCEL_REQUESTED",
    "VENUE_CONNECTED",
    "VENUE_DISCONNECTED",
]


class CircuitState(str, Enum):
    """Circuit breaker state."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit open, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class SimpleCircuitBreaker:
    """Simple circuit breaker for database failures.

    Per proposal §13.1: Circuit breaker opens after 10 consecutive failures,
    stays open for 5 minutes, then goes half-open to test recovery.

    This is a simplified circuit breaker specifically for EventSink database operations.
    It's separate from the reconciliation circuit breaker in ops/control.py.
    """

    def __init__(
        self,
        failure_threshold: int = 10,
        cooldown_seconds: float = 300.0,  # 5 minutes
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening (default: 10)
            cooldown_seconds: Seconds to wait before half-open state (default: 300.0)
        """
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._half_open_test_count = 0

    def record_success(self) -> None:
        """Record a successful operation."""
        if self._state == CircuitState.HALF_OPEN:
            # Success in half-open: close circuit
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_test_count = 0
            logger.info("Circuit breaker closed after successful test")
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed operation."""
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker opened after {count} failures",
                    count=self._failure_count,
                )
        elif self._state == CircuitState.HALF_OPEN:
            # Failure in half-open: open circuit again
            self._state = CircuitState.OPEN
            self._half_open_test_count = 0
            logger.warning("Circuit breaker reopened after half-open test failure")

    def is_open(self) -> bool:
        """Check if circuit is open (should reject requests).

        Returns:
            True if circuit is open, False if closed or half-open
        """
        if self._state == CircuitState.OPEN:
            # Check if cooldown period has passed
            if self._last_failure_time:
                elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                if elapsed >= self._cooldown_seconds:
                    # Transition to half-open
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_test_count = 0
                    logger.info("Circuit breaker entering half-open state")
                    return False  # Half-open allows one test request
            return True  # Still in cooldown
        return False  # Closed or half-open

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if request should be allowed, False if circuit is open
        """
        if self._state == CircuitState.OPEN:
            return not self.is_open()  # Will transition to half-open if cooldown passed
        return True  # Closed or half-open

    @property
    def state(self) -> CircuitState:
        """Get current circuit breaker state."""
        # Update state if needed (check cooldown)
        if self._state == CircuitState.OPEN:
            self.is_open()  # This will transition to half-open if cooldown passed
        return self._state


class EventSink:
    """Event sink that writes events to PostgreSQL asynchronously.

    Per architecture.mdc §G: Event sink must not affect trading components.
    Subscribes to EventBus and writes events in batches.

    Features:
    - Subscribes to all event topics
    - Batch writing (100 events or 1.0s flush interval)
    - Retry logic with exponential backoff (max 5 retries)
    - Circuit breaker for database failures (opens after 10 failures, 5min cooldown)
    - Graceful error handling (never throws, only logs)
    - Buffer overflow protection (drops oldest events if buffer > 10,000)

    The EventSink runs as a separate async task and does not block trading operations.
    If database writes fail, events are logged but trading continues unaffected.
    """

    def __init__(
        self,
        bus: EventBus,
        store: PostgreSQLEventStore,
        batch_size: int = 100,
        flush_interval_s: float = 1.0,
        max_buffer_size: int = 10000,
    ) -> None:
        """Initialize event sink.

        Args:
            bus: Event bus to subscribe to
            store: PostgreSQL event store
            batch_size: Maximum number of events per batch (default: 100)
            flush_interval_s: Seconds between flushes (default: 1.0)
            max_buffer_size: Maximum buffer size before dropping events (default: 10000)
        """
        self._bus = bus
        self._store = store
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_s
        self._max_buffer_size = max_buffer_size

        self._buffer: list[Event] = []
        self._running = False
        self._circuit_breaker = SimpleCircuitBreaker()
        self._subscribed_queues: list[asyncio.Queue[Event]] = []
        self._flush_task: asyncio.Task[None] | None = None
        self._consume_tasks: list[asyncio.Task[None]] = []

    async def run(self) -> None:
        """Start event sink (subscribe to events and write to DB).

        This method:
        1. Subscribes to all event topics
        2. Starts consumer tasks for each topic
        3. Starts flush task for batch writing
        4. Runs until stop() is called

        Per proposal: Event sink runs independently and never throws exceptions.
        All errors are logged but do not crash the sink.
        """
        if self._running:
            logger.warning("EventSink is already running")
            return

        self._running = True
        logger.info("Starting EventSink")

        try:
            # Subscribe to all event topics
            await self._subscribe_to_all_topics()

            # Start flush task
            self._flush_task = asyncio.create_task(self._flush_loop())

            # Start consumer tasks for each subscribed queue
            for queue in self._subscribed_queues:
                task = asyncio.create_task(self._consume_queue(queue))
                self._consume_tasks.append(task)

            logger.info(
                "EventSink started: {topic_count} topics, batch_size={batch_size}, "
                "flush_interval={flush_interval}s",
                topic_count=len(self._subscribed_queues),
                batch_size=self._batch_size,
                flush_interval=self._flush_interval_s,
            )

            # Wait for all tasks (they run until stop() is called)
            await asyncio.gather(*self._consume_tasks, self._flush_task, return_exceptions=True)

        except Exception as e:
            logger.exception(
                "EventSink run() error (should never happen): {error}",
                error=str(e),
            )
        finally:
            self._running = False

    async def _subscribe_to_all_topics(self) -> None:
        """Subscribe to all event topics.

        Gets all event topics from the events module using lazy loading (__getattr__).
        """
        import polytrader.events as events_module

        # Get all topics using lazy loading (__getattr__)
        topics: list[Topic[Event]] = []
        for topic_name in _EVENT_TOPICS:
            try:
                topic = getattr(events_module, topic_name)
                topics.append(topic)
            except AttributeError:
                logger.warning(
                    "EventSink: Topic {topic_name} not found, skipping",
                    topic_name=topic_name,
                )

        # Subscribe to all topics
        for topic in topics:
            queue = self._bus.subscribe(topic)
            self._subscribed_queues.append(queue)

    async def _consume_queue(self, queue: asyncio.Queue[Event]) -> None:
        """Consume events from a topic queue.

        Args:
            queue: Queue to consume events from
        """
        while self._running:
            try:
                # Wait for event with timeout to allow checking _running flag
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue

                # Only buffer Event instances
                if isinstance(event, Event):
                    await self._add_to_buffer(event)

            except Exception as e:
                logger.exception(
                    "Error consuming event from queue: {error}",
                    error=str(e),
                )
                # Continue consuming even on error

    async def _add_to_buffer(self, event: Event) -> None:
        """Add event to buffer.

        Args:
            event: Event to add to buffer
        """
        # Check buffer overflow
        if len(self._buffer) >= self._max_buffer_size:
            # Drop oldest event (FIFO)
            dropped = self._buffer.pop(0)
            logger.warning(
                "EventSink buffer overflow: dropped event {event_id}",
                event_id=dropped.event_id,
                event_type=type(dropped).__name__,
            )

        self._buffer.append(event)

    async def _flush_loop(self) -> None:
        """Flush loop: periodically flush buffered events to database."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval_s)
                if self._running:
                    await self._flush_batch()
            except Exception as e:
                logger.exception(
                    "Error in flush loop: {error}",
                    error=str(e),
                )
                # Continue flushing even on error

    async def _flush_batch(self) -> None:
        """Flush buffered events to database.

        Per proposal: Uses retry logic with exponential backoff.
        Never throws exceptions - all errors are logged.
        """
        if not self._buffer:
            return

        # Check circuit breaker
        if not self._circuit_breaker.allow_request():
            logger.debug("Circuit breaker is open, skipping flush")
            return

        # Extract batch
        batch_size = min(self._batch_size, len(self._buffer))
        batch = self._buffer[:batch_size]
        self._buffer = self._buffer[batch_size:]

        # Try to write batch with retry logic
        success = await self._write_batch_with_retry(batch)

        if success:
            self._circuit_breaker.record_success()
        else:
            self._circuit_breaker.record_failure()
            # Put events back in buffer (at the front, so they're retried first)
            self._buffer = batch + self._buffer

    async def _write_batch_with_retry(self, batch: list[Event]) -> bool:
        """Write batch to database with retry logic.

        Args:
            batch: List of events to write

        Returns:
            True if write succeeded, False otherwise
        """
        max_retries = 5
        base_delay = 1.0  # 1 second
        max_delay = 60.0  # 60 seconds

        for attempt in range(max_retries):
            try:
                # Write all events in batch
                for event in batch:
                    await self._store.append(event)

                logger.debug(
                    "EventSink flushed {count} events to database",
                    count=len(batch),
                )
                return True

            except Exception as e:
                if attempt < max_retries - 1:
                    # Calculate exponential backoff with jitter
                    delay = min(base_delay * (2**attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)  # 10% jitter
                    total_delay = delay + jitter

                    logger.warning(
                        "EventSink batch write failed (attempt {attempt}/{max_retries}): {error}. "
                        "Retrying in {delay:.2f}s",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error=str(e),
                        delay=total_delay,
                    )

                    await asyncio.sleep(total_delay)
                else:
                    # Final attempt failed
                    logger.error(
                        "EventSink batch write failed after {max_retries} attempts: {error}",
                        max_retries=max_retries,
                        error=str(e),
                        event_count=len(batch),
                    )
                    return False

        return False

    async def stop(self) -> None:
        """Stop event sink (flush remaining events).

        This method:
        1. Stops consuming new events
        2. Flushes remaining events in buffer
        3. Waits for all tasks to complete
        """
        if not self._running:
            return

        logger.info("Stopping EventSink")

        self._running = False

        # Cancel consumer tasks
        for task in self._consume_tasks:
            task.cancel()

        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()

        # Wait for tasks to complete
        if self._consume_tasks:
            await asyncio.gather(*self._consume_tasks, return_exceptions=True)
        if self._flush_task:
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush of remaining events
        if self._buffer:
            logger.info(
                "EventSink flushing {count} remaining events",
                count=len(self._buffer),
            )
            await self._flush_batch()

        logger.info("EventSink stopped")
