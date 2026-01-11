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
from polytrader.events import MARKET_CHANGE, MARKET_DATA, SIGNALS, EventBus
from polytrader.logging_config import logger
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.observer import IObserver
from polytrader.position_manager import IPositionManager
from polytrader.store import IMarketDataStore
from polytrader.strategies import IStrategy
from polytrader.types import MarketChangeEvent, Position


class MarketSupervisor:
    """Manages market-specific component lifecycle.

    Coordinates Adapter, Observer, Strategy per market.
    Handles market transitions and strategy evaluation.

    Per flows.mdc §4: Strategy layer produces SignalEvent (probabilistic scores).
    Supervisor evaluates strategy on-demand for fast decision-making.
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
        """Start the supervisor and discover initial market."""
        self._running = True
        logger.bind(pattern=self.pattern).info("Starting MarketSupervisor")

        # Initial market discovery
        market = await self.discovery.get_current_market(self.pattern)
        if not market:
            raise RuntimeError(f"No active market found for pattern: {self.pattern}")

        await self._transition_to_market(market)

        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_market())

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

        Args:
            new_market: Market slug to transition to
        """
        old_market = self.current_market

        if old_market == new_market:
            logger.bind(market=new_market).debug("Already on market, skipping transition")
            return

        logger.bind(old_market=old_market, new_market=new_market).info(
            "Transitioning from {old_market} to {new_market}"
        )

        # Stop old components
        await self._stop_components()

        # Update current market
        self.current_market = new_market

        # Create new components
        self.adapter = self.adapter_factory(new_market)
        self.observer = self.observer_factory(self.adapter)
        self.strategy = self.strategy_factory(new_market)

        # Start new components
        self._observer_task = asyncio.create_task(self.observer.run())
        # Strategy evaluation: subscribe to MARKET_DATA and evaluate on-demand
        self._strategy_evaluation_task = asyncio.create_task(self._evaluate_strategy_loop())
        # Strategy background tasks (if strategy needs them)
        self._strategy_background_task = asyncio.create_task(self._run_strategy_background())

        # Publish market change event
        event = MarketChangeEvent(
            old_market=old_market,
            new_market=new_market,
        )
        await self.bus.publish(MARKET_CHANGE, event)

        logger.bind(new_market=new_market).info(
            "Successfully transitioned to market: {new_market}", new_market=new_market
        )

    async def _stop_components(self) -> None:
        """Stop all current components."""
        if self.observer:
            self.observer.stop()
        if self.strategy:
            self.strategy.stop()

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
                except Exception:
                    logger.exception("Error evaluating strategy")
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
        logger.bind(interval=self.monitor_interval).info(
            "Starting market monitor (checking every {interval}s)"
        )

        while self._running:
            await asyncio.sleep(self.monitor_interval)

            try:
                # Check if current market is still active
                current = await self.discovery.get_current_market(self.pattern)

                if current and current != self.current_market:
                    # Market has changed
                    logger.bind(old_market=self.current_market, new_market=current).info(
                        "Market change detected: {old_market} → {new_market}"
                    )
                    await self._transition_to_market(current)
                elif not current:
                    # No active market (gap between markets)
                    logger.warning("No active market found, waiting...")
                    # Retry in shorter interval
                    await asyncio.sleep(5.0)
            except Exception:
                logger.exception("Error in market monitor")
                # Continue monitoring despite errors

    async def _cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up MarketSupervisor")
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

    def stop(self) -> None:
        """Stop the supervisor (non-blocking)."""
        self._running = False

    @property
    def current_market_slug(self) -> str | None:
        """Get current active market slug."""
        return self.current_market
