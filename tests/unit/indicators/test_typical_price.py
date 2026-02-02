"""Unit tests for typical_price indicator.

Per unit_testing_technical.mdc: deterministic, fast, isolated, no I/O.
"""

import pytest

from polytrader.indicators.typical_price import typical_price


class TestTypicalPrice:
    """Tests for typical_price(high, low, close)."""

    def test_typical_price_formula(self) -> None:
        """Typical price is (high + low + close) / 3."""
        result = typical_price(high=10.0, low=2.0, close=6.0)
        assert result == (10.0 + 2.0 + 6.0) / 3.0
        assert result == 6.0

    def test_typical_price_symmetric(self) -> None:
        """When high=low=close, result equals that value."""
        result = typical_price(high=0.5, low=0.5, close=0.5)
        assert result == 0.5

    def test_typical_price_zero(self) -> None:
        """Zero inputs yield zero."""
        result = typical_price(high=0.0, low=0.0, close=0.0)
        assert result == 0.0

    @pytest.mark.parametrize(
        ("high", "low", "close", "expected"),
        [
            (1.0, 0.0, 0.5, (1.0 + 0.0 + 0.5) / 3.0),
            (100.0, 90.0, 95.0, 95.0),
        ],
    )
    def test_typical_price_parametrized(
        self, high: float, low: float, close: float, expected: float
    ) -> None:
        """Parametrized boundary and normal cases."""
        assert typical_price(high, low, close) == expected
