"""Strategy runner: Manages a single strategy's lifecycle and routing.

Per Commit 1.3: StrategyRunner uses shared MarketSupervisor and evaluates
strategy on MARKET_DATA events from the shared supervisor.

Per Platform_Proposal.md §3.1: StrategyRunner routes intents to paper/live
lanes based on strategy activation.

Per flow.md §4: Strategy layer produces SignalEvent (probabilistic scores).
StrategyRunner subscribes to MARKET_DATA and evaluates strategy on-demand.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.db.models import StrategyRecord
from polytrader.events import MARKET_DATA, SIGNALS, EventBus
from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.logging_config import logger
from polytrader.store import IMarketDataStore
from polytrader.supervisor.errors import classify_service_error
from polytrader.supervisor.market import MarketSupervisor
from polytrader.types import Position

if TYPE_CHECKING:
    from polytrader.position_manager import IPositionManager
    from polytrader.strategies.base import IStrategy


class StrategyRunner:
    """Manages a single strategy's lifecycle and routing.

    Per Commit 1.3: StrategyRunner uses a shared MarketSupervisor (created
    by MarketSupervisorRegistry) and evaluates strategy on MARKET_DATA events.

    Responsibilities:
    - Subscribe to MARKET_DATA from shared MarketSupervisor
    - Create strategy instance lazily (on first market data)
    - Evaluate strategy on market data events
    - Publish SignalEvent with model_id = strategy.strategy_id
    - Manage strategy lifecycle (start/stop)

    Attributes:
        strategy: StrategyRecord from registry
        market_supervisor: Shared MarketSupervisor instance (already started)
        bus: Event bus for communication
        store: Market data store
        strategy_factory: Factory for creating strategy instances
        position_manager: Position manager (optional)
        _running: Whether the runner is active
        _strategy_instance: Strategy instance (created lazily)
        _subscription: MARKET_DATA subscription queue
        _evaluation_task: Task for evaluating strategy on market data
        _background_task: Task for strategy background tasks
    """

    def __init__(
        self,
        strategy: StrategyRecord,
        bus: EventBus,
        store: IMarketDataStore,
        market_supervisor: MarketSupervisor,
        strategy_factory: Callable[[str], "IStrategy"],
        position_manager: "IPositionManager | None" = None,
    ) -> None:
        """Initialize strategy runner.

        Args:
            strategy: StrategyRecord from registry
            bus: Event bus for communication
            store: Market data store
            market_supervisor: Shared MarketSupervisor instance (already started)
            strategy_factory: Factory for creating strategy instances
            position_manager: Position manager (optional)
        """
        self.strategy = strategy
        self.bus = bus
        self.store = store
        self.market_supervisor = market_supervisor
        self.strategy_factory = strategy_factory
        self.position_manager = position_manager

        self._running = False
        self._strategy_instance: IStrategy | None = None
        self._subscription: asyncio.Queue[MarketDataEvent] | None = None
        self._evaluation_task: asyncio.Task | None = None
        self._background_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the strategy runner.

        Subscribes to MARKET_DATA events and starts evaluation loop.
        Strategy instance is created lazily on first market data.
        """
        if self._running:
            return

        self._running = True
        logger.bind(
            strategy_id=self.strategy.strategy_id,
            strategy_name=self.strategy.name,
        ).info("Starting StrategyRunner")

        try:
            # Subscribe to MARKET_DATA from shared supervisor
            self._subscription = self.bus.subscribe(MARKET_DATA)

            # Start evaluation loop
            self._evaluation_task = asyncio.create_task(self._evaluate_strategy_loop())

            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
            ).info("StrategyRunner started")
        except Exception:
            self._running = False
            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
                error_class="fatal",
            ).exception("Failed to start StrategyRunner")
            raise

    async def _evaluate_strategy_loop(self) -> None:
        """Evaluate strategy on market data events from shared MarketSupervisor.

        Per flows.mdc §4: Strategy layer produces SignalEvent on-demand.
        This loop subscribes to MARKET_DATA and calls evaluate() directly.
        """
        if self._subscription is None:
            return

        try:
            while self._running:
                event = await self._subscription.get()

                # Filter by current market (check if event matches supervisor's current market)
                if event.market_slug != self.market_supervisor.current_market:
                    continue

                # Create strategy instance on first market data if not created yet
                if self._strategy_instance is None:
                    self._strategy_instance = self.strategy_factory(event.market_slug)
                    # Start background tasks now that strategy exists
                    if self._background_task is None:
                        self._background_task = asyncio.create_task(self._run_strategy_background())

                # Evaluate strategy
                try:
                    positions = self._get_positions()
                    signal = self._strategy_instance.evaluate(event, positions=positions)

                    if signal is not None:
                        # Ensure signal has correct model_id (strategy_id from registry)
                        # Note: strategy.evaluate() may return SignalEvent with different model_id
                        # We override it to use strategy_id from registry
                        if isinstance(signal, SignalEvent):
                            # Create new SignalEvent with correct model_id
                            signal = SignalEvent(
                                market_slug=signal.market_slug,
                                outcome=signal.outcome,
                                p_up=signal.p_up,
                                p_down=signal.p_down,
                                edge=signal.edge,
                                confidence=signal.confidence,
                                model_id=self.strategy.strategy_id,  # Use strategy_id from registry
                                model_version=signal.model_version,
                                snapshot_hash=signal.snapshot_hash,
                                snapshot_version=signal.snapshot_version,
                                rationale=signal.rationale,
                            )

                        # Publish signal to portfolio layer
                        await self.bus.publish(SIGNALS, signal)
                except Exception as e:
                    error_class = classify_service_error(e)
                    logger.bind(
                        strategy_id=self.strategy.strategy_id,
                        market=event.market_slug,
                        error_type=type(e).__name__,
                        error_class=error_class,
                    ).exception("Error evaluating strategy")
                    # Continue processing despite errors
        except Exception:
            logger.exception("Error in strategy evaluation loop")
            raise

    async def _run_strategy_background(self) -> None:
        """Run strategy background tasks (if strategy needs them)."""
        if self._strategy_instance is None:
            return

        try:
            await self._strategy_instance.run()
        except Exception:
            logger.exception("Error in strategy background task")
            # Continue despite errors

    def _get_positions(self) -> dict[tuple[str, str], Position]:
        """Get current positions for strategy evaluation.

        Returns:
            Dict mapping (market_slug, outcome) to Position
        """
        if self.position_manager is None:
            return {}

        # Get positions for this strategy
        # Note: PositionManager may need strategy_id filtering in future
        all_positions = self.position_manager.get_positions()
        if all_positions is None:
            return {}

        # Convert Outcome to str for type compatibility
        # PositionManager returns dict[tuple[str, Outcome], Position]
        # but we need dict[tuple[str, str], Position] for strategy.evaluate()

        result: dict[tuple[str, str], Position] = {}
        for (market_slug, outcome), position in all_positions.items():
            result[(market_slug, str(outcome))] = position
        return result

    async def stop(self) -> None:
        """Stop the strategy runner.

        Cancels evaluation/background tasks and unsubscribes from MARKET_DATA.
        Does NOT stop MarketSupervisor (registry manages lifecycle).
        """
        if not self._running:
            return

        self._running = False
        logger.bind(
            strategy_id=self.strategy.strategy_id,
            strategy_name=self.strategy.name,
        ).info("Stopping StrategyRunner")

        try:
            # Cancel tasks
            if self._evaluation_task:
                self._evaluation_task.cancel()
                try:
                    await self._evaluation_task
                except asyncio.CancelledError:
                    pass

            if self._background_task:
                self._background_task.cancel()
                try:
                    await self._background_task
                except asyncio.CancelledError:
                    pass

            # Unsubscribe from market data (just clear reference, queue will be garbage collected)
            # Note: EventBus doesn't have explicit unsubscribe, but stopping the task
            # that reads from the queue effectively unsubscribes
            self._subscription = None

            # Stop strategy instance if created
            if self._strategy_instance:
                self._strategy_instance.stop()

            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
            ).info("StrategyRunner stopped")
        except Exception:
            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
                error_class="fatal",
            ).exception("Error stopping StrategyRunner")
            raise

    def is_running(self) -> bool:
        """Check if the runner is active.

        Returns:
            True if running, False otherwise
        """
        return self._running
