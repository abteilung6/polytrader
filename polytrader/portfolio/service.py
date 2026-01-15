"""Portfolio service/orchestrator per flows.mdc §5."""

import asyncio
import time

from polytrader.events import PROPOSALS, SIGNALS, TARGETS, EventBus
from polytrader.events.types import MarketDataEvent, SignalEvent, TargetEvent
from polytrader.logging_config import logger
from polytrader.obs.logging import bind_strategy_context
from polytrader.obs.metrics import IMetricsCollector, MemoryMetricsCollector
from polytrader.portfolio.intents import convert_target_to_intent
from polytrader.portfolio.sizing import calculate_size
from polytrader.portfolio.targets import convert_signal_to_target
from polytrader.position_manager import IPositionManager
from polytrader.store import IMarketDataStore
from polytrader.types import Outcome, Position


class PortfolioService:
    """Orchestrates portfolio construction layer.

    Subscribes to SIGNALS topic and converts signals → targets → order intents.
    Per flows.mdc §5: Portfolio Construction converts scores → targets → intents.
    """

    def __init__(
        self,
        bus: EventBus,
        store: IMarketDataStore,
        position_manager: IPositionManager | None = None,
        fixed_size_usd: float = 1.0,
        metrics: IMetricsCollector | None = None,
    ) -> None:
        """Initialize portfolio service.

        Args:
            bus: Event bus for subscribing/publishing
            store: Market data store (for current market data)
            position_manager: Position manager (for portfolio-aware sizing)
            fixed_size_usd: Fixed size for targets (default: 1.0)
            metrics: Metrics collector (optional, for observability)
        """
        self.bus = bus
        self.store = store
        self.position_manager = position_manager
        self.fixed_size_usd = fixed_size_usd
        self.metrics = metrics or MemoryMetricsCollector()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the portfolio service (subscribe to SIGNALS)."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the portfolio service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main loop: subscribe to SIGNALS and process."""
        signals_queue = self.bus.subscribe(SIGNALS)

        bind_strategy_context(
            logger, strategy_id="portfolio_service", event_type="PortfolioServiceStarted"
        ).info("PortfolioService started, subscribing to SIGNALS")

        try:
            while self._running:
                signal = await signals_queue.get()
                await self._process_signal(signal)
        except asyncio.CancelledError:
            bind_strategy_context(
                logger, strategy_id="portfolio_service", event_type="PortfolioServiceStopped"
            ).info("PortfolioService stopped")
            raise
        except Exception:
            bind_strategy_context(
                logger,
                strategy_id="portfolio_service",
                event_type="PortfolioServiceError",
                error_class="system",
            ).exception("Error in PortfolioService")
            raise

    async def _process_signal(self, signal: SignalEvent) -> None:
        """Process a SignalEvent: convert to target → size → intent.

        Per flows.mdc §5: Convert scores → target exposure → order intent.
        """
        start_time = time.perf_counter()
        self.metrics.increment_counter("portfolio_signals_received_total")

        try:
            # Step 1: Convert signal to target
            target = convert_signal_to_target(signal, fixed_size_usd=self.fixed_size_usd)
            if target is None:
                latency_ms = (time.perf_counter() - start_time) * 1000
                bind_strategy_context(
                    logger,
                    strategy_id=signal.model_id,
                    correlation_id=signal.correlation_id,
                    market_slug=signal.market_slug,
                    outcome=signal.outcome,
                    event_type="PortfolioNoTarget",
                    latency_ms=latency_ms,
                ).debug(
                    "No target generated from signal",
                    edge=signal.edge,
                    confidence=signal.confidence,
                )
                return

            self.metrics.increment_counter("portfolio_targets_generated_total")

            # Step 2: [Optional] Publish TargetEvent for observability
            target_event = TargetEvent(
                market_slug=target.market_slug,
                outcome=target.outcome,
                target_exposure=target.target_exposure,
                target_rationale=target.rationale,
                constraint_binding=target.constraint_binding,
                sizing_metadata=target.sizing_metadata,
                correlation_id=signal.correlation_id,
            )
            await self.bus.publish(TARGETS, target_event)

            # Step 3: Get current market data (for limit_price)
            market_data = self._get_current_market_data(signal.market_slug, signal.outcome)
            if market_data is None:
                latency_ms = (time.perf_counter() - start_time) * 1000
                bind_strategy_context(
                    logger,
                    strategy_id=signal.model_id,
                    correlation_id=signal.correlation_id,
                    market_slug=signal.market_slug,
                    outcome=signal.outcome,
                    event_type="PortfolioNoMarketData",
                    error_class="system",
                    latency_ms=latency_ms,
                ).warning("No market data available for signal")
                return

            # Step 4: Get current position (for portfolio-aware sizing)
            current_position = self._get_current_position(signal.market_slug, signal.outcome)

            # Step 5: Calculate order size (portfolio-aware)
            size = calculate_size(target, current_position)
            if size <= 0.0:
                latency_ms = (time.perf_counter() - start_time) * 1000
                bind_strategy_context(
                    logger,
                    strategy_id=signal.model_id,
                    correlation_id=signal.correlation_id,
                    market_slug=signal.market_slug,
                    outcome=signal.outcome,
                    event_type="PortfolioNoSize",
                    latency_ms=latency_ms,
                ).debug(
                    "No order size needed (target already met or size <= 0)",
                    target_exposure=target.target_exposure,
                    current_position=current_position.size if current_position else 0.0,
                    calculated_size=size,
                )
                return

            # Step 6: Convert target to order intent
            intent = convert_target_to_intent(target, market_data, signal, size)
            if intent is None:
                latency_ms = (time.perf_counter() - start_time) * 1000
                bind_strategy_context(
                    logger,
                    strategy_id=signal.model_id,
                    correlation_id=signal.correlation_id,
                    market_slug=target.market_slug,
                    outcome=target.outcome,
                    event_type="PortfolioNoIntent",
                    error_class="system",
                    latency_ms=latency_ms,
                ).warning("No order intent generated from target")
                return

            # Step 7: Publish OrderIntentEvent to PROPOSALS (RiskChecker subscribes here)
            await self.bus.publish(PROPOSALS, intent)
            self.metrics.increment_counter("portfolio_intents_generated_total")

            # Record processing latency
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.record_histogram("portfolio_processing_latency_ms", latency_ms)

            bind_strategy_context(
                logger,
                strategy_id=signal.model_id,
                correlation_id=intent.correlation_id,
                market_slug=intent.market_slug,
                outcome=intent.outcome,
                event_type="PortfolioIntentPublished",
                latency_ms=latency_ms,
            ).info(
                "Published OrderIntentEvent to PROPOSALS",
                side=intent.side,
                size=intent.size,
                limit_price=intent.limit_price,
            )

        except Exception:
            self.metrics.increment_counter("portfolio_errors_total")
            latency_ms = (time.perf_counter() - start_time) * 1000
            bind_strategy_context(
                logger,
                strategy_id=signal.model_id,
                correlation_id=signal.correlation_id,
                market_slug=signal.market_slug,
                outcome=signal.outcome,
                event_type="PortfolioProcessingError",
                error_class="system",
                latency_ms=latency_ms,
            ).exception("Error processing signal")
            # Continue processing despite errors

    def _get_current_market_data(self, market_slug: str, outcome: str) -> MarketDataEvent | None:
        """Get current market data from store.

        Returns the most recent MarketDataEvent for the given market/outcome.
        """
        outcome_typed: Outcome = outcome  # type: ignore[assignment]
        history = self.store.history(market_slug, outcome_typed)
        if not history:
            return None
        return history[-1]  # Most recent

    def _get_current_position(self, market_slug: str, outcome: str) -> Position | None:
        """Get current position from position manager.

        Returns the current Position for the given market/outcome, or None if no position.
        """
        if self.position_manager is None:
            return None

        positions = self.position_manager.get_positions()
        if positions is None:
            return None

        # Convert outcome string to Outcome type for dict key
        outcome_typed: Outcome = outcome  # type: ignore[assignment]
        key = (market_slug, outcome_typed)
        return positions.get(key)
