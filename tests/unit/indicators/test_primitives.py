"""Unit tests for semantic primitives: deviation_z, fair_price_anchor, trend_strength_ema_gap.

Per unit_testing_technical.mdc: deterministic, fast, isolated, no I/O.
"""

from datetime import UTC, datetime

import pytest

from polytrader.indicators.candles.models import Candle
from polytrader.indicators.primitives import (
    deviation_z,
    fair_price_anchor,
    trend_strength_ema_gap,
)


def _candle(open_: float, high: float, low: float, close: float) -> Candle:
    """Create Candle with given OHLC; ts_start fixed for tests."""
    return Candle(
        open=open_,
        high=high,
        low=low,
        close=close,
        ts_start=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
    )


class TestDeviationZ:
    """Tests for deviation_z(value, anchor, scale)."""

    def test_normal_case(self) -> None:
        """(value - anchor) / scale when scale > 0."""
        assert abs(deviation_z(110.0, 100.0, 5.0) - 2.0) < 1e-9
        assert abs(deviation_z(90.0, 100.0, 5.0) - (-2.0)) < 1e-9
        assert abs(deviation_z(100.0, 100.0, 5.0)) < 1e-9

    def test_zero_scale_returns_zero(self) -> None:
        """Scale <= 0 returns 0.0 (guarded)."""
        assert deviation_z(110.0, 100.0, 0.0) == 0.0
        assert deviation_z(110.0, 100.0, -1.0) == 0.0

    def test_negative_scale_returns_zero(self) -> None:
        """Negative scale returns 0.0."""
        assert deviation_z(1.0, 0.0, -0.5) == 0.0


class TestFairPriceAnchor:
    """Tests for fair_price_anchor(candles, method, window)."""

    def test_empty_candles_returns_empty(self) -> None:
        """Empty candle list returns empty list."""
        result = fair_price_anchor([], method="rolling_mean", window=3)
        assert result == []

    def test_rolling_mean_window_one(self) -> None:
        """Window=1: anchor is typical price per candle."""
        candles = [
            _candle(1.0, 2.0, 0.0, 1.0),  # typical = (2+0+1)/3 = 1.0
            _candle(2.0, 3.0, 1.0, 2.0),  # typical = (3+1+2)/3 = 2.0
        ]
        result = fair_price_anchor(candles, method="rolling_mean", window=1)
        assert len(result) == 2
        assert abs(result[0] - 1.0) < 1e-9
        assert abs(result[1] - 2.0) < 1e-9

    def test_rolling_mean_window_three(self) -> None:
        """Window=3: first two indices 0.0, then rolling mean of typical prices."""
        # Typical prices: 1.0, 2.0, 3.0 → rolling_mean gives [2.0] (mean of 1,2,3)
        candles = [
            _candle(1.0, 1.0, 1.0, 1.0),  # tp=1
            _candle(2.0, 2.0, 2.0, 2.0),  # tp=2
            _candle(3.0, 3.0, 3.0, 3.0),  # tp=3
        ]
        result = fair_price_anchor(candles, method="rolling_mean", window=3)
        assert len(result) == 3
        assert result[0] == 0.0
        assert result[1] == 0.0
        assert abs(result[2] - 2.0) < 1e-9

    def test_raises_invalid_window(self) -> None:
        """Window < 1 raises ValueError."""
        candles = [_candle(1.0, 1.0, 1.0, 1.0)]
        with pytest.raises(ValueError, match="window must be >= 1"):
            fair_price_anchor(candles, method="rolling_mean", window=0)
        with pytest.raises(ValueError, match="window must be >= 1"):
            fair_price_anchor(candles, method="rolling_mean", window=-1)

    def test_raises_unsupported_method(self) -> None:
        """Unsupported method raises ValueError."""
        candles = [_candle(1.0, 1.0, 1.0, 1.0)]
        with pytest.raises(ValueError, match="method must be 'rolling_mean'"):
            fair_price_anchor(candles, method="ema", window=1)
        with pytest.raises(ValueError, match="method must be 'rolling_mean'"):
            fair_price_anchor(candles, method="", window=1)


class TestTrendStrengthEmaGap:
    """Tests for trend_strength_ema_gap(close_series, fast, slow, volatility_series)."""

    def test_warmup_and_normal(self) -> None:
        """Result length equals close_series; warmup then |ema_fast - ema_slow|/vol."""
        close = [10.0, 11.0, 12.0, 13.0, 14.0]
        vol = [1.0, 1.0, 1.0, 1.0, 1.0]
        result = trend_strength_ema_gap(close, fast=2, slow=3, volatility_series=vol)
        assert len(result) == 5
        # EMA(2): [10, 10.67, 11.56, 12.52, 13.51]; EMA(3): [10, 10.5, 11.25, 12.13, 13.06]
        # Gap at index 4: |13.51 - 13.06| = 0.45
        assert result[0] >= 0.0
        assert result[4] >= 0.0
        assert abs(result[4] - abs(0.45)) < 0.01  # approximate

    def test_zero_vol_returns_zero_at_index(self) -> None:
        """When volatility_series[i] <= 0, result[i] is 0.0."""
        close = [1.0, 2.0, 3.0]
        vol = [1.0, 0.0, 1.0]  # zero at index 1
        result = trend_strength_ema_gap(close, fast=1, slow=1, volatility_series=vol)
        assert len(result) == 3
        assert result[0] >= 0.0
        assert result[1] == 0.0
        assert result[2] == 0.0  # ema_fast=ema_slow when fast=slow=1 (both equal close)

    def test_empty_series_returns_empty(self) -> None:
        """Empty close_series returns empty list."""
        result = trend_strength_ema_gap([], fast=2, slow=3, volatility_series=[])
        assert result == []

    def test_raises_invalid_fast_slow(self) -> None:
        """fast < 1 or slow < 1 raises ValueError."""
        close = [1.0, 2.0]
        vol = [1.0, 1.0]
        with pytest.raises(ValueError, match="fast must be >= 1"):
            trend_strength_ema_gap(close, fast=0, slow=2, volatility_series=vol)
        with pytest.raises(ValueError, match="slow must be >= 1"):
            trend_strength_ema_gap(close, fast=2, slow=0, volatility_series=vol)

    def test_raises_length_mismatch(self) -> None:
        """Mismatched close_series and volatility_series lengths raise ValueError."""
        close = [1.0, 2.0, 3.0]
        vol_short = [1.0, 1.0]
        with pytest.raises(ValueError, match="same length"):
            trend_strength_ema_gap(close, fast=1, slow=2, volatility_series=vol_short)
