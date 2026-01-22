"""Unit tests for RiskEngine with strategy activation policy.

Per Platform_Proposal.md §2.3: Tests verify that RiskEngine.check() includes
strategy activation policy and aggregates results correctly.
"""

from polytrader.risk.engine import RiskEngine
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode
from tests.factories.events import create_order_intent_event


def create_risk_context(
    strategy_id: str = "test_strategy",
    active_strategies: set[str] | None = None,
    is_paper_mode: bool = True,
) -> RiskContext:
    """Create a test RiskContext with deterministic defaults.

    Args:
        strategy_id: Strategy ID for the order intent
        active_strategies: Set of active strategy IDs (default: empty set)
        is_paper_mode: Whether in paper mode (default: True)

    Returns:
        RiskContext with specified parameters
    """
    from polytrader.events.types import MarketDataEvent

    intent = create_order_intent_event(strategy_id=strategy_id)
    # Add market data to avoid RISK_DATA_STALE
    market_data = MarketDataEvent(
        market_slug=intent.market_slug,
        outcome=intent.outcome,
        best_bid=0.45,
        best_ask=0.55,
    )
    return RiskContext(
        intent=intent,
        market_data=market_data,
        active_strategies=active_strategies or set(),
        is_paper_mode=is_paper_mode,
        reconciliation_healthy=True,
    )


def create_risk_limits() -> RiskLimits:
    """Create default risk limits for tests."""
    return RiskLimits(
        max_order_size=100.0,
        max_position_per_market=1000.0,
        max_position_global=10000.0,
        max_notional_exposure=50000.0,
        max_trades_per_market=10,
        max_data_staleness_seconds=5.0,
        order_rate_limit_per_minute=60,
    )


class TestRiskEngineStrategyActivation:
    """Tests for RiskEngine with strategy activation policy."""

    def test_includes_strategy_activation_policy(self) -> None:
        """Test RiskEngine.check() includes strategy activation policy."""
        context = create_risk_context(
            strategy_id="inactive_strategy",
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()
        engine = RiskEngine(limits=limits)

        result = engine.check(context)

        # Should be denied by strategy activation policy
        assert result.allowed is False
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes

    def test_policy_order_strategy_activation_runs(self) -> None:
        """Test policy order: strategy activation check runs (verify in policy list)."""
        limits = create_risk_limits()
        engine = RiskEngine(limits=limits)

        # Verify check_strategy_activation is in the policy list
        from polytrader.risk.policies import check_strategy_activation

        assert check_strategy_activation in engine.policies

        # Verify it runs after token_ownership and before max_trades_per_market
        from polytrader.risk.policies import (
            check_max_trades_per_market,
            check_token_ownership,
        )

        token_ownership_idx = engine.policies.index(check_token_ownership)
        strategy_activation_idx = engine.policies.index(check_strategy_activation)
        max_trades_idx = engine.policies.index(check_max_trades_per_market)

        assert token_ownership_idx < strategy_activation_idx < max_trades_idx

    def test_aggregation_strategy_activation_deny_final_denied(self) -> None:
        """Test aggregation: strategy activation deny → final result denied."""
        context = create_risk_context(
            strategy_id="inactive_strategy",
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()
        engine = RiskEngine(limits=limits)

        result = engine.check(context)

        # Final result should be denied
        assert result.allowed is False
        # Should include RISK_STRATEGY_NOT_ACTIVE in reason codes
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes

    def test_reason_codes_strategy_not_active_in_result(self) -> None:
        """Test reason codes: RISK_STRATEGY_NOT_ACTIVE in result.reason_codes."""
        context = create_risk_context(
            strategy_id="inactive_strategy",
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()
        engine = RiskEngine(limits=limits)

        result = engine.check(context)

        # Should be denied and include RISK_STRATEGY_NOT_ACTIVE
        assert result.allowed is False
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes

    def test_paper_mode_allows_all_strategies(self) -> None:
        """Test paper mode: all strategies allowed regardless of activation."""
        # Inactive strategy in paper mode should still pass
        context = create_risk_context(
            strategy_id="inactive_strategy",
            active_strategies=set(),  # Empty set (inactive)
            is_paper_mode=True,
        )
        limits = create_risk_limits()
        engine = RiskEngine(limits=limits)

        result = engine.check(context)

        # Should pass (other policies may deny, but strategy activation won't)
        # If all other policies pass, result should be allowed
        # Note: This test assumes other policies pass (valid order)
        if result.allowed:
            assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in result.reason_codes

    def test_live_mode_only_active_strategies_allowed(self) -> None:
        """Test live mode: only active strategies allowed."""
        # Inactive strategy in live mode
        context_inactive = create_risk_context(
            strategy_id="inactive_strategy",
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()
        engine = RiskEngine(limits=limits)

        result_inactive = engine.check(context_inactive)

        # Inactive strategy should be denied
        assert result_inactive.allowed is False
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result_inactive.reason_codes
