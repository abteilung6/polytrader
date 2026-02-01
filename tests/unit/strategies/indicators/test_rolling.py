"""Unit tests for rolling_mean and ema.

Per unit_testing_technical.mdc: deterministic, fast, isolated, no I/O.
"""

import pytest

from polytrader.strategies.indicators.rolling import ema, rolling_mean


class TestRollingMean:
    """Tests for rolling_mean(values, window)."""

    def test_rolling_mean_basic(self) -> None:
        """Rolling mean of [1,2,3,4,5] with window=3 gives [2,3,4]."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = rolling_mean(values, window=3)
        assert result == [2.0, 3.0, 4.0]

    def test_rolling_mean_window_one(self) -> None:
        """Window=1 returns each value as its own mean."""
        values = [1.0, 2.0, 3.0]
        result = rolling_mean(values, window=1)
        assert result == [1.0, 2.0, 3.0]

    def test_rolling_mean_window_equals_length(self) -> None:
        """Window equals length returns single value (mean of all)."""
        values = [2.0, 4.0, 6.0]
        result = rolling_mean(values, window=3)
        assert result == [4.0]

    def test_rolling_mean_empty_list(self) -> None:
        """Empty list returns empty list."""
        result = rolling_mean([], window=3)
        assert result == []

    def test_rolling_mean_insufficient_data(self) -> None:
        """List shorter than window returns empty list."""
        result = rolling_mean([1.0, 2.0], window=5)
        assert result == []

    def test_rolling_mean_raises_invalid_window(self) -> None:
        """Window < 1 raises ValueError."""
        with pytest.raises(ValueError, match="window must be >= 1"):
            rolling_mean([1.0, 2.0], window=0)
        with pytest.raises(ValueError, match="window must be >= 1"):
            rolling_mean([1.0, 2.0], window=-1)

    @pytest.mark.parametrize(
        ("values", "window", "expected_last"),
        [
            ([1.0] * 10, 5, 1.0),
            ([1.0, 2.0, 3.0, 4.0, 5.0], 2, 4.5),
        ],
    )
    def test_rolling_mean_parametrized(
        self, values: list[float], window: int, expected_last: float
    ) -> None:
        """Parametrized cases for rolling mean."""
        result = rolling_mean(values, window)
        assert len(result) == len(values) - window + 1
        assert result[-1] == expected_last


class TestEma:
    """Tests for ema(values, window)."""

    def test_ema_same_length_as_input(self) -> None:
        """EMA result has same length as input."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = ema(values, window=3)
        assert len(result) == len(values)

    def test_ema_first_value_equals_first_input(self) -> None:
        """First EMA value equals first input (seed)."""
        values = [10.0, 20.0, 30.0]
        result = ema(values, window=2)
        assert result[0] == 10.0

    def test_ema_window_one(self) -> None:
        """Window=1 gives alpha=1, so EMA equals input series."""
        values = [1.0, 2.0, 3.0]
        result = ema(values, window=1)
        assert result == values

    def test_ema_constant_series(self) -> None:
        """Constant input yields constant EMA."""
        values = [5.0] * 10
        result = ema(values, window=3)
        assert result == values

    def test_ema_empty_list(self) -> None:
        """Empty list returns empty list."""
        result = ema([], window=3)
        assert result == []

    def test_ema_single_value(self) -> None:
        """Single value returns single value."""
        result = ema([7.0], window=5)
        assert result == [7.0]

    def test_ema_raises_invalid_window(self) -> None:
        """Window < 1 raises ValueError."""
        with pytest.raises(ValueError, match="window must be >= 1"):
            ema([1.0, 2.0], window=0)
        with pytest.raises(ValueError, match="window must be >= 1"):
            ema([1.0, 2.0], window=-1)

    def test_ema_deterministic(self) -> None:
        """Same input produces same output (determinism)."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        a = ema(values, window=3)
        b = ema(values, window=3)
        assert a == b

    @pytest.mark.parametrize("window", [1, 2, 5, 20])
    def test_ema_window_boundaries(self, window: int) -> None:
        """EMA accepts valid window values."""
        values = [float(i) for i in range(50)]
        result = ema(values, window=window)
        assert len(result) == 50
        assert result[0] == 0.0
