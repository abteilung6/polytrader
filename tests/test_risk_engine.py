"""Tests for risk engine.

Per testing.mdc §1.A: Unit tests for risk engine (fast, deterministic).
Per testing.mdc §2: Test hard veto works and emits reason codes.
"""

from unittest.mock import MagicMock

from polytrader.risk.engine import RiskEngine
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode, RiskResult
from polytrader.types import MarketDataEvent, OrderIntentEvent


class TestRiskEngineBasic:
    """Tests for basic risk engine functionality."""

    def test_risk_engine_allows_valid_order(self) -> None:
        """Test that valid orders pass all policies."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
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

        limits = RiskLimits(
            max_order_size=10.0,
            max_position_per_market=100.0,
            max_position_global=1000.0,
            max_notional_exposure=5000.0,
            max_trades_per_market=10,
            max_data_staleness_seconds=5.0,
            order_rate_limit_per_minute=60,
        )

        engine = RiskEngine(limits=limits)
        result = engine.check(context)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_risk_engine_denies_invalid_order(self) -> None:
        """Test that invalid orders are denied by at least one policy."""
        # Create an expired intent
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        # Make intent expired by setting clock 3 seconds in the future
        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 3.0

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        engine = RiskEngine(limits=limits, clock=clock)
        result = engine.check(context)

        assert result.allowed is False
        assert RiskReasonCode.RISK_PROPOSAL_EXPIRED in result.reason_codes

    def test_risk_engine_denies_multiple_violations(self) -> None:
        """Test that multiple policy violations are all detected."""
        # Create intent that violates multiple policies:
        # 1. Expired (via clock) - from check_proposal_validity
        # 2. Position limit violation - from check_position_limits
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=5.0,  # Will violate position limit
            reason="Test",
            ttl_s=2.0,
        )

        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 3.0  # Expired

        # Set up context with existing position that will cause limit violation
        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 0.5},  # Already have position
        )
        limits = RiskLimits(
            max_order_size=10.0,
            max_position_per_market=1.0,  # Will be exceeded (0.5 + 5.0 = 5.5 > 1.0)
        )

        engine = RiskEngine(limits=limits, clock=clock)
        result = engine.check(context)

        assert result.allowed is False
        # Both violations should be detected (from different policies)
        assert RiskReasonCode.RISK_PROPOSAL_EXPIRED in result.reason_codes
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes


class TestRiskEnginePolicyOrder:
    """Tests for policy ordering and execution."""

    def test_risk_engine_policy_order(self) -> None:
        """Test that policies run in fixed order."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        # Track policy execution order
        execution_order: list[str] = []

        def mock_policy_1(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            execution_order.append("policy_1")
            return RiskResult(allowed=True, reason_codes=[RiskReasonCode.RISK_ALLOWED])

        def mock_policy_2(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            execution_order.append("policy_2")
            return RiskResult(allowed=True, reason_codes=[RiskReasonCode.RISK_ALLOWED])

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_1, mock_policy_2]

        engine.check(context)

        assert execution_order == ["policy_1", "policy_2"]

    def test_risk_engine_continues_after_denial(self) -> None:
        """Test that all policies run even after one denies."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        execution_count = 0

        def mock_policy_deny(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            nonlocal execution_count
            execution_count += 1
            return RiskResult(allowed=False, reason_codes=[RiskReasonCode.RISK_PROPOSAL_EXPIRED])

        def mock_policy_allow(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            nonlocal execution_count
            execution_count += 1
            return RiskResult(allowed=True, reason_codes=[RiskReasonCode.RISK_ALLOWED])

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_deny, mock_policy_allow]

        result = engine.check(context)

        assert result.allowed is False
        assert execution_count == 2  # Both policies ran


class TestRiskEngineAggregation:
    """Tests for result aggregation."""

    def test_risk_engine_aggregates_reason_codes(self) -> None:
        """Test that reason codes from all policies are aggregated."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        def mock_policy_1(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED, RiskReasonCode.RISK_MAX_POSITION],
            )

        def mock_policy_2(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED, RiskReasonCode.RISK_RATE_LIMIT],
            )

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_1, mock_policy_2]

        result = engine.check(context)

        # All reason codes should be present
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes
        assert RiskReasonCode.RISK_RATE_LIMIT in result.reason_codes

    def test_risk_engine_aggregates_projections(self) -> None:
        """Test that projections from all policies are merged."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        def mock_policy_1(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED],
                projections={"projection_1": 100.0},
            )

        def mock_policy_2(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED],
                projections={"projection_2": 200.0},
            )

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_1, mock_policy_2]

        result = engine.check(context)

        assert result.projections["projection_1"] == 100.0
        assert result.projections["projection_2"] == 200.0

    def test_risk_engine_aggregates_metadata(self) -> None:
        """Test that metadata from all policies is merged."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        def mock_policy_1(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED],
                metadata={"metadata_1": "value_1"},
            )

        def mock_policy_2(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED],
                metadata={"metadata_2": "value_2"},
            )

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_1, mock_policy_2]

        result = engine.check(context)

        assert result.metadata["metadata_1"] == "value_1"
        assert result.metadata["metadata_2"] == "value_2"

    def test_risk_engine_deduplicates_reason_codes(self) -> None:
        """Test that duplicate reason codes are removed (first occurrence kept)."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        def mock_policy_1(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED, RiskReasonCode.RISK_MAX_POSITION],
            )

        def mock_policy_2(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(
                allowed=True,
                reason_codes=[RiskReasonCode.RISK_ALLOWED, RiskReasonCode.RISK_MAX_POSITION],
            )

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_1, mock_policy_2]

        result = engine.check(context)

        # Duplicate reason codes should be deduplicated
        assert result.reason_codes.count(RiskReasonCode.RISK_ALLOWED) == 1
        assert result.reason_codes.count(RiskReasonCode.RISK_MAX_POSITION) == 1
        # Order should be preserved (first occurrence)
        assert result.reason_codes[0] == RiskReasonCode.RISK_ALLOWED
        assert result.reason_codes[1] == RiskReasonCode.RISK_MAX_POSITION


class TestRiskEngineClock:
    """Tests for clock injection."""

    def test_risk_engine_with_clock(self) -> None:
        """Test that clock is passed to policies that need it."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 1.0  # Not expired

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        engine = RiskEngine(limits=limits, clock=clock)
        engine.check(context)

        # Clock should have been called by check_proposal_validity
        assert clock.monotonic.called

    def test_risk_engine_without_clock(self) -> None:
        """Test that engine works without clock (uses time.monotonic())."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
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

        limits = RiskLimits(
            max_order_size=10.0,
            max_position_per_market=100.0,
            max_position_global=1000.0,
            max_notional_exposure=5000.0,
            max_trades_per_market=10,
            max_data_staleness_seconds=5.0,
            order_rate_limit_per_minute=60,
        )

        engine = RiskEngine(limits=limits)
        result = engine.check(context)

        # Should work without explicit clock
        assert result.allowed is True


class TestRiskEngineCustomPolicies:
    """Tests for customizable policies."""

    def test_risk_engine_custom_policies(self) -> None:
        """Test that custom policy list can be used."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        custom_policy_called = False

        def custom_policy(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            nonlocal custom_policy_called
            custom_policy_called = True
            return RiskResult(allowed=True, reason_codes=[RiskReasonCode.RISK_ALLOWED])

        engine = RiskEngine(limits=limits)
        engine.policies = [custom_policy]

        result = engine.check(context)

        assert custom_policy_called
        assert result.allowed is True


class TestRiskEngineEdgeCases:
    """Tests for edge cases."""

    def test_risk_engine_empty_policies(self) -> None:
        """Test that engine handles empty policy list."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        engine = RiskEngine(limits=limits)
        engine.policies = []

        result = engine.check(context)

        # With no policies, should default to allowed (empty reason codes)
        assert result.allowed is True
        assert len(result.reason_codes) == 0

    def test_risk_engine_all_policies_deny(self) -> None:
        """Test that engine denies when all policies deny."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
        )

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        def mock_policy_deny(ctx: RiskContext, lims: RiskLimits) -> RiskResult:
            return RiskResult(allowed=False, reason_codes=[RiskReasonCode.RISK_PROPOSAL_EXPIRED])

        engine = RiskEngine(limits=limits)
        engine.policies = [mock_policy_deny, mock_policy_deny]

        result = engine.check(context)

        assert result.allowed is False
        # Should have deduplicated reason codes
        assert result.reason_codes.count(RiskReasonCode.RISK_PROPOSAL_EXPIRED) == 1
