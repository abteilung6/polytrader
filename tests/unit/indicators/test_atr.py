"""Unit tests for ATR (Average True Range) indicator.

Per unit_testing_technical.mdc: deterministic, fast, isolated, no I/O.
"""

import pytest

from polytrader.indicators.atr import atr


class TestAtr:
    """Tests for atr(high, low, close, window)."""

    def test_atr_same_length_as_input(self) -> None:
        """ATR result has same length as high/low/close."""
        high = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        low = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        close = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5]
        result = atr(high, low, close, window=3)
        assert len(result) == len(high)

    def test_atr_first_window_minus_one_are_zero(self) -> None:
        """First (window-1) values are 0.0 (not enough data)."""
        high = [10.0, 11.0, 12.0, 13.0, 14.0]
        low = [9.0, 10.0, 11.0, 12.0, 13.0]
        close = [9.5, 10.5, 11.5, 12.5, 13.5]
        result = atr(high, low, close, window=3)
        assert result[0] == 0.0
        assert result[1] == 0.0
        assert result[2] != 0.0

    def test_atr_flat_range(self) -> None:
        """When high=low=close (no range), TR is 0; ATR converges to 0."""
        high = [5.0] * 20
        low = [5.0] * 20
        close = [5.0] * 20
        result = atr(high, low, close, window=5)
        assert result[4] == 0.0
        assert result[-1] == 0.0

    def test_atr_constant_range(self) -> None:
        """Constant range (high-low=2) yields predictable ATR."""
        high = [12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
        low = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        close = [11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        result = atr(high, low, close, window=2)
        # TR = [2, 2, 2, 2, 2, 2]. First ATR at index 1 = mean(TR[0:2]) = 2.0
        assert result[1] == 2.0
        # ATR[2] = (ATR[1]*(2-1) + TR[2])/2 = (2 + 2)/2 = 2.0
        assert result[2] == 2.0
        assert result[-1] == 2.0

    def test_atr_empty_lists(self) -> None:
        """Empty inputs return empty list."""
        result = atr([], [], [], window=5)
        assert result == []

    def test_atr_insufficient_data(self) -> None:
        """Length less than window: valid ATR never computed; first window-1 are 0."""
        high = [1.0, 2.0]
        low = [0.0, 1.0]
        close = [0.5, 1.5]
        result = atr(high, low, close, window=5)
        assert len(result) == 2
        assert result == [0.0, 0.0]

    def test_atr_raises_invalid_window(self) -> None:
        """Window < 1 raises ValueError."""
        with pytest.raises(ValueError, match="window must be >= 1"):
            atr([1.0], [0.0], [0.5], window=0)
        with pytest.raises(ValueError, match="window must be >= 1"):
            atr([1.0], [0.0], [0.5], window=-1)

    def test_atr_raises_length_mismatch(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            atr([1.0, 2.0], [0.0], [0.5, 1.5], window=2)
        with pytest.raises(ValueError, match="same length"):
            atr([1.0], [0.0, 1.0], [0.5, 1.5], window=2)

    def test_atr_deterministic(self) -> None:
        """Same input produces same output (determinism)."""
        high = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        low = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0]
        close = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5]
        a = atr(high, low, close, window=3)
        b = atr(high, low, close, window=3)
        assert a == b

    @pytest.mark.parametrize("window", [1, 2, 14])
    def test_atr_window_boundaries(self, window: int) -> None:
        """ATR accepts valid window values and produces valid last value when enough data."""
        n = max(20, window + 5)
        high = [float(10 + i) for i in range(n)]
        low = [float(9 + i) for i in range(n)]
        close = [float(9.5 + i) for i in range(n)]
        result = atr(high, low, close, window=window)
        assert len(result) == n
        if n >= window:
            assert result[window - 1] >= 0.0
            assert result[-1] >= 0.0
