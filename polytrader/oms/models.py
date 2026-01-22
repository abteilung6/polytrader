"""OMS models: Order, Fill, and OrderState enum.

Per flows.mdc §7: Orders have explicit finite state machine.
Per architecture.mdc §D: OMS owns all order state.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from polytrader.events.types import OrderIntentEvent
from polytrader.types import Outcome, Side

if TYPE_CHECKING:
    pass  # Forward references handled by string annotations


class OrderState(str, Enum):
    """Order state enum per flows.mdc §7.

    States represent the lifecycle of an order from creation to terminal state.
    All state transitions must be validated via FSM (see oms/fsm.py).

    State Flow:
        NEW → PENDING_SUBMIT → SUBMITTED → ACKED → (PARTIALLY_FILLED) → FILLED
        NEW → PENDING_SUBMIT → SUBMITTED → REJECTED
        NEW → PENDING_SUBMIT → CANCELLED
        ACKED → CANCELLED
        PARTIALLY_FILLED → CANCELLED
    """

    NEW = "NEW"  # Initial state after order creation
    PENDING_SUBMIT = "PENDING_SUBMIT"  # Ready to submit to execution layer
    SUBMITTED = "SUBMITTED"  # Sent to execution layer
    ACKED = "ACKED"  # Acknowledged by venue
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Partially filled
    FILLED = "FILLED"  # Fully filled (terminal)
    CANCELLED = "CANCELLED"  # Cancelled (terminal)
    REJECTED = "REJECTED"  # Rejected by venue (terminal)


class Order(BaseModel):
    """Order model representing an order in the OMS.

    Per flows.mdc §7: OMS owns all order state. This model is the
    authoritative representation of an order's lifecycle.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key (deterministic from intent)
        venue_order_id: Venue-assigned order ID (None until acked)
        state: Current order state (see OrderState enum)
        intent: Original approved order intent
        market_slug: Market identifier
        outcome: Market outcome ("UP" or "DOWN")
        side: Trade side ("BUY" or "SELL")
        size: Order size in USD
        limit_price: Limit price for the order
        filled_size: Cumulative filled size in USD
        avg_fill_price: Average fill price (None until first fill)
        created_at: Monotonic timestamp when order was created
        updated_at: Monotonic timestamp when order was last updated
        reject_reason: Rejection reason (None unless REJECTED)
        correlation_id: Correlation ID from intent (for tracing)
    """

    order_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Internal UUID for the order",
    )
    client_order_id: str = Field(description="Idempotency key (deterministic from intent)")
    venue_order_id: str | None = Field(
        default=None,
        description="Venue-assigned order ID (None until acked)",
    )
    state: OrderState = Field(
        default=OrderState.NEW,
        description="Current order state",
    )
    intent: OrderIntentEvent = Field(description="Original approved order intent")
    market_slug: str = Field(description="Market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")
    side: Side = Field(description="Trade side: BUY or SELL")
    size: float = Field(gt=0, description="Order size in USD")
    limit_price: float = Field(gt=0, le=1, description="Limit price for the order (0-1 range)")
    filled_size: float = Field(
        default=0.0,
        ge=0,
        description="Cumulative filled size in USD",
    )
    avg_fill_price: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Average fill price (None until first fill)",
    )
    created_at: float = Field(
        default_factory=time.monotonic,
        description="Monotonic timestamp when order was created",
    )
    updated_at: float = Field(
        default_factory=time.monotonic,
        description="Monotonic timestamp when order was last updated",
    )
    reject_reason: str | None = Field(
        default=None,
        description="Rejection reason (None unless REJECTED)",
    )
    correlation_id: str = Field(description="Correlation ID from intent (for tracing)")
    strategy_id: str | None = Field(
        default=None,
        description=(
            "Strategy identifier (derived from intent.strategy_id, optional for convenience)"
        ),
    )

    @property
    def remaining_size(self) -> float:
        """Remaining unfilled size in USD.

        Returns:
            Remaining size (size - filled_size)
        """
        return self.size - self.filled_size

    @property
    def fill_percentage(self) -> float:
        """Fill percentage (0.0 to 1.0).

        Returns:
            Fill percentage (filled_size / size)
        """
        if self.size == 0:
            return 0.0
        return self.filled_size / self.size

    @property
    def is_terminal(self) -> bool:
        """Check if order is in a terminal state.

        Terminal states: FILLED, CANCELLED, REJECTED

        Returns:
            True if order is in terminal state
        """
        return self.state in (
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
        )

    @property
    def is_open(self) -> bool:
        """Check if order is open (not terminal).

        Returns:
            True if order is not in terminal state
        """
        return not self.is_terminal

    model_config = {
        "frozen": False,  # Orders are mutable (state transitions)
        "validate_assignment": True,
    }


class Fill(BaseModel):
    """Fill model representing a single fill event.

    Per flows.mdc §10: Fills update order state and emit FillEvent.
    Multiple fills can occur for a single order (partial fills).

    Attributes:
        fill_id: Internal UUID for the fill
        order_id: Parent order ID
        venue_fill_id: Venue-assigned fill ID (None if not available)
        size: Fill quantity in USD
        price: Fill price (0-1 range)
        fee: Fee amount in USD
        filled_at: Monotonic timestamp when fill occurred
        correlation_id: Correlation ID from parent order (for tracing)
    """

    fill_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Internal UUID for the fill",
    )
    order_id: str = Field(description="Parent order ID")
    venue_fill_id: str | None = Field(
        default=None,
        description="Venue-assigned fill ID (None if not available)",
    )
    size: float = Field(gt=0, description="Fill quantity in USD")
    price: float = Field(gt=0, le=1, description="Fill price (0-1 range)")
    fee: float = Field(
        ge=0,
        description="Fee amount in USD",
    )
    filled_at: float = Field(
        default_factory=time.monotonic,
        description="Monotonic timestamp when fill occurred",
    )
    correlation_id: str = Field(description="Correlation ID from parent order (for tracing)")

    @property
    def net_proceeds(self) -> float:
        """Net proceeds from fill (size - fee).

        Returns:
            Net proceeds in USD
        """
        return self.size - self.fee

    model_config = {
        "frozen": True,  # Fills are immutable
        "validate_assignment": True,
    }
