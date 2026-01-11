"""Tests for PortfolioService."""

import asyncio

import pytest

from polytrader.common.ids import generate_correlation_id
from polytrader.events import PROPOSALS, SIGNALS, TARGETS, EventBus
from polytrader.events.types import MarketDataEvent, OrderIntentEvent, SignalEvent, TargetEvent
from polytrader.portfolio.service import PortfolioService
from polytrader.position_manager import IPositionManager
from polytrader.store import MemoryMarketDataStore
from polytrader.types import Outcome, Position


class FakePositionManager(IPositionManager):
    """Fake position manager for testing."""

    def __init__(self, positions: dict[tuple[str, str], Position] | None = None) -> None:
        self._positions = positions or {}

    def get_positions(self) -> dict[tuple[str, Outcome], Position] | None:
        """Return positions."""
        # Convert keys from (str, str) to (str, Outcome) for protocol compliance
        from polytrader.types import Outcome

        result: dict[tuple[str, Outcome], Position] = {}
        for (market_slug, outcome_str), position in self._positions.items():
            outcome: Outcome = outcome_str  # type: ignore[assignment]
            result[(market_slug, outcome)] = position
        return result if result else None

    async def run(self) -> None:
        """Not used in tests."""
        pass

    def stop(self) -> None:
        """Not used in tests."""
        pass


class TestPortfolioService:
    """Tests for PortfolioService."""

    @pytest.mark.asyncio
    async def test_portfolio_service_converts_signal_to_intent(self) -> None:
        """Test complete flow: SignalEvent → Target → OrderIntentEvent."""
        bus = EventBus()
        store = MemoryMarketDataStore()

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
        )

        # Subscribe to PROPOSALS to capture OrderIntentEvent
        proposals_queue = bus.subscribe(PROPOSALS)

        # Start service
        await portfolio_service.start()
        # Give service time to subscribe
        await asyncio.sleep(0.01)

        # Create and publish SignalEvent
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
        intent = await asyncio.wait_for(proposals_queue.get(), timeout=1.0)

        assert intent is not None
        assert isinstance(intent, OrderIntentEvent)
        assert intent.market_slug == "test-market"
        assert intent.outcome == "UP"
        assert intent.side == "BUY"
        assert intent.size == 1.0
        assert intent.correlation_id == signal.correlation_id

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_publishes_to_proposals(self) -> None:
        """Test that OrderIntentEvent is published to PROPOSALS topic."""
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

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

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

        intent = await asyncio.wait_for(proposals_queue.get(), timeout=1.0)
        assert intent is not None
        assert isinstance(intent, OrderIntentEvent)

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_handles_no_target(self) -> None:
        """Test that service handles signals that don't generate targets."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()

        # Signal with no edge/confidence (should not generate target)
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.5,
            p_down=0.5,
            edge=0.0,  # No edge
            confidence=0.0,  # No confidence
            model_id="test_model",
            model_version="1.0.0",
            rationale="No edge signal",
            correlation_id=generate_correlation_id(),
        )
        await bus.publish(SIGNALS, signal)

        # Should not generate OrderIntentEvent
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(proposals_queue.get(), timeout=0.5)

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_portfolio_aware_sizing(self) -> None:
        """Test that sizing accounts for existing positions."""
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

        # Create position manager with existing position
        existing_position = Position(
            market_slug="test-market",
            outcome="UP",
            size=0.5,  # Already have 0.5
            target_price=0.60,
            entry_price=0.30,
            entry_time=1000.0,
        )
        position_manager = FakePositionManager(positions={("test-market", "UP"): existing_position})

        portfolio_service = PortfolioService(
            bus=bus,
            store=store,
            position_manager=position_manager,
            fixed_size_usd=1.0,  # Target is 1.0, but already have 0.5
        )
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

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

        intent = await asyncio.wait_for(proposals_queue.get(), timeout=1.0)

        # Size should be 1.0 - 0.5 = 0.5 (portfolio-aware)
        assert intent.size == 0.5

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_no_market_data(self) -> None:
        """Test that service handles missing market data gracefully."""
        bus = EventBus()
        store = MemoryMarketDataStore()  # Empty store, no market data

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

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

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_correlation_id_propagation(self) -> None:
        """Test that correlation_id propagates through the pipeline."""
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
        proposals_queue = bus.subscribe(PROPOSALS)
        targets_queue = bus.subscribe(TARGETS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

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

        # Check TargetEvent correlation_id (may arrive before or after OrderIntentEvent)
        target_event = await asyncio.wait_for(targets_queue.get(), timeout=2.0)
        assert target_event.correlation_id == corr_id

        # Check OrderIntentEvent correlation_id
        intent = await asyncio.wait_for(proposals_queue.get(), timeout=2.0)
        assert intent.correlation_id == corr_id

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_publishes_target_event(self) -> None:
        """Test that TargetEvent is published to TARGETS topic."""
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

        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

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

        target_event = await asyncio.wait_for(targets_queue.get(), timeout=1.0)
        assert target_event is not None
        assert isinstance(target_event, TargetEvent)
        assert target_event.market_slug == "test-market"
        assert target_event.outcome == "UP"
        assert target_event.target_exposure == 1.0

        await portfolio_service.stop()

    @pytest.mark.asyncio
    async def test_portfolio_service_no_size_needed(self) -> None:
        """Test that service handles case where target is already met."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        store.add(market_data)

        # Position already meets target (1.0)
        existing_position = Position(
            market_slug="test-market",
            outcome="UP",
            size=1.0,  # Already have full target
            target_price=0.60,
            entry_price=0.30,
            entry_time=1000.0,
        )
        position_manager = FakePositionManager(positions={("test-market", "UP"): existing_position})

        portfolio_service = PortfolioService(
            bus=bus,
            store=store,
            position_manager=position_manager,
            fixed_size_usd=1.0,
        )
        proposals_queue = bus.subscribe(PROPOSALS)

        await portfolio_service.start()
        await asyncio.sleep(0.01)  # Give service time to subscribe

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

        # Should not generate OrderIntentEvent (size = 0)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(proposals_queue.get(), timeout=0.5)

        await portfolio_service.stop()
