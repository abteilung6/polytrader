"""Tests for execution adapter protocol.

Per Commit 1: Verify that adapters implement IVenueAdapter protocol correctly.
"""

from polytrader.adapters.polymarket.models import VenueResponse
from polytrader.types import OrderIntentEvent


class TestIVenueAdapterProtocol:
    """Tests for IVenueAdapter protocol compliance."""

    def test_clob_venue_adapter_implements_protocol(self) -> None:
        """Test that ClobVenueAdapter implements IVenueAdapter protocol."""
        from unittest.mock import MagicMock

        from polytrader.adapters.polymarket.trading import ClobVenueAdapter

        # Create a ClobVenueAdapter instance
        clob_client = MagicMock()
        gamma_client = MagicMock()
        adapter = ClobVenueAdapter(clob_client, gamma_client)

        # Verify it implements the protocol (structural typing)
        # This will pass if ClobVenueAdapter has the required methods
        assert hasattr(adapter, "submit_order")
        assert hasattr(adapter, "cancel_order")

        # Verify method signatures match protocol
        import inspect

        submit_sig = inspect.signature(adapter.submit_order)
        assert "client_order_id" in submit_sig.parameters
        assert "intent" in submit_sig.parameters

        cancel_sig = inspect.signature(adapter.cancel_order)
        assert "client_order_id" in cancel_sig.parameters
        assert "venue_order_id" in cancel_sig.parameters

    def test_execution_router_accepts_protocol(self) -> None:
        """Test that ExecutionRouter accepts IVenueAdapter protocol."""

        from polytrader.events import EventBus
        from polytrader.execution.router import ExecutionRouter

        # Create a mock adapter that implements the protocol
        class MockAdapter:
            async def submit_order(
                self, client_order_id: str, intent: OrderIntentEvent
            ) -> VenueResponse:
                return VenueResponse(
                    venue_order_id="mock-123",
                    status="FILLED",
                    raw_response={},
                )

            async def cancel_order(
                self, client_order_id: str, venue_order_id: str
            ) -> VenueResponse:
                return VenueResponse(
                    venue_order_id="mock-123",
                    status="CANCELLED",
                    raw_response={},
                )

        # Verify ExecutionRouter accepts it
        bus = EventBus()
        adapter = MockAdapter()
        router = ExecutionRouter(bus=bus, adapter=adapter)

        assert router._adapter is adapter

    def test_protocol_type_checking(self) -> None:
        """Test that Protocol enables type checking."""
        from unittest.mock import MagicMock

        from polytrader.events import EventBus
        from polytrader.execution.router import ExecutionRouter

        # This should type-check correctly
        bus = EventBus()

        # Create a mock that doesn't implement the protocol
        class IncompleteAdapter:
            pass

        # Type checker should catch this, but runtime won't
        # We can't test mypy here, but we can verify the structure
        incomplete = IncompleteAdapter()

        # Runtime check: verify it doesn't have required methods
        assert not hasattr(incomplete, "submit_order")
        assert not hasattr(incomplete, "cancel_order")

        # A proper adapter should work
        from polytrader.adapters.polymarket.trading import ClobVenueAdapter

        clob_client = MagicMock()
        gamma_client = MagicMock()
        proper_adapter = ClobVenueAdapter(clob_client, gamma_client)

        router = ExecutionRouter(bus=bus, adapter=proper_adapter)
        assert router._adapter is proper_adapter
