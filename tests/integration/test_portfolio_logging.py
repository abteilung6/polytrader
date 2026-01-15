"""Integration tests for structured logging in portfolio service.

Per Commit 9: Enforce structured logging in portfolio and strategy layers.
Per observability.mdc §2: Every log line must include correlation_id when applicable.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.portfolio.service import PortfolioService
from polytrader.store import MemoryMarketDataStore


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def store() -> MemoryMarketDataStore:
    """Create a market data store for testing."""
    return MemoryMarketDataStore()


@pytest.fixture
def portfolio_service(bus: EventBus, store: MemoryMarketDataStore) -> PortfolioService:
    """Create a portfolio service for testing."""
    return PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)


@pytest.fixture
def sample_signal() -> SignalEvent:
    """Create a sample signal for testing."""
    return SignalEvent(
        market_slug="test-market",
        outcome="UP",
        p_up=0.7,
        p_down=0.3,
        edge=0.2,
        confidence=0.8,
        model_id="simple_threshold",
        model_version="1.0.0",
        rationale="Test signal",
    )


@pytest.fixture
def sample_market_data() -> MarketDataEvent:
    """Create sample market data for testing."""
    return MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        mid=0.45,
        best_bid=0.44,
        best_ask=0.46,
        spread=0.02,
        sequence=1,
    )


class TestPortfolioStructuredLogging:
    """Tests for structured logging with correlation_id in portfolio service."""

    @pytest.mark.asyncio
    @patch("polytrader.portfolio.service.logger")
    async def test_process_signal_logs_correlation_id_on_success(
        self,
        mock_logger: MagicMock,
        bus: EventBus,
        store: MemoryMarketDataStore,
        sample_signal: SignalEvent,
        sample_market_data: MarketDataEvent,
    ) -> None:
        """Test that successful signal processing logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Add market data to store
        store.add(sample_market_data)

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        # Process signal
        await portfolio_service._process_signal(sample_signal)

        # Verify bind_strategy_context was called for success log
        assert mock_logger.bind.called

        # Find the PortfolioIntentPublished log call
        success_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "PortfolioIntentPublished":
                success_call = kwargs
                break

        assert success_call is not None, "PortfolioIntentPublished log not found"

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in success_call
        assert success_call["correlation_id"] == sample_signal.correlation_id
        assert "strategy_id" in success_call
        assert success_call["strategy_id"] == "simple_threshold"
        assert "market_slug" in success_call
        assert success_call["market_slug"] == "test-market"
        assert "outcome" in success_call
        assert "event_type" in success_call
        assert success_call["event_type"] == "PortfolioIntentPublished"
        assert "latency_ms" in success_call

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.portfolio.service.logger")
    async def test_process_signal_logs_correlation_id_no_target(
        self,
        mock_logger: MagicMock,
        bus: EventBus,
        store: MemoryMarketDataStore,
    ) -> None:
        """Test that no target logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create signal with edge <= 0 (will not generate target)
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.5,
            p_down=0.5,
            edge=0.0,  # No edge, won't generate target
            confidence=0.5,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        # Process signal
        await portfolio_service._process_signal(signal)

        # Verify bind_strategy_context was called for no target log
        assert mock_logger.bind.called

        # Find the PortfolioNoTarget log call
        no_target_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "PortfolioNoTarget":
                no_target_call = kwargs
                break

        assert no_target_call is not None, "PortfolioNoTarget log not found"

        # Verify required fields
        assert "correlation_id" in no_target_call
        assert no_target_call["correlation_id"] == signal.correlation_id
        assert "strategy_id" in no_target_call
        assert "event_type" in no_target_call
        assert no_target_call["event_type"] == "PortfolioNoTarget"
        assert "latency_ms" in no_target_call

        # Verify debug was called
        mock_bound_logger.debug.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.portfolio.service.logger")
    async def test_process_signal_logs_correlation_id_no_market_data(
        self,
        mock_logger: MagicMock,
        bus: EventBus,
        store: MemoryMarketDataStore,
        sample_signal: SignalEvent,
    ) -> None:
        """Test that no market data warning logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Don't add market data to store (will trigger warning)
        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        # Process signal
        await portfolio_service._process_signal(sample_signal)

        # Verify bind_strategy_context was called for no market data log
        assert mock_logger.bind.called

        # Find the PortfolioNoMarketData log call
        no_md_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "PortfolioNoMarketData":
                no_md_call = kwargs
                break

        assert no_md_call is not None, "PortfolioNoMarketData log not found"

        # Verify required fields
        assert "correlation_id" in no_md_call
        assert no_md_call["correlation_id"] == sample_signal.correlation_id
        assert "strategy_id" in no_md_call
        assert "market_slug" in no_md_call
        assert "event_type" in no_md_call
        assert no_md_call["event_type"] == "PortfolioNoMarketData"
        assert "error_class" in no_md_call
        assert "latency_ms" in no_md_call

        # Verify warning was called
        mock_bound_logger.warning.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.portfolio.service.logger")
    @patch("polytrader.portfolio.service.convert_signal_to_target")
    async def test_process_signal_logs_correlation_id_on_error(
        self,
        mock_convert_signal: MagicMock,
        mock_logger: MagicMock,
        bus: EventBus,
        store: MemoryMarketDataStore,
        sample_signal: SignalEvent,
    ) -> None:
        """Test that error logs include correlation_id and error_class."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Make convert_signal_to_target raise an error
        mock_convert_signal.side_effect = RuntimeError("Conversion error")

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        # Process signal (will raise error)
        await portfolio_service._process_signal(sample_signal)

        # Verify bind_strategy_context was called for error log
        assert mock_logger.bind.called

        # Find the PortfolioProcessingError log call
        error_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "PortfolioProcessingError":
                error_call = kwargs
                break

        assert error_call is not None, "PortfolioProcessingError log not found"

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in error_call
        assert error_call["correlation_id"] == sample_signal.correlation_id
        assert "strategy_id" in error_call
        assert "market_slug" in error_call
        assert "event_type" in error_call
        assert error_call["event_type"] == "PortfolioProcessingError"
        assert "error_class" in error_call
        assert "latency_ms" in error_call

        # Verify exception was called
        mock_bound_logger.exception.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.portfolio.service.logger")
    async def test_portfolio_service_start_stop_logs(
        self,
        mock_logger: MagicMock,
        bus: EventBus,
        store: MemoryMarketDataStore,
    ) -> None:
        """Test that start/stop logs include event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        # Start service
        await portfolio_service.start()
        await asyncio.sleep(0.05)  # Give it time to start

        # Stop service
        await portfolio_service.stop()

        # Verify bind_strategy_context was called for start/stop logs
        assert mock_logger.bind.called

        # Find the PortfolioServiceStarted log call
        started_call = None
        stopped_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "PortfolioServiceStarted":
                started_call = kwargs
            elif kwargs.get("event_type") == "PortfolioServiceStopped":
                stopped_call = kwargs

        assert started_call is not None, "PortfolioServiceStarted log not found"
        assert stopped_call is not None, "PortfolioServiceStopped log not found"

        # Verify required fields
        assert "strategy_id" in started_call
        assert started_call["strategy_id"] == "portfolio_service"
        assert "event_type" in started_call
        assert started_call["event_type"] == "PortfolioServiceStarted"

        assert "strategy_id" in stopped_call
        assert stopped_call["strategy_id"] == "portfolio_service"
        assert "event_type" in stopped_call
        assert stopped_call["event_type"] == "PortfolioServiceStopped"

        # Verify info was called
        mock_bound_logger.info.assert_called()
