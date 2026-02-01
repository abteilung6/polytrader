"""Unit tests for Candle model.

Per unit_testing_technical.mdc: deterministic, fast, isolated.
"""

from datetime import UTC, datetime

import pytest

from polytrader.strategies.candles.models import Candle


class TestCandle:
    """Tests for Candle dataclass."""

    def test_candle_construction(self) -> None:
        """Candle can be constructed with open, high, low, close, ts_start."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        c = Candle(open=0.1, high=0.5, low=0.05, close=0.4, ts_start=ts)
        assert c.open == 0.1
        assert c.high == 0.5
        assert c.low == 0.05
        assert c.close == 0.4
        assert c.ts_start == ts

    def test_candle_frozen(self) -> None:
        """Candle is immutable (frozen dataclass)."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        c = Candle(open=0.1, high=0.5, low=0.05, close=0.4, ts_start=ts)
        with pytest.raises(AttributeError):
            c.open = 0.2  # type: ignore[misc]
        with pytest.raises(AttributeError):
            c.ts_start = datetime(2024, 1, 16, 0, 0, 0, tzinfo=UTC)  # type: ignore[misc]
