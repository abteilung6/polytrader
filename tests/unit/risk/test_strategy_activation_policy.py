"""Unit tests for strategy activation risk policy.

Per Platform_Proposal.md §2.3: Tests verify that check_strategy_activation()
correctly allows/denies based on strategy activation status and execution mode.
"""

import pytest

from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode
from polytrader.risk.policies import check_strategy_activation
from tests.factories.events import create_order_intent_event


class FixedClock:
    """Fixed clock for deterministic time in tests."""

    def __init__(self, time: float = 1000.0) -> None:
        """Initialize with fixed time.

        Args:
            time: Fixed monotonic time
        """
        self._time = time

    def monotonic(self) -> float:
        """Return fixed monotonic time."""
        return self._time


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
    intent = create_order_intent_event(strategy_id=strategy_id)
    return RiskContext(
        intent=intent,
        active_strategies=active_strategies or set(),
        is_paper_mode=is_paper_mode,
    )


def create_risk_limits() -> RiskLimits:
    """Create default risk limits for tests."""
    return RiskLimits()


class TestStrategyActivationPolicy:
    """Tests for check_strategy_activation policy."""

    def test_allows_active_strategy_live_mode(self) -> None:
        """Test check_strategy_activation() allows active strategy (live mode)."""
        context = create_risk_context(
            strategy_id="strategy_1",
            active_strategies={"strategy_1", "strategy_2"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()

        result = check_strategy_activation(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in result.reason_codes

    def test_denies_inactive_strategy_live_mode(self) -> None:
        """Test check_strategy_activation() denies inactive strategy (live mode)."""
        context = create_risk_context(
            strategy_id="strategy_1",
            active_strategies={"strategy_2", "strategy_3"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()

        result = check_strategy_activation(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes
        assert "strategy_id" in result.metadata
        assert result.metadata["strategy_id"] == "strategy_1"
        assert "active_strategies" in result.metadata
        assert result.metadata["is_paper_mode"] is False

    def test_always_allows_paper_mode(self) -> None:
        """Test check_strategy_activation() always allows in paper mode (no check)."""
        # Test with inactive strategy in paper mode
        context = create_risk_context(
            strategy_id="strategy_1",
            active_strategies=set(),  # Empty set (inactive)
            is_paper_mode=True,
        )
        limits = create_risk_limits()

        result = check_strategy_activation(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in result.reason_codes

    def test_returns_strategy_not_active_reason_code(self) -> None:
        """Test check_strategy_activation() returns RISK_STRATEGY_NOT_ACTIVE reason code."""
        context = create_risk_context(
            strategy_id="inactive_strategy",
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )
        limits = create_risk_limits()

        result = check_strategy_activation(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes
        assert len(result.reason_codes) == 1

    @pytest.mark.parametrize(
        "strategy_id,active_strategies,is_paper_mode,expected_allowed",
        [
            # Live mode tests
            ("strategy_1", {"strategy_1"}, False, True),
            ("strategy_1", {"strategy_1", "strategy_2"}, False, True),
            ("strategy_1", {"strategy_2"}, False, False),
            ("strategy_1", set(), False, False),
            # Paper mode tests (always allow)
            ("strategy_1", {"strategy_1"}, True, True),
            ("strategy_1", {"strategy_2"}, True, True),
            ("strategy_1", set(), True, True),
        ],
    )
    def test_parameterized_combinations(
        self,
        strategy_id: str,
        active_strategies: set[str],
        is_paper_mode: bool,
        expected_allowed: bool,
    ) -> None:
        """Parameterized test: multiple active/inactive combinations."""
        context = create_risk_context(
            strategy_id=strategy_id,
            active_strategies=active_strategies,
            is_paper_mode=is_paper_mode,
        )
        limits = create_risk_limits()

        result = check_strategy_activation(context, limits)

        assert result.allowed is expected_allowed
        if expected_allowed:
            assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        else:
            assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes
