"""Execution adapter protocol for venue adapters.

Per architecture.mdc §H: Adapters contain IO only, no business logic.
This protocol defines the interface for both real and paper trading adapters.

Both ClobVenueAdapter and PaperExecutionAdapter (future) implement this protocol.
"""

from typing import Protocol

from polytrader.adapters.polymarket.models import VenueResponse
from polytrader.events.types import OrderIntentEvent


class IVenueAdapter(Protocol):
    """Protocol for venue adapters (real and paper).

    Per architecture.mdc §H: Adapters contain IO only.
    Both ClobVenueAdapter and PaperExecutionAdapter implement this protocol.

    This protocol ensures type safety and allows ExecutionRouter to work
    with any adapter implementation (real or simulated).
    """

    async def submit_order(
        self,
        client_order_id: str,
        intent: OrderIntentEvent,
    ) -> VenueResponse:
        """Submit order to venue (real or simulated).

        Per flows.mdc §9: Adapter translates internal command to venue API.

        Args:
            client_order_id: Idempotency key
            intent: Order intent with market/outcome/side/size

        Returns:
            Normalized venue response

        Raises:
            VenueError: If order submission fails (with error_type classification)
        """
        ...

    async def cancel_order(
        self,
        client_order_id: str,
        venue_order_id: str,
    ) -> VenueResponse:
        """Cancel order on venue (real or simulated).

        Per flows.mdc §9: Adapter translates internal command to venue API.

        Args:
            client_order_id: Idempotency key
            venue_order_id: Venue-assigned order ID

        Returns:
            Normalized venue response

        Raises:
            VenueError: If cancellation fails (with error_type classification)
        """
        ...
