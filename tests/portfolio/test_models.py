"""Tests for portfolio models."""

import pytest

from polytrader.portfolio.models import PortfolioConstraints, Target


class TestTarget:
    """Tests for Target dataclass."""

    def test_target_creation(self) -> None:
        """Test that Target can be created with all required fields."""
        target = Target(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        assert target.market_slug == "btc-updown-15m-1768122000"
        assert target.outcome == "UP"
        assert target.target_exposure == 1.0
        assert target.rationale == "Test target"
        assert target.constraint_binding == []
        assert target.sizing_metadata == {}

    def test_target_validation_non_negative_exposure(self) -> None:
        """Test that target_exposure must be >= 0.0."""
        # Valid: target_exposure = 0.0
        target1 = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=0.0,
            rationale="Zero target",
            constraint_binding=[],
            sizing_metadata={},
        )
        assert target1.target_exposure == 0.0

        # Valid: target_exposure > 0.0
        target2 = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Positive target",
            constraint_binding=[],
            sizing_metadata={},
        )
        assert target2.target_exposure == 1.0

        # Invalid: target_exposure < 0.0
        with pytest.raises(ValueError, match="target_exposure must be >= 0.0"):
            Target(
                market_slug="test-market",
                outcome="UP",
                target_exposure=-0.1,
                rationale="Invalid negative target",
                constraint_binding=[],
                sizing_metadata={},
            )

    def test_target_is_immutable(self) -> None:
        """Test that Target is immutable (frozen dataclass)."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test",
            constraint_binding=[],
            sizing_metadata={},
        )

        # Frozen dataclass should raise AttributeError on assignment
        with pytest.raises(AttributeError):
            target.target_exposure = 2.0  # type: ignore[misc]

    def test_target_with_constraints(self) -> None:
        """Test that Target can include constraint binding."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=0.5,
            rationale="Clipped target",
            constraint_binding=["max_position", "capital_limit"],
            sizing_metadata={},
        )

        assert target.constraint_binding == ["max_position", "capital_limit"]

    def test_target_with_sizing_metadata(self) -> None:
        """Test that Target can include sizing metadata."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=16.32,
            rationale="Profit-targeted sizing",
            constraint_binding=[],
            sizing_metadata={
                "sizing_method": "profit_targeted",
                "target_profit_usdc": 10.0,
                "required_investment": 16.32,
            },
        )

        assert target.sizing_metadata["sizing_method"] == "profit_targeted"
        assert target.sizing_metadata["target_profit_usdc"] == 10.0


class TestPortfolioConstraints:
    """Tests for PortfolioConstraints dataclass."""

    def test_portfolio_constraints_creation(self) -> None:
        """Test that PortfolioConstraints can be created."""
        constraints = PortfolioConstraints(
            max_position_per_market=10.0,
            max_capital_per_market=100.0,
            max_total_exposure=1000.0,
        )

        assert constraints.max_position_per_market == 10.0
        assert constraints.max_capital_per_market == 100.0
        assert constraints.max_total_exposure == 1000.0

    def test_portfolio_constraints_defaults(self) -> None:
        """Test that PortfolioConstraints has None defaults."""
        constraints = PortfolioConstraints()

        assert constraints.max_position_per_market is None
        assert constraints.max_capital_per_market is None
        assert constraints.max_total_exposure is None

    def test_portfolio_constraints_clip_target_placeholder(self) -> None:
        """Test that clip_target is a placeholder (returns unchanged)."""
        constraints = PortfolioConstraints()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test",
            constraint_binding=[],
            sizing_metadata={},
        )

        clipped = constraints.clip_target(target, current_position=0.0)

        # Placeholder returns unchanged
        assert clipped == target
