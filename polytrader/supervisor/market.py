"""Market supervisor: Manages market-specific component lifecycle.

Per two-supervisor architecture:
- MarketSupervisor manages: Adapter, Observer, Strategy (per market)
- Handles market transitions and strategy evaluation
- Queries PositionManager from SystemSupervisor (doesn't own it)
"""

import asyncio
import time
from collections.abc import Callable

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_CHANGE, MARKET_DATA, SIGNALS, SYSTEM_LIFECYCLE, EventBus
from polytrader.events.types import (
    MarketChangeEvent,
    ServiceErrorEvent,
    ServiceStartedEvent,
    ServiceStoppedEvent,
)
from polytrader.logging_config import logger
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.observer import IObserver
from polytrader.position_manager import IPositionManager
from polytrader.store import IMarketDataStore
from polytrader.strategies import IStrategy
from polytrader.supervisor.errors import classify_service_error
from polytrader.supervisor.metrics import (
    record_market_transition,
    record_service_error,
    record_service_started,
    record_service_stopped,
)
from polytrader.types import Position

SUPERVISOR_TYPE = "MarketSupervisor"


class MarketSupervisor:
    """Manages market-specific component lifecycle.

    Coordinates Adapter, Observer, Strategy per market.
    Handles market transitions and strategy evaluation.
    Per flows.mdc §4: Strategy layer produces SignalEvent (probabilistic scores).
    Supervisor evaluates strategy on-demand for fast decision-making.

    Per observability.mdc:
    - Emits ServiceStartedEvent, ServiceStoppedEvent, ServiceErrorEvent
    - Records metrics (transitions, service failures)
    - Classifies errors (retryable vs fatal)
    - Structured logging with context
    """

    def __init__(
        self,
        pattern: str,
        discovery_service: IMarketDiscoveryService,
        adapter_factory: Callable[[str], IMarketDataAdapter],
        observer_factory: Callable[[IMarketDataAdapter], IObserver],
        strategy_factory: Callable[[str], IStrategy],
        bus: EventBus,
        store: IMarketDataStore,
        position_manager: IPositionManager | None = None,
        monitor_interval: float = 1.0,
        evaluation_throttle_ms: float = 0.0,
    ) -> None:
        """Initialize the market supervisor.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")
            discovery_service: Service for finding active markets
            adapter_factory: Factory function to create adapters
            observer_factory: Factory function to create observers
            strategy_factory: Factory function to create strategies
            bus: Event bus for communication
            store: Market data store for historical data
            position_manager: Position manager reference (from SystemSupervisor, for querying)
            monitor_interval: How often to check for market changes (seconds, default: 1.0)
            evaluation_throttle_ms: Minimum time between strategy evaluations (ms, default: 0.0)
        """
        self.pattern = pattern
        self.discovery = discovery_service
        self.adapter_factory = adapter_factory
        self.observer_factory = observer_factory
        self.strategy_factory = strategy_factory
        self.bus = bus
        self.store = store
        self.position_manager = position_manager
        self.monitor_interval = monitor_interval
        self.evaluation_throttle_ms = evaluation_throttle_ms

        # Current state
        self.current_market: str | None = None
        self.adapter: IMarketDataAdapter | None = None
        self.observer: IObserver | None = None
        self.strategy: IStrategy | None = None

        # Tasks
        self._running = False
        self._observer_task: asyncio.Task | None = None
        self._strategy_evaluation_task: asyncio.Task | None = None
        self._strategy_background_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None

        # Evaluation throttling
        self._last_evaluation_time: float = 0.0

    async def start(self) -> None:
        """Start the supervisor and discover initial market.

        Per observability.mdc:
        - Emits ServiceStartedEvent
        - Records metrics
        - Classifies errors
        """
        self._running = True
        logger.bind(supervisor=SUPERVISOR_TYPE, pattern=self.pattern).info(
            "Starting MarketSupervisor"
        )

        try:
            # Initial market discovery
            market = await self.discovery.get_current_market(self.pattern)
            if not market:
                error_msg = f"No active market found for pattern: {self.pattern}"
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    pattern=self.pattern,
                    error_class="fatal",
                ).error(error_msg)

                # Emit error event
                error_event = ServiceErrorEvent(
                    service_name="MarketSupervisor",
                    supervisor_type=SUPERVISOR_TYPE,
                    error_type="RuntimeError",
                    error_message=error_msg,
                    error_class="fatal",
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

                record_service_error("MarketSupervisor", SUPERVISOR_TYPE, "RuntimeError", "fatal")
                raise RuntimeError(error_msg)

            await self._transition_to_market(market)

            # Start monitoring task
            self._monitor_task = asyncio.create_task(self._monitor_market())

            logger.bind(supervisor=SUPERVISOR_TYPE, pattern=self.pattern, market=market).info(
                "MarketSupervisor started (initial market: {market})",
                market=market,
            )

        except Exception as e:
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                pattern=self.pattern,
                error_type=error_type,
                error_class=error_class,
            ).exception(
                "Failed to start MarketSupervisor: {error}",
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name="MarketSupervisor",
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=error_msg,
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            record_service_error("MarketSupervisor", SUPERVISOR_TYPE, error_type, error_class)
            raise

    async def run(self) -> None:
        """Run the supervisor (wait for tasks to complete)."""
        if not self._running:
            raise RuntimeError("MarketSupervisor not started. Call start() first.")

        try:
            # Wait for all tasks
            tasks = [
                t
                for t in [
                    self._observer_task,
                    self._strategy_evaluation_task,
                    self._strategy_background_task,
                    self._monitor_task,
                ]
                if t is not None
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await self._cleanup()

    async def _transition_to_market(self, new_market: str) -> None:
        """Transition all components to a new market.

        Stops all current components, then starts new ones with the new market.

        Per observability.mdc:
        - Emits ServiceStartedEvent, ServiceStoppedEvent for components
        - Records metrics (transitions)
        - Classifies errors

        Args:
            new_market: Market slug to transition to
        """
        old_market = self.current_market

        if old_market == new_market:
            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                market=new_market,
                old_market=old_market,
            ).debug(
                "⏭️  Skipping transition: already on market {market} (old={old})",
                market=new_market,
                old=old_market,
            )
            return

        transition_start = time.perf_counter()
        logger.bind(
            supervisor=SUPERVISOR_TYPE,
            old_market=old_market,
            new_market=new_market,
        ).info(
            "Transitioning from {old_market} to {new_market}",
            old_market=old_market or "None",
            new_market=new_market,
        )

        try:
            # Stop old components
            await self._stop_components()

            # Update current market
            self.current_market = new_market

            # Create and start new components with observability
            component_start = time.perf_counter()

            # Adapter
            self.adapter = self.adapter_factory(new_market)
            adapter_start_ms = (time.perf_counter() - component_start) * 1000
            record_service_started("Adapter", SUPERVISOR_TYPE, adapter_start_ms)
            started_event = ServiceStartedEvent(
                service_name="Adapter",
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=adapter_start_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            # Observer
            component_start = time.perf_counter()
            self.observer = self.observer_factory(self.adapter)
            self._observer_task = asyncio.create_task(self.observer.run())
            observer_start_ms = (time.perf_counter() - component_start) * 1000
            record_service_started("Observer", SUPERVISOR_TYPE, observer_start_ms)
            started_event = ServiceStartedEvent(
                service_name="Observer",
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=observer_start_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            # Strategy
            component_start = time.perf_counter()
            self.strategy = self.strategy_factory(new_market)
            # Strategy evaluation: subscribe to MARKET_DATA and evaluate on-demand
            self._strategy_evaluation_task = asyncio.create_task(self._evaluate_strategy_loop())
            # Strategy background tasks (if strategy needs them)
            self._strategy_background_task = asyncio.create_task(self._run_strategy_background())
            strategy_start_ms = (time.perf_counter() - component_start) * 1000
            record_service_started("Strategy", SUPERVISOR_TYPE, strategy_start_ms)
            started_event = ServiceStartedEvent(
                service_name="Strategy",
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=strategy_start_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            # Record transition metric
            record_market_transition(SUPERVISOR_TYPE, old_market, new_market)

            # Publish market change event (only once per actual transition)
            event = MarketChangeEvent(
                old_market=old_market,
                new_market=new_market,
            )
            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                old_market=old_market,
                new_market=new_market,
                event_id=event.event_id,
            ).info(
                "📢 Publishing MarketChangeEvent: {old_market} → {new_market} (event_id={event_id})",
                old_market=old_market or "None",
                new_market=new_market,
                event_id=event.event_id,
            )
            await self.bus.publish(MARKET_CHANGE, event)

            transition_time_ms = (time.perf_counter() - transition_start) * 1000
            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                new_market=new_market,
                transition_time_ms=transition_time_ms,
            ).info(
                "Successfully transitioned to market: {new_market} in {time_ms:.1f}ms",
                new_market=new_market,
                time_ms=transition_time_ms,
            )

        except Exception as e:
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                old_market=old_market,
                new_market=new_market,
                error_type=error_type,
                error_class=error_class,
            ).exception(
                "Failed to transition to market {new_market}: {error}",
                new_market=new_market,
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name="MarketSupervisor",
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=f"Transition error: {error_msg}",
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            record_service_error("MarketSupervisor", SUPERVISOR_TYPE, error_type, error_class)
            raise

    async def _stop_components(self) -> None:
        """Stop all current components.

        Per observability.mdc:
        - Emits ServiceStoppedEvent for each component
        - Records metrics
        """
        # Stop components in reverse order
        if self.strategy:
            try:
                self.strategy.stop()
                record_service_stopped("Strategy", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="Strategy",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="Strategy",
                    error_type=type(e).__name__,
                ).exception("Error stopping Strategy: {error}", error=str(e))

        if self.observer:
            try:
                self.observer.stop()
                record_service_stopped("Observer", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="Observer",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="Observer",
                    error_type=type(e).__name__,
                ).exception("Error stopping Observer: {error}", error=str(e))

        # Cancel tasks
        tasks = [
            self._observer_task,
            self._strategy_evaluation_task,
            self._strategy_background_task,
        ]

        for task in tasks:
            if task and not task.done():
                task.cancel()

        # Wait for tasks to complete
        if tasks:
            await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)

        # Clear references
        self._observer_task = None
        self._strategy_evaluation_task = None
        self._strategy_background_task = None

    async def _evaluate_strategy_loop(self) -> None:
        """Evaluate strategy on market data events (fast path).

        Per flows.mdc §4: Strategy layer produces SignalEvent on-demand.
        This loop subscribes to MARKET_DATA and calls evaluate() directly.
        """
        if self.strategy is None:
            return

        market_data_queue = self.bus.subscribe(MARKET_DATA)

        try:
            while self._running:
                event = await market_data_queue.get()

                # Filter by current market
                if event.market_slug != self.current_market:
                    continue

                # Throttle evaluation if configured
                if self.evaluation_throttle_ms > 0.0:
                    now = time.perf_counter() * 1000  # ms
                    if now - self._last_evaluation_time < self.evaluation_throttle_ms:
                        continue
                    self._last_evaluation_time = now

                # Fast, synchronous evaluation (no async overhead)
                try:
                    signal = self.strategy.evaluate(event, positions=self._get_positions())
                    if signal is not None:
                        # Publish signal to portfolio layer
                        await self.bus.publish(SIGNALS, signal)
                except Exception as e:
                    error_class = classify_service_error(e)
                    error_type = type(e).__name__
                    logger.bind(
                        supervisor=SUPERVISOR_TYPE,
                        market=self.current_market,
                        error_type=error_type,
                        error_class=error_class,
                    ).exception("Error evaluating strategy")
                    # Continue processing despite errors
        except Exception:
            logger.exception("Error in strategy evaluation loop")
            raise

    async def _run_strategy_background(self) -> None:
        """Run strategy background tasks (if strategy needs them).

        Most strategies don't need this (stateless).
        """
        if self.strategy is None:
            return

        try:
            await self.strategy.run()
        except Exception:
            logger.exception("Error in strategy background task")
            # Continue despite errors

    def _get_positions(self) -> dict[tuple[str, str], Position]:
        """Get current positions for strategy context.

        Queries PositionManager from SystemSupervisor (doesn't own it).

        Returns:
            Dict mapping (market_slug, outcome) -> Position
        """
        if self.position_manager is None:
            return {}

        positions = self.position_manager.get_positions()
        if positions is None:
            return {}

        # Cast Outcome (Literal["UP", "DOWN"]) to str for IStrategy protocol
        # Outcome is a subtype of str, so this is safe
        return {(market, str(outcome)): pos for (market, outcome), pos in positions.items()}

    async def _monitor_market(self) -> None:
        """Monitor current market and detect expiration/transitions."""
        logger.bind(
            supervisor=SUPERVISOR_TYPE,
            interval=self.monitor_interval,
        ).info(
            "Starting market monitor (checking every {interval}s)",
            interval=self.monitor_interval,
        )

        while self._running:
            await asyncio.sleep(self.monitor_interval)

            try:
                # Check if current market is still active
                current = await self.discovery.get_current_market(self.pattern)

                if current and current != self.current_market:
                    # Market has changed
                    logger.bind(
                        supervisor=SUPERVISOR_TYPE,
                        old_market=self.current_market,
                        new_market=current,
                    ).info(
                        "🔀 Market change detected: {old_market} → {new_market}",
                        old_market=self.current_market or "None",
                        new_market=current,
                    )
                    await self._transition_to_market(current)
                elif current == self.current_market:
                    # Same market, no change (log at debug level to reduce noise)
                    logger.bind(
                        supervisor=SUPERVISOR_TYPE,
                        market=current,
                    ).debug(
                        "Market unchanged: {market} (no transition needed)",
                        market=current,
                    )
                elif not current:
                    # No active market (gap between markets)
                    logger.bind(
                        supervisor=SUPERVISOR_TYPE,
                        pattern=self.pattern,
                    ).warning("No active market found, waiting...")
                    # Retry in shorter interval
                    await asyncio.sleep(5.0)
            except Exception as e:
                error_class = classify_service_error(e)
                error_type = type(e).__name__
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    error_type=error_type,
                    error_class=error_class,
                ).exception("Error in market monitor")
                # Continue monitoring despite errors

    async def _cleanup(self) -> None:
        """Clean up all resources."""
        logger.bind(supervisor=SUPERVISOR_TYPE).info("Cleaning up MarketSupervisor")
        self._running = False

        # Cancel monitor task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Stop all components
        await self._stop_components()

        logger.bind(supervisor=SUPERVISOR_TYPE).info("MarketSupervisor cleaned up")

    def stop(self) -> None:
        """Stop the supervisor (non-blocking)."""
        self._running = False

    @property
    def current_market_slug(self) -> str | None:
        """Get current active market slug."""
        return self.current_market
