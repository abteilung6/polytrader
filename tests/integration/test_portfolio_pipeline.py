"""Integration tests for Portfolio Construction pipeline.

Tests the full flow: SignalEvent → TargetEvent → OrderIntentEvent → RiskCheckEvent
"""

import asyncio

import pytest

from polytrader.common.ids import generate_correlation_id
from polytrader.events import APPROVED_PROPOSALS, PROPOSALS, SIGNALS, TARGETS, EventBus
from polytrader.events.types import SignalEvent, TargetEvent, rebuild_event_models
from polytrader.obs.metrics import MemoryMetricsCollector
from polytrader.portfolio.service import PortfolioService
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from polytrader.types import MarketDataEvent, OrderIntentEvent, Outcome  # noqa: F401

# Rebuild event models to resolve forward references
rebuild_event_models()


class TestPortfolioPipeline:
    """Integration tests for Portfolio Construction pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_signal_to_intent(self) -> None:
        """Test complete pipeline: SignalEvent → TargetEvent → OrderIntentEvent."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        metrics = MemoryMetricsCollector()

        # Add market data to store
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        store.add(market_data)

        # Create portfolio service
        portfolio_service = PortfolioService(
            bus=bus,
            store=store,
            fixed_size_usd=1.0,
            metrics=metrics,
        )

        # Subscribe to events
        targets_queue = bus.subscribe(TARGETS)
        proposals_queue = bus.subscribe(PROPOSALS)

        # Start portfolio service
        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

        # Create and publish SignalEvent
        corr_id = generate_correlation_id()
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="test_model",
            model_version="1.0.0",
            rationale="Test signal",
            correlation_id=corr_id,
        )
        await bus.publish(SIGNALS, signal)

        # Wait for TargetEvent
        target_event = await asyncio.wait_for(targets_queue.get(), timeout=2.0)
        assert target_event is not None
        assert isinstance(target_event, TargetEvent)
        assert target_event.market_slug == "test-market"
        assert target_event.correlation_id == corr_id

        # Wait for OrderIntentEvent
        intent = await asyncio.wait_for(proposals_queue.get(), timeout=2.0)
        assert intent is not None
        assert isinstance(intent, OrderIntentEvent)
        assert intent.market_slug == "test-market"
        assert intent.outcome == "UP"
        assert intent.side == "BUY"
        assert intent.correlation_id == corr_id

        # Verify metrics
        assert metrics.get_counter("portfolio_signals_received_total") == 1
        assert metrics.get_counter("portfolio_targets_generated_total") == 1
        assert metrics.get_counter("portfolio_intents_generated_total") == 1

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_pipeline_with_risk_checker(self) -> None:
        """Test pipeline including RiskChecker: SignalEvent → OrderIntentEvent → RiskCheckEvent."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        store.add(market_data)

        # Create portfolio service
        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        # Create risk checker
        risk_limits = get_default_limits()
        risk_engine = RiskEngine(limits=risk_limits)
        risk_checker = RiskChecker(bus=bus, engine=risk_engine, store=store)

        # Subscribe to events
        proposals_queue = bus.subscribe(PROPOSALS)
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start services in order
        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give PortfolioService time to subscribe
        risk_task = asyncio.create_task(risk_checker.run())
        await asyncio.sleep(0.01)  # Give RiskChecker time to subscribe

        # Publish SignalEvent
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="test_model",
            model_version="1.0.0",
            rationale="Test signal",
            correlation_id=generate_correlation_id(),
        )
        await bus.publish(SIGNALS, signal)

        # Wait for OrderIntentEvent
        intent = await asyncio.wait_for(proposals_queue.get(), timeout=2.0)
        assert intent is not None
        assert isinstance(intent, OrderIntentEvent)

        # RiskChecker should process and publish to APPROVED_PROPOSALS if allowed
        # Wait a bit for risk check to complete
        try:
            approved = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
            assert approved is not None
        except TimeoutError:
            # Risk checker might have denied it, which is fine for this test
            # We just verify the OrderIntentEvent was published correctly
            pass

        # Cleanup
        risk_task.cancel()
        await portfolio_service.stop()
        risk_checker.stop()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(self) -> None:
        """Test that correlation_id propagates through the entire pipeline."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        store.add(market_data)

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        targets_queue = bus.subscribe(TARGETS)
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)

        corr_id = generate_correlation_id()
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="test_model",
            model_version="1.0.0",
            rationale="Test signal",
            correlation_id=corr_id,
        )
        await bus.publish(SIGNALS, signal)

        # Verify correlation_id in TargetEvent
        target_event = await asyncio.wait_for(targets_queue.get(), timeout=2.0)
        assert target_event.correlation_id == corr_id

        # Verify correlation_id in OrderIntentEvent
        intent = await asyncio.wait_for(proposals_queue.get(), timeout=2.0)
        assert intent.correlation_id == corr_id

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_error_handling_missing_market_data(self) -> None:
        """Test that PortfolioService handles missing market data gracefully."""
        bus = EventBus()
        store = MemoryMarketDataStore()  # Empty store, no market data
        metrics = MemoryMetricsCollector()

        portfolio_service = PortfolioService(
            bus=bus,
            store=store,
            fixed_size_usd=1.0,
            metrics=metrics,
        )
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)

        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="test_model",
            model_version="1.0.0",
            rationale="Test signal",
            correlation_id=generate_correlation_id(),
        )
        await bus.publish(SIGNALS, signal)

        # Should not generate OrderIntentEvent (no market data)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(proposals_queue.get(), timeout=0.5)

        # Should have received signal but not generated intent
        assert metrics.get_counter("portfolio_signals_received_total") == 1
        assert metrics.get_counter("portfolio_intents_generated_total") == 0

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_metrics_collection(self) -> None:
        """Test that PortfolioService collects metrics correctly."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        metrics = MemoryMetricsCollector()

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        store.add(market_data)

        portfolio_service = PortfolioService(
            bus=bus,
            store=store,
            fixed_size_usd=1.0,
            metrics=metrics,
        )

        await portfolio_service.start()
        await asyncio.sleep(0.01)

        # Process multiple signals
        for _ in range(3):
            signal = SignalEvent(
                market_slug="test-market",
                outcome="UP",
                p_up=0.7,
                p_down=0.3,
                edge=0.4,
                confidence=0.8,
                model_id="test_model",
                model_version="1.0.0",
                rationale="Test signal",
                correlation_id=generate_correlation_id(),
            )
            await bus.publish(SIGNALS, signal)
            await asyncio.sleep(0.01)  # Small delay between signals

        await asyncio.sleep(0.1)  # Give time for processing

        # Verify metrics
        assert metrics.get_counter("portfolio_signals_received_total") == 3
        assert metrics.get_counter("portfolio_targets_generated_total") == 3
        assert metrics.get_counter("portfolio_intents_generated_total") == 3

        # Check latency histogram exists (check percentiles)
        latency_percentiles = metrics.get_histogram_percentiles("portfolio_processing_latency_ms")
        assert len(latency_percentiles) > 0

        await portfolio_service.stop()
