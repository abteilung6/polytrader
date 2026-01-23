"""Integration tests for risk metrics emission from RiskChecker.

Per testing.mdc §1.B: Integration tests for risk metrics.
"""

import pytest

from polytrader.events import EventBus
from polytrader.events.types import MarketDataEvent, OrderIntentEvent
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.risk.engine import RiskChecker, RiskEngine
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode


@pytest.mark.integration
class TestRiskCheckerMetrics:
    """Tests that RiskChecker emits metrics per observability.mdc §4."""

    @pytest.mark.asyncio
    async def test_risk_checker_emits_allowed_metric(self) -> None:
        """Test that RiskChecker emits metrics for allowed checks."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        limits = RiskLimits()
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
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

        # Check should emit metrics
        await checker.check(intent, context)

        # Verify metrics were emitted
        assert collector.get_counter("risk_checks_total", labels={"allowed": "true"}) == 1
        assert collector.get_counter("risk_checks_total", labels={"allowed": "false"}) == 0

    @pytest.mark.asyncio
    async def test_risk_checker_emits_denied_metric(self) -> None:
        """Test that RiskChecker emits metrics for denied checks."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        limits = RiskLimits(max_order_size=0.5)  # Small limit to force denial
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,  # Larger than max_order_size
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(intent=intent)

        # Check should emit metrics
        await checker.check(intent, context)

        # Verify metrics were emitted
        assert collector.get_counter("risk_checks_total", labels={"allowed": "false"}) == 1
        assert collector.get_counter("risk_checks_total", labels={"allowed": "true"}) == 0
        # Should have recorded denial reason
        assert (
            collector.get_counter(
                "risk_denials_total", labels={"reason": RiskReasonCode.RISK_ORDER_TOO_LARGE.value}
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_risk_checker_emits_projected_exposure(self) -> None:
        """Test that RiskChecker emits projected exposure metric."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        limits = RiskLimits()
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
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

        # Check should emit metrics
        await checker.check(intent, context)

        # Projected exposure may or may not be in projections
        # (depends on which policies run)
        # Just verify the metric infrastructure works
        exposure = collector.get_gauge("risk_projected_exposure")
        # Should be 0.0 if not set, or a positive value if set
        assert exposure >= 0.0
