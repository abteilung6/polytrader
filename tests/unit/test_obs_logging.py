"""Tests for structured logging helper utilities per observability.mdc §2, §3.

Per Commit 5: Add structured logging helper utilities.
"""

from unittest.mock import MagicMock

from polytrader.events.types import OrderIntentEvent
from polytrader.obs.logging import (
    bind_correlation_context,
    bind_order_context,
    bind_strategy_context,
)
from polytrader.oms.models import Order


class TestStructuredLoggingHelpers:
    """Tests for structured logging helper functions."""

    def test_bind_correlation_context(self) -> None:
        """Test that bind_correlation_context binds correlation_id and additional fields."""
        # Create a mock logger
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Bind correlation context
        bound_logger = bind_correlation_context(
            mock_logger,
            correlation_id="test-correlation-123",
            market_slug="btc-updown-15m",
            outcome="UP",
            event_type="SignalEvent",
        )

        # Verify bind was called with correct fields
        mock_logger.bind.assert_called_once()
        call_kwargs = mock_logger.bind.call_args[1]

        assert "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == "test-correlation-123"
        assert call_kwargs["market_slug"] == "btc-updown-15m"
        assert call_kwargs["outcome"] == "UP"
        assert call_kwargs["event_type"] == "SignalEvent"

        # Verify returned logger is the bound logger
        assert bound_logger is mock_bound_logger

    def test_bind_correlation_context_minimal(self) -> None:
        """Test that bind_correlation_context works with only correlation_id."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        bound_logger = bind_correlation_context(mock_logger, correlation_id="test-correlation-456")

        mock_logger.bind.assert_called_once()
        call_kwargs = mock_logger.bind.call_args[1]

        assert "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == "test-correlation-456"
        assert len(call_kwargs) == 1  # Only correlation_id

        assert bound_logger is mock_bound_logger

    def test_bind_order_context(self) -> None:
        """Test that bind_order_context binds all order-related fields."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create a test order
        intent = OrderIntentEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test intent",
            strategy_id="simple_threshold",
        )

        order = Order(
            order_id="order-123",
            client_order_id="client-123",
            venue_order_id="venue-123",
            intent=intent,
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            size=1.0,
            limit_price=0.45,
            correlation_id="correlation-123",
        )

        # Bind order context with additional fields
        bound_logger = bind_order_context(
            mock_logger, order, event_type="OrderSubmitted", latency_ms=5.0
        )

        # Verify bind was called with all order fields
        mock_logger.bind.assert_called_once()
        call_kwargs = mock_logger.bind.call_args[1]

        # Verify all order-related fields are present
        assert call_kwargs["correlation_id"] == "correlation-123"
        assert call_kwargs["order_id"] == "order-123"
        assert call_kwargs["client_order_id"] == "client-123"
        assert call_kwargs["venue_order_id"] == "venue-123"
        assert call_kwargs["market_slug"] == "btc-updown-15m"
        assert call_kwargs["outcome"] == "UP"
        assert call_kwargs["side"] == "BUY"

        # Verify additional fields
        assert call_kwargs["event_type"] == "OrderSubmitted"
        assert call_kwargs["latency_ms"] == 5.0

        assert bound_logger is mock_bound_logger

    def test_bind_order_context_with_none_venue_order_id(self) -> None:
        """Test that bind_order_context handles None venue_order_id correctly."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        intent = OrderIntentEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test intent",
            strategy_id="simple_threshold",
        )

        order = Order(
            order_id="order-123",
            client_order_id="client-123",
            venue_order_id=None,  # Not yet acked
            intent=intent,
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            size=1.0,
            limit_price=0.45,
            correlation_id="correlation-123",
        )

        bound_logger = bind_order_context(mock_logger, order)

        call_kwargs = mock_logger.bind.call_args[1]

        # Verify venue_order_id is None (not missing)
        assert "venue_order_id" in call_kwargs
        assert call_kwargs["venue_order_id"] is None
        assert call_kwargs["order_id"] == "order-123"
        assert call_kwargs["client_order_id"] == "client-123"

        assert bound_logger is mock_bound_logger

    def test_bind_order_context_overrides(self) -> None:
        """Test that additional kwargs override order fields."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        intent = OrderIntentEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test intent",
            strategy_id="simple_threshold",
        )

        order = Order(
            order_id="order-123",
            client_order_id="client-123",
            venue_order_id="venue-123",
            intent=intent,
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            size=1.0,
            limit_price=0.45,
            correlation_id="correlation-123",
        )

        # Override market_slug with additional kwargs
        bound_logger = bind_order_context(
            mock_logger, order, market_slug="override-market", event_type="OrderSubmitted"
        )

        call_kwargs = mock_logger.bind.call_args[1]

        # Verify override works
        assert call_kwargs["market_slug"] == "override-market"
        assert call_kwargs["event_type"] == "OrderSubmitted"
        # Other fields should still be from order
        assert call_kwargs["order_id"] == "order-123"

        assert bound_logger is mock_bound_logger

    def test_bind_strategy_context(self) -> None:
        """Test that bind_strategy_context binds strategy-related fields."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        bound_logger = bind_strategy_context(
            mock_logger,
            strategy_id="simple_threshold",
            correlation_id="correlation-123",
            market_slug="btc-updown-15m",
            event_type="StrategyEval",
            latency_ms=2.5,
        )

        mock_logger.bind.assert_called_once()
        call_kwargs = mock_logger.bind.call_args[1]

        assert call_kwargs["strategy_id"] == "simple_threshold"
        assert call_kwargs["correlation_id"] == "correlation-123"
        assert call_kwargs["market_slug"] == "btc-updown-15m"
        assert call_kwargs["event_type"] == "StrategyEval"
        assert call_kwargs["latency_ms"] == 2.5

        assert bound_logger is mock_bound_logger

    def test_bind_strategy_context_without_correlation_id(self) -> None:
        """Test that bind_strategy_context works without correlation_id."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        bound_logger = bind_strategy_context(
            mock_logger,
            strategy_id="simple_threshold",
            market_slug="btc-updown-15m",
            event_type="StrategyEval",
        )

        call_kwargs = mock_logger.bind.call_args[1]

        assert call_kwargs["strategy_id"] == "simple_threshold"
        assert "correlation_id" not in call_kwargs  # Not provided
        assert call_kwargs["market_slug"] == "btc-updown-15m"
        assert call_kwargs["event_type"] == "StrategyEval"

        assert bound_logger is mock_bound_logger

    def test_bind_strategy_context_minimal(self) -> None:
        """Test that bind_strategy_context works with only strategy_id."""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        bound_logger = bind_strategy_context(mock_logger, strategy_id="simple_threshold")

        call_kwargs = mock_logger.bind.call_args[1]

        assert call_kwargs["strategy_id"] == "simple_threshold"
        assert len(call_kwargs) == 1  # Only strategy_id

        assert bound_logger is mock_bound_logger

    def test_logging_helpers_integration(self) -> None:
        """Test that helpers work with real logger (integration test)."""
        # Use real logger to verify helpers work correctly
        from polytrader.logging_config import logger

        # Test bind_correlation_context
        log_ctx1 = bind_correlation_context(
            logger,
            correlation_id="test-123",
            market_slug="btc-updown-15m",
            event_type="TestEvent",
        )
        # Should not raise, and should return a bound logger
        assert log_ctx1 is not None

        # Test bind_strategy_context
        log_ctx2 = bind_strategy_context(
            logger,
            strategy_id="simple_threshold",
            correlation_id="test-456",
            latency_ms=1.0,
        )
        assert log_ctx2 is not None

        # Test bind_order_context with a real order
        intent = OrderIntentEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test intent",
            strategy_id="simple_threshold",
        )

        order = Order(
            order_id="order-test",
            client_order_id="client-test",
            venue_order_id=None,
            intent=intent,
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            size=1.0,
            limit_price=0.45,
            correlation_id="correlation-test",
        )

        log_ctx3 = bind_order_context(logger, order, event_type="OrderCreated")
        assert log_ctx3 is not None
