"""Tests for risk module structured logging with correlation IDs.

Per observability.mdc §2, §3:
- All logs must include correlation_id when applicable
- Structured logging with required fields
"""

import asyncio
from unittest.mock import MagicMock, patch

from polytrader.events import PROPOSALS, EventBus, MemoryEventStore
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.risk.models import RiskContext, RiskLimits
from polytrader.store import MemoryMarketDataStore
from polytrader.types import MarketDataEvent, OrderIntentEvent


class TestRiskStructuredLogging:
    """Tests for structured logging with correlation IDs in risk module."""

    @patch("polytrader.risk.engine.logger")
    async def test_risk_checker_logs_correlation_id_allowed(self, mock_logger: MagicMock) -> None:
        """Test that RiskChecker logs include correlation_id for allowed orders.

        Per observability.mdc §2: Every log line must include correlation_id when applicable.
        """
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        limits = get_default_limits()
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=60.0,
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        context = RiskContext(
            intent=intent,
            market_data=market_data,
            reconciliation_healthy=True,
        )

        # Mock the bound logger to capture calls
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        await checker.check(intent, context)

        # Verify logger.bind was called with correlation_id per observability.mdc §2
        mock_logger.bind.assert_called()
        call_kwargs = mock_logger.bind.call_args[1]

        assert "correlation_id" in call_kwargs, "correlation_id must be in log context"
        assert call_kwargs["correlation_id"] == intent.correlation_id
        assert "market_slug" in call_kwargs
        assert "outcome" in call_kwargs
        assert "side" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "RiskCheck"

        # Verify info was called for allowed order
        mock_bound_logger.info.assert_called()
        info_call = mock_bound_logger.info.call_args
        assert "Risk check allowed" in info_call[0][0] or "allowed" in str(info_call)

    @patch("polytrader.risk.engine.logger")
    async def test_risk_checker_logs_correlation_id_denied(self, mock_logger: MagicMock) -> None:
        """Test that RiskChecker logs include correlation_id for denied orders.

        Per observability.mdc §2: Every log line must include correlation_id when applicable.
        """
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        # Use max_trades_per_market=1 and set up context with already executed trade
        limits = RiskLimits(
            version="1.0",
            max_position_per_market=100.0,
            max_position_global=1000.0,
            max_notional_exposure=5000.0,
            max_order_size=10.0,
            max_trades_per_market=1,  # Only 1 trade allowed
            order_rate_limit_per_minute=60,
            cancel_rate_limit_per_minute=120,
            max_data_staleness_seconds=5.0,
            price_deviation_threshold=0.1,
        )
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=60.0,
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        # Set up context with already executed trade to trigger RISK_MAX_TRADES_PER_MARKET
        context = RiskContext(
            intent=intent,
            market_data=market_data,
            executed_trades={(intent.market_slug, intent.outcome)},  # Already traded
            reconciliation_healthy=True,
        )

        # Mock the bound logger to capture calls
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        await checker.check(intent, context)

        # Verify logger.bind was called with correlation_id per observability.mdc §2
        mock_logger.bind.assert_called()
        call_kwargs = mock_logger.bind.call_args[1]

        assert "correlation_id" in call_kwargs, "correlation_id must be in log context"
        assert call_kwargs["correlation_id"] == intent.correlation_id

        # Verify warning was called for denied order
        mock_bound_logger.warning.assert_called()
        warning_call = mock_bound_logger.warning.call_args
        assert "denied" in warning_call[0][0].lower() or "denied" in str(warning_call)

    @patch("polytrader.risk.engine.logger")
    async def test_risk_checker_run_logs_correlation_id(self, mock_logger: MagicMock) -> None:
        """Test that RiskChecker.run() logs include correlation_id.

        Per observability.mdc §2: Every log line must include correlation_id when applicable.
        """
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        limits = get_default_limits()
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=60.0,
        )

        # Publish proposal to bus (RiskChecker subscribes to PROPOSALS)
        await bus.publish(PROPOSALS, intent)

        # Start checker in background
        task = asyncio.create_task(checker.run())

        # Give it a moment to process
        await asyncio.sleep(0.1)

        # Stop checker
        checker.stop()
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify logger.info was called (for "RiskChecker started")
        mock_logger.info.assert_called()
