"""Paper execution adapter for simulated order execution.

Per flows.mdc §8: Execution adapters are IO-only.
This adapter simulates venue responses without real API calls.

Per architecture.mdc §H: Adapters contain IO only, no business logic.
Fill simulation is deterministic based on configuration.
"""

import asyncio
import random
import uuid

from polytrader.adapters.polymarket.models import VenueError, VenueResponse
from polytrader.events import FILLS
from polytrader.events.bus import EventBus
from polytrader.events.types import FillEvent, OrderIntentEvent
from polytrader.execution.adapter import IVenueAdapter
from polytrader.execution.fill_models import (
    FillModel,
    calculate_fill_price,
    should_fill,
    should_reject,
)
from polytrader.logging_config import logger
from polytrader.store import IMarketDataStore


class PaperExecutionAdapter(IVenueAdapter):
    """Simulates order execution for paper trading.

    Per flows.mdc §8: Execution adapters are IO-only.
    This adapter simulates venue responses without real API calls.

    Per architecture.mdc §H: Adapters contain IO only, no business logic.
    Fill simulation is deterministic based on configuration.

    Implements IVenueAdapter protocol for type-safe integration with ExecutionRouter.

    Attributes:
        _bus: Event bus for publishing FillEvents
        _store: Market data store (for mid price lookup)
        _fill_model: Fill simulation model
        _fill_probability: Probability of fill (0-1)
        _rejection_probability: Probability of rejection (0-1)
        _latency_ms: Simulated latency in milliseconds
        _rng: Random number generator (for deterministic testing)
    """

    def __init__(
        self,
        bus: EventBus,
        store: IMarketDataStore,
        fill_model: FillModel = FillModel.MID_PRICE,
        fill_probability: float = 1.0,
        rejection_probability: float = 0.0,
        latency_ms: float = 50.0,
        slippage_bps: float = 10.0,
        rng: random.Random | None = None,
    ) -> None:
        """Initialize paper execution adapter.

        Args:
            bus: Event bus for publishing FillEvents
            store: Market data store (for mid price lookup)
            fill_model: How to simulate fills (default: MID_PRICE)
            fill_probability: Probability of fill (0-1, default: 1.0)
            rejection_probability: Probability of rejection (0-1, default: 0.0)
            latency_ms: Simulated latency in milliseconds (default: 50.0)
            slippage_bps: Slippage in basis points for SLIPPAGE model (default: 10.0)
            rng: Random number generator (for deterministic testing, defaults to global)
        """
        self._bus = bus
        self._store = store
        self._fill_model = fill_model
        self._fill_probability = fill_probability
        self._rejection_probability = rejection_probability
        self._latency_ms = latency_ms
        self._slippage_bps = slippage_bps
        self._rng = rng or random.Random()

        # Validate probabilities
        if not 0.0 <= fill_probability <= 1.0:
            raise ValueError(f"fill_probability must be in [0, 1], got {fill_probability}")
        if not 0.0 <= rejection_probability <= 1.0:
            raise ValueError(
                f"rejection_probability must be in [0, 1], got {rejection_probability}"
            )

    async def submit_order(
        self,
        client_order_id: str,
        intent: OrderIntentEvent,
    ) -> VenueResponse:
        """Simulate order submission.

        Per flows.mdc §9: Adapter translates internal command to venue API.
        This adapter simulates the venue response and publishes FillEvent.

        Flow:
        1. Check rejection probability (simulate venue reject)
        2. Check fill probability (simulate no fill)
        3. Calculate fill price based on fill_model
        4. Simulate latency
        5. Generate VenueResponse
        6. Publish FillEvent to bus (simulates immediate fill)
        7. Return VenueResponse

        Args:
            client_order_id: Idempotency key
            intent: Order intent with market/outcome/side/size

        Returns:
            Normalized VenueResponse (same format as ClobVenueAdapter)

        Raises:
            VenueError: If order is rejected (with error_type classification)
        """
        # 1. Check rejection probability
        if should_reject(self._rejection_probability, self._rng):
            raise VenueError(
                error_type="fatal",
                message="Simulated venue rejection",
                raw_error=ValueError("Paper trading: simulated rejection"),
            )

        # 2. Check fill probability
        if not should_fill(self._fill_probability, self._rng):
            # Return pending response (order not filled)
            return VenueResponse(
                venue_order_id=f"paper-pending-{client_order_id}",
                status="PENDING",
                raw_response={
                    "status": "PENDING",
                    "order_id": f"paper-pending-{client_order_id}",
                    "client_order_id": client_order_id,
                },
            )

        # 3. Calculate fill price
        try:
            fill_price = calculate_fill_price(
                self._fill_model,
                intent,
                self._store,
                self._slippage_bps,
            )
        except ValueError as e:
            # If fill price calculation fails, fallback to limit price
            logger.bind(
                error=str(e),
                fill_model=self._fill_model.value,
                market_slug=intent.market_slug,
            ).warning(
                "Failed to calculate fill price, using limit price: {error}",
                error=str(e),
            )
            fill_price = intent.limit_price

        # 4. Simulate latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        # 5. Generate VenueResponse
        venue_order_id = f"paper-{uuid.uuid4().hex[:8]}"
        venue_response = VenueResponse(
            venue_order_id=venue_order_id,
            status="FILLED",
            raw_response={
                "status": "FILLED",
                "order_id": venue_order_id,
                "client_order_id": client_order_id,
                "fill_price": fill_price,
            },
        )

        # 6. Publish FillEvent to bus (simulates immediate fill)
        # Note: We don't have order_id here, but OMS can match FillEvents to orders
        # by client_order_id or correlation_id. The ExecutionRouter will receive
        # the OrderAckEvent and can then publish FillEvent with the correct order_id.
        # For paper trading, we simulate immediate fills, so we publish directly.
        # The OMS will handle matching this FillEvent to the correct order.
        # TODO: Consider having ExecutionRouter publish FillEvent after ack,
        #       since it has access to order_id from the command.
        fill_event = FillEvent(
            order_id=client_order_id,  # OMS will match by client_order_id or correlation_id
            fill_id=str(uuid.uuid4()),
            size=intent.size,
            price=fill_price,
            fee=0.0,  # Paper trading: no fees
            venue_fill_id=venue_order_id,
            correlation_id=intent.correlation_id,
        )
        await self._bus.publish(FILLS, fill_event)

        logger.bind(
            client_order_id=client_order_id,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            fill_price=fill_price,
            fill_model=self._fill_model.value,
        ).info(
            "📝 Paper fill: {market_slug}/{outcome} {side} ${size:.2f} @ {fill_price:.4f} "
            "(model: {fill_model})",
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            fill_price=fill_price,
            fill_model=self._fill_model.value,
        )

        # 7. Return VenueResponse
        return venue_response

    async def cancel_order(
        self,
        client_order_id: str,
        venue_order_id: str,
    ) -> VenueResponse:
        """Simulate order cancellation.

        Per flows.mdc §9: Adapter translates internal command to venue API.
        Paper trading: cancellation always succeeds.

        Args:
            client_order_id: Idempotency key
            venue_order_id: Venue-assigned order ID

        Returns:
            Normalized VenueResponse
        """
        # Simulate latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        return VenueResponse(
            venue_order_id=venue_order_id,
            status="CANCELLED",
            raw_response={
                "status": "CANCELLED",
                "order_id": venue_order_id,
                "client_order_id": client_order_id,
            },
        )
