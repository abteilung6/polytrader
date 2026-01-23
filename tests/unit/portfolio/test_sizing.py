"""Tests for portfolio-aware sizing calculation."""

from polytrader.portfolio.models import Target
from polytrader.portfolio.sizing import calculate_size
from polytrader.types import Position


class TestCalculateSize:
    """Tests for calculate_size function."""

    def test_calculate_size_no_position(self) -> None:
        """Test sizing when no current position exists."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        size = calculate_size(target, current_position=None)

        assert size == 1.0

    def test_calculate_size_with_position_below_target(self) -> None:
        """Test sizing when current position is below target."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=5.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        current_position = Position(
            market_slug="test-market",
            outcome="UP",
            size=2.0,
            target_price=0.50,
            entry_price=0.50,
            entry_time=1234567890.0,
        )

        size = calculate_size(target, current_position=current_position)

        # size = target_exposure - current_position.size = 5.0 - 2.0 = 3.0
        assert size == 3.0

    def test_calculate_size_with_position_at_target(self) -> None:
        """Test sizing when current position equals target."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=5.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        current_position = Position(
            market_slug="test-market",
            outcome="UP",
            size=5.0,
            target_price=0.50,
            entry_price=0.50,
            entry_time=1234567890.0,
        )

        size = calculate_size(target, current_position=current_position)

        # size = target_exposure - current_position.size = 5.0 - 5.0 = 0.0
        assert size == 0.0

    def test_calculate_size_with_position_above_target(self) -> None:
        """Test sizing when current position exceeds target (clamped to 0)."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=3.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        current_position = Position(
            market_slug="test-market",
            outcome="UP",
            size=5.0,
            target_price=0.50,
            entry_price=0.50,
            entry_time=1234567890.0,
        )

        size = calculate_size(target, current_position=current_position)

        # size = max(0.0, target_exposure - current_position.size)
        #      = max(0.0, 3.0 - 5.0) = max(0.0, -2.0) = 0.0
        assert size == 0.0

    def test_calculate_size_zero_target(self) -> None:
        """Test sizing with zero target exposure."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=0.0,
            rationale="Zero target",
            constraint_binding=[],
            sizing_metadata={},
        )

        size = calculate_size(target, current_position=None)

        assert size == 0.0

    def test_calculate_size_zero_target_with_position(self) -> None:
        """Test sizing with zero target but existing position."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=0.0,
            rationale="Zero target",
            constraint_binding=[],
            sizing_metadata={},
        )

        current_position = Position(
            market_slug="test-market",
            outcome="UP",
            size=2.0,
            target_price=0.50,
            entry_price=0.50,
            entry_time=1234567890.0,
        )

        size = calculate_size(target, current_position=current_position)

        # size = max(0.0, 0.0 - 2.0) = 0.0
        assert size == 0.0
