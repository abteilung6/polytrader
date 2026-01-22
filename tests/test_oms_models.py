"""Tests for OMS models: Order, Fill, OrderState."""

import time

import pytest
from pydantic import ValidationError

from polytrader.events.types import OrderIntentEvent
from polytrader.oms.models import Fill, Order, OrderState
from polytrader.types import Outcome, Side


def create_test_intent(
    market_slug: str = "test-market",
    outcome: Outcome = "UP",
    side: Side = "BUY",
    size: float = 10.0,
    limit_price: float = 0.5,
    strategy_id: str = "simple_threshold",
) -> OrderIntentEvent:
    """Create a test OrderIntentEvent."""
    return OrderIntentEvent(
        market_slug=market_slug,
        outcome=outcome,
        side=side,
        target_price=0.6,
        limit_price=limit_price,
        size=size,
        reason="Test intent",
        strategy_id=strategy_id,
    )


class TestOrderState:
    """Tests for OrderState enum."""

    def test_order_state_values(self) -> None:
        """Test that all expected states exist."""
        assert OrderState.NEW == "NEW"
        assert OrderState.PENDING_SUBMIT == "PENDING_SUBMIT"
        assert OrderState.SUBMITTED == "SUBMITTED"
        assert OrderState.ACKED == "ACKED"
        assert OrderState.PARTIALLY_FILLED == "PARTIALLY_FILLED"
        assert OrderState.FILLED == "FILLED"
        assert OrderState.CANCELLED == "CANCELLED"
        assert OrderState.REJECTED == "REJECTED"

    def test_order_state_string_representation(self) -> None:
        """Test that states can be used as strings."""
        # For str, Enum, .value gives the string value
        assert OrderState.NEW.value == "NEW"
        # str() returns the enum name representation, not the value
        # But the enum member itself can be used as a string in comparisons
        assert OrderState.NEW == "NEW"  # Direct comparison works for str, Enum


class TestOrder:
    """Tests for Order model."""

    def test_order_creation_minimal(self) -> None:
        """Test creating an order with minimal required fields."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.order_id is not None
        assert order.client_order_id == "test-client-id"
        assert order.state == OrderState.NEW
        assert order.venue_order_id is None
        assert order.filled_size == 0.0
        assert order.avg_fill_price is None
        assert order.reject_reason is None
        assert order.correlation_id == intent.correlation_id

    def test_order_creation_with_defaults(self) -> None:
        """Test that defaults are applied correctly."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.created_at > 0
        assert order.updated_at > 0
        assert order.updated_at >= order.created_at

    def test_order_validation_size_positive(self) -> None:
        """Test that size must be positive."""
        intent = create_test_intent()
        with pytest.raises(ValidationError) as exc_info:
            Order(
                client_order_id="test-client-id",
                intent=intent,
                market_slug=intent.market_slug,
                outcome=intent.outcome,
                side=intent.side,
                size=-1.0,  # Invalid
                limit_price=intent.limit_price,
                correlation_id=intent.correlation_id,
            )
        assert "greater than 0" in str(exc_info.value).lower()

    def test_order_validation_limit_price_range(self) -> None:
        """Test that limit_price must be in 0-1 range."""
        intent = create_test_intent()
        with pytest.raises(ValidationError) as exc_info:
            Order(
                client_order_id="test-client-id",
                intent=intent,
                market_slug=intent.market_slug,
                outcome=intent.outcome,
                side=intent.side,
                size=intent.size,
                limit_price=1.5,  # Invalid (> 1)
                correlation_id=intent.correlation_id,
            )
        assert "less than or equal to 1" in str(exc_info.value).lower()

    def test_order_remaining_size(self) -> None:
        """Test remaining_size property."""
        intent = create_test_intent(size=10.0)
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=10.0,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.remaining_size == 10.0

        order.filled_size = 3.0
        assert order.remaining_size == 7.0

        order.filled_size = 10.0
        assert order.remaining_size == 0.0

    def test_order_fill_percentage(self) -> None:
        """Test fill_percentage property."""
        intent = create_test_intent(size=10.0)
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=10.0,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.fill_percentage == 0.0

        order.filled_size = 5.0
        assert order.fill_percentage == 0.5

        order.filled_size = 10.0
        assert order.fill_percentage == 1.0

    def test_order_fill_percentage_zero_size(self) -> None:
        """Test fill_percentage with zero size (edge case)."""
        intent = create_test_intent(size=0.01)  # Small but valid
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=0.01,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )
        # Should not crash
        assert order.fill_percentage >= 0.0

    def test_order_is_terminal(self) -> None:
        """Test is_terminal property."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert not order.is_terminal  # NEW is not terminal

        order.state = OrderState.FILLED
        assert order.is_terminal

        order.state = OrderState.CANCELLED
        assert order.is_terminal

        order.state = OrderState.REJECTED
        assert order.is_terminal

        order.state = OrderState.ACKED
        assert not order.is_terminal

    def test_order_is_open(self) -> None:
        """Test is_open property."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.is_open  # NEW is open

        order.state = OrderState.FILLED
        assert not order.is_open

        order.state = OrderState.ACKED
        assert order.is_open

    def test_order_venue_order_id_update(self) -> None:
        """Test that venue_order_id can be updated."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.venue_order_id is None

        order.venue_order_id = "venue-123"
        assert order.venue_order_id == "venue-123"

    def test_order_filled_size_update(self) -> None:
        """Test that filled_size can be updated."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.filled_size == 0.0

        order.filled_size = 5.0
        assert order.filled_size == 5.0

    def test_order_avg_fill_price_update(self) -> None:
        """Test that avg_fill_price can be updated."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.avg_fill_price is None

        order.avg_fill_price = 0.55
        assert order.avg_fill_price == 0.55

    def test_order_reject_reason(self) -> None:
        """Test reject_reason field."""
        intent = create_test_intent()
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        assert order.reject_reason is None

        order.reject_reason = "Insufficient balance"
        assert order.reject_reason == "Insufficient balance"


class TestFill:
    """Tests for Fill model."""

    def test_fill_creation_minimal(self) -> None:
        """Test creating a fill with minimal required fields."""
        fill = Fill(
            order_id="order-123",
            size=5.0,
            price=0.55,
            fee=0.1,
            correlation_id="corr-123",
        )

        assert fill.fill_id is not None
        assert fill.order_id == "order-123"
        assert fill.size == 5.0
        assert fill.price == 0.55
        assert fill.fee == 0.1
        assert fill.venue_fill_id is None
        assert fill.correlation_id == "corr-123"
        assert fill.filled_at > 0

    def test_fill_creation_with_venue_id(self) -> None:
        """Test creating a fill with venue_fill_id."""
        fill = Fill(
            order_id="order-123",
            size=5.0,
            price=0.55,
            fee=0.1,
            venue_fill_id="venue-fill-456",
            correlation_id="corr-123",
        )

        assert fill.venue_fill_id == "venue-fill-456"

    def test_fill_validation_size_positive(self) -> None:
        """Test that size must be positive."""
        with pytest.raises(ValidationError) as exc_info:
            Fill(
                order_id="order-123",
                size=-1.0,  # Invalid
                price=0.55,
                fee=0.1,
                correlation_id="corr-123",
            )
        assert "greater than 0" in str(exc_info.value).lower()

    def test_fill_validation_price_range(self) -> None:
        """Test that price must be in 0-1 range."""
        with pytest.raises(ValidationError) as exc_info:
            Fill(
                order_id="order-123",
                size=5.0,
                price=1.5,  # Invalid (> 1)
                fee=0.1,
                correlation_id="corr-123",
            )
        assert "less than or equal to 1" in str(exc_info.value).lower()

    def test_fill_validation_fee_non_negative(self) -> None:
        """Test that fee must be non-negative."""
        with pytest.raises(ValidationError) as exc_info:
            Fill(
                order_id="order-123",
                size=5.0,
                price=0.55,
                fee=-0.1,  # Invalid
                correlation_id="corr-123",
            )
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_fill_net_proceeds(self) -> None:
        """Test net_proceeds property."""
        fill = Fill(
            order_id="order-123",
            size=10.0,
            price=0.55,
            fee=0.2,
            correlation_id="corr-123",
        )

        assert fill.net_proceeds == 9.8

        fill = Fill(
            order_id="order-123",
            size=5.0,
            price=0.55,
            fee=0.0,  # No fee
            correlation_id="corr-123",
        )

        assert fill.net_proceeds == 5.0

    def test_fill_immutability(self) -> None:
        """Test that fills are immutable (frozen)."""
        fill = Fill(
            order_id="order-123",
            size=5.0,
            price=0.55,
            fee=0.1,
            correlation_id="corr-123",
        )

        # Fills are frozen, so assignment should raise an error
        # Note: Pydantic frozen models raise ValidationError on assignment
        with pytest.raises(ValidationError):
            fill.size = 10.0  # type: ignore[misc]

    def test_fill_timestamp(self) -> None:
        """Test that filled_at is set correctly."""
        before = time.monotonic()
        fill = Fill(
            order_id="order-123",
            size=5.0,
            price=0.55,
            fee=0.1,
            correlation_id="corr-123",
        )
        after = time.monotonic()

        assert before <= fill.filled_at <= after


class TestOrderFillIntegration:
    """Tests for Order and Fill integration."""

    def test_order_with_multiple_fills(self) -> None:
        """Test updating order with multiple fills."""
        intent = create_test_intent(size=10.0)
        order = Order(
            client_order_id="test-client-id",
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=10.0,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
        )

        # First fill
        fill1 = Fill(
            order_id=order.order_id,
            size=3.0,
            price=0.55,
            fee=0.05,
            correlation_id=order.correlation_id,
        )
        order.filled_size += fill1.size
        order.avg_fill_price = fill1.price

        assert order.filled_size == 3.0
        assert order.remaining_size == 7.0
        assert order.fill_percentage == 0.3

        # Second fill
        fill2 = Fill(
            order_id=order.order_id,
            size=4.0,
            price=0.56,
            fee=0.06,
            correlation_id=order.correlation_id,
        )
        order.filled_size += fill2.size
        # Update average: weighted average
        total_value = (fill1.size * fill1.price) + (fill2.size * fill2.price)
        total_size = fill1.size + fill2.size
        order.avg_fill_price = total_value / total_size

        assert order.filled_size == 7.0
        assert order.remaining_size == 3.0
        assert order.fill_percentage == 0.7
        assert abs(order.avg_fill_price - 0.5557) < 0.001  # Weighted average

        # Final fill
        fill3 = Fill(
            order_id=order.order_id,
            size=3.0,
            price=0.57,
            fee=0.05,
            correlation_id=order.correlation_id,
        )
        order.filled_size += fill3.size
        total_value = (
            (fill1.size * fill1.price) + (fill2.size * fill2.price) + (fill3.size * fill3.price)
        )
        total_size = fill1.size + fill2.size + fill3.size
        order.avg_fill_price = total_value / total_size
        order.state = OrderState.FILLED

        assert order.filled_size == 10.0
        assert order.remaining_size == 0.0
        assert order.fill_percentage == 1.0
        assert order.is_terminal
        assert not order.is_open
