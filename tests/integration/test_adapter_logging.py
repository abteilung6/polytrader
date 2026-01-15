"""Integration tests for structured logging in adapters.

Per Commit 8: Enforce structured logging in adapters.
Per observability.mdc §2: Every log line must include correlation_id when applicable.
"""

from unittest.mock import MagicMock, patch

import pytest

from polytrader.adapters.polymarket.trading import ClobVenueAdapter
from polytrader.events.types import OrderIntentEvent


@pytest.fixture
def mock_clob_client() -> MagicMock:
    """Create a mock CLOB client for testing."""
    client = MagicMock()
    client.create_market_order = MagicMock(
        return_value={"hash": "test-hash-123", "token_id": "test-token"}
    )
    client.post_order = MagicMock(return_value={"order_id": "venue-123", "status": "acknowledged"})
    client.get_balance_allowance = MagicMock(
        return_value={"balance": "1000.0", "allowance": "auto"}
    )
    return client


@pytest.fixture
def mock_gamma_client() -> MagicMock:
    """Create a mock Gamma client for testing."""
    client = MagicMock()
    market = MagicMock()
    market.get_token_id = MagicMock(return_value="token-123")
    client.get_market_by_slug = MagicMock(return_value=market)
    return client


@pytest.fixture
def adapter(mock_clob_client: MagicMock, mock_gamma_client: MagicMock) -> ClobVenueAdapter:
    """Create a CLOB venue adapter for testing."""
    return ClobVenueAdapter(clob_client=mock_clob_client, gamma_client=mock_gamma_client)


@pytest.fixture
def sample_intent() -> OrderIntentEvent:
    """Create a sample order intent for testing."""
    return OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=100.0,
        target_price=0.55,
        limit_price=0.55,
        reason="Test intent",
        ttl_s=60.0,
    )


class TestAdapterStructuredLogging:
    """Tests for structured logging with correlation_id in adapters."""

    @pytest.mark.asyncio
    @patch("polytrader.adapters.polymarket.trading.logger")
    async def test_submit_order_logs_correlation_id_on_success(
        self,
        mock_logger: MagicMock,
        adapter: ClobVenueAdapter,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that successful submit_order logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        response = await adapter.submit_order("client-123", sample_intent)

        # Verify response
        assert response.venue_order_id == "venue-123"

        # Verify bind_correlation_context was called for success log
        assert mock_logger.bind.called

        # Find the AdapterSubmitSuccess log call
        success_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "AdapterSubmitSuccess":
                success_call = kwargs
                break

        assert success_call is not None, "AdapterSubmitSuccess log not found"

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in success_call
        assert success_call["correlation_id"] == sample_intent.correlation_id
        assert "client_order_id" in success_call
        assert success_call["client_order_id"] == "client-123"
        assert "venue_order_id" in success_call
        assert success_call["venue_order_id"] == "venue-123"
        assert "market_slug" in success_call
        assert success_call["market_slug"] == "test-market"
        assert "outcome" in success_call
        assert "side" in success_call
        assert "event_type" in success_call
        assert success_call["event_type"] == "AdapterSubmitSuccess"
        assert "latency_ms" in success_call

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.adapters.polymarket.trading.logger")
    async def test_submit_order_logs_correlation_id_on_error(
        self,
        mock_logger: MagicMock,
        adapter: ClobVenueAdapter,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that error logs include correlation_id and error_class."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Make post_order raise an error
        adapter.clob_client.post_order = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("API error")
        )

        from polytrader.adapters.polymarket.models import VenueError

        with pytest.raises(VenueError):
            await adapter.submit_order("client-123", sample_intent)

        # Verify bind_correlation_context was called for error log
        assert mock_logger.bind.called

        # Find the AdapterSubmitError log call
        error_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "AdapterSubmitError":
                error_call = kwargs
                break

        assert error_call is not None, "AdapterSubmitError log not found"

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in error_call
        assert error_call["correlation_id"] == sample_intent.correlation_id
        assert "client_order_id" in error_call
        assert "market_slug" in error_call
        assert "event_type" in error_call
        assert error_call["event_type"] == "AdapterSubmitError"
        assert "error_class" in error_call
        assert "latency_ms" in error_call

        # Verify exception was called
        mock_bound_logger.exception.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.adapters.polymarket.trading.logger")
    async def test_place_market_order_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        adapter: ClobVenueAdapter,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that _place_market_order logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        response = adapter._place_market_order(
            token_id="token-123",
            amount=100.0,
            side="BUY",
            client_order_id="client-123",
            correlation_id=sample_intent.correlation_id,
            market_slug=sample_intent.market_slug,
            outcome=sample_intent.outcome,
        )

        # Verify response
        assert response["order_id"] == "venue-123"

        # Verify bind_correlation_context was called
        assert mock_logger.bind.called

        # Find the AdapterPlaceOrder log call
        place_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "AdapterPlaceOrder":
                place_call = kwargs
                break

        assert place_call is not None, "AdapterPlaceOrder log not found"

        # Verify required fields
        assert "correlation_id" in place_call
        assert place_call["correlation_id"] == sample_intent.correlation_id
        assert "client_order_id" in place_call
        assert "market_slug" in place_call
        assert "outcome" in place_call
        assert "side" in place_call
        assert "event_type" in place_call
        assert place_call["event_type"] == "AdapterPlaceOrder"

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.adapters.polymarket.trading.logger")
    async def test_verify_balance_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        adapter: ClobVenueAdapter,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that _verify_balance logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        balance = await adapter._verify_balance(
            required_amount=100.0, correlation_id=sample_intent.correlation_id
        )

        # Verify balance
        assert balance == 1000.0

        # Verify bind_correlation_context was called
        assert mock_logger.bind.called

        # Find the AdapterBalanceCheck log call
        balance_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "AdapterBalanceCheck":
                balance_call = kwargs
                break

        assert balance_call is not None, "AdapterBalanceCheck log not found"

        # Verify required fields
        assert "correlation_id" in balance_call
        assert balance_call["correlation_id"] == sample_intent.correlation_id
        assert "event_type" in balance_call
        assert balance_call["event_type"] == "AdapterBalanceCheck"
        assert "required_amount" in balance_call
        assert "balance" in balance_call

        # Verify info was called
        mock_bound_logger.info.assert_called()
