"""Unit tests for aggregate_ticks_to_candles.

Per unit_testing_technical.mdc: deterministic, fast, isolated, no I/O.
"""

from datetime import UTC, datetime

import pytest

from polytrader.events.types import MarketDataEvent
from polytrader.indicators.candles import aggregate_ticks_to_candles


def _event(
    ts_wall: str, mid: float, market_slug: str = "test", outcome: str = "UP"
) -> MarketDataEvent:
    """Create MarketDataEvent with given ts_wall and mid (bid=ask=mid)."""
    return MarketDataEvent(
        market_slug=market_slug,
        outcome=outcome,
        best_bid=mid,
        best_ask=mid,
        ts_wall=ts_wall,
    )


class TestAggregateTicksToCandles:
    """Tests for aggregate_ticks_to_candles(events, interval_minutes)."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty events returns empty list."""
        result = aggregate_ticks_to_candles([], interval_minutes=15)
        assert result == []

    def test_single_tick_one_candle(self) -> None:
        """Single event yields one candle; open=high=low=close=mid."""
        events = [
            _event("2024-01-15T10:30:00Z", 0.5),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 1
        c = result[0]
        assert c.open == 0.5
        assert c.high == 0.5
        assert c.low == 0.5
        assert c.close == 0.5
        assert c.ts_start == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_two_ticks_same_bucket_one_candle(self) -> None:
        """Two events in same 15m bucket yield one candle; OHLC from mids."""
        events = [
            _event("2024-01-15T10:30:00Z", 0.4),
            _event("2024-01-15T10:35:00Z", 0.6),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 1
        c = result[0]
        assert c.open == 0.4
        assert c.high == 0.6
        assert c.low == 0.4
        assert c.close == 0.6
        assert c.ts_start == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_two_buckets_two_candles(self) -> None:
        """Events in different 15m buckets yield two candles."""
        events = [
            _event("2024-01-15T10:20:00Z", 0.3),
            _event("2024-01-15T10:35:00Z", 0.7),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 2
        assert result[0].ts_start == datetime(2024, 1, 15, 10, 15, 0, tzinfo=UTC)
        assert result[0].open == 0.3
        assert result[0].close == 0.3
        assert result[1].ts_start == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert result[1].open == 0.7
        assert result[1].close == 0.7

    def test_15m_truncation(self) -> None:
        """Events at 10:00 and 10:14 fall in same bucket; 10:15 in next."""
        events = [
            _event("2024-01-15T10:00:00Z", 0.1),
            _event("2024-01-15T10:14:00Z", 0.2),
            _event("2024-01-15T10:15:00Z", 0.3),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 2
        assert result[0].ts_start == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert result[0].open == 0.1
        assert result[0].high == 0.2
        assert result[0].close == 0.2
        assert result[1].ts_start == datetime(2024, 1, 15, 10, 15, 0, tzinfo=UTC)
        assert result[1].open == 0.3
        assert result[1].close == 0.3

    def test_deterministic_order_independent(self) -> None:
        """Same events in different order produce same candles (sorted by ts_wall)."""
        events1 = [
            _event("2024-01-15T10:35:00Z", 0.6),
            _event("2024-01-15T10:30:00Z", 0.4),
        ]
        events2 = [
            _event("2024-01-15T10:30:00Z", 0.4),
            _event("2024-01-15T10:35:00Z", 0.6),
        ]
        r1 = aggregate_ticks_to_candles(events1, interval_minutes=15)
        r2 = aggregate_ticks_to_candles(events2, interval_minutes=15)
        assert len(r1) == len(r2) == 1
        assert r1[0].open == r2[0].open == 0.4
        assert r1[0].close == r2[0].close == 0.6

    def test_uses_mid_not_bid_ask_separately(self) -> None:
        """OHLC uses mid (average of bid/ask) per event."""
        events = [
            MarketDataEvent(
                market_slug="test",
                outcome="UP",
                best_bid=0.2,
                best_ask=0.4,
                ts_wall="2024-01-15T10:30:00Z",
            ),
            MarketDataEvent(
                market_slug="test",
                outcome="UP",
                best_bid=0.5,
                best_ask=0.7,
                ts_wall="2024-01-15T10:35:00Z",
            ),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 1
        # mid1 = (0.2+0.4)/2 = 0.3, mid2 = (0.5+0.7)/2 = 0.6
        assert abs(result[0].open - 0.3) < 1e-9
        assert abs(result[0].high - 0.6) < 1e-9
        assert abs(result[0].low - 0.3) < 1e-9
        assert abs(result[0].close - 0.6) < 1e-9

    def test_interval_minutes_raises_invalid(self) -> None:
        """interval_minutes < 1 raises ValueError."""
        with pytest.raises(ValueError, match="interval_minutes must be >= 1"):
            aggregate_ticks_to_candles([_event("2024-01-15T10:30:00Z", 0.5)], interval_minutes=0)
        with pytest.raises(ValueError, match="interval_minutes must be >= 1"):
            aggregate_ticks_to_candles([], interval_minutes=-1)

    def test_ts_wall_z_suffix(self) -> None:
        """ts_wall with Z suffix parses correctly."""
        events = [_event("2024-06-01T12:00:00Z", 0.5)]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 1
        assert result[0].ts_start == datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    def test_interval_60_minutes(self) -> None:
        """60-minute interval buckets correctly."""
        events = [
            _event("2024-01-15T10:00:00Z", 0.1),
            _event("2024-01-15T10:30:00Z", 0.2),
            _event("2024-01-15T11:00:00Z", 0.3),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=60)
        assert len(result) == 2
        assert result[0].ts_start == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert result[0].open == 0.1
        assert result[0].close == 0.2
        assert result[1].ts_start == datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)
        assert result[1].open == 0.3
        assert result[1].close == 0.3

    def test_result_sorted_by_ts_start(self) -> None:
        """Output candles are sorted by ts_start."""
        events = [
            _event("2024-01-15T11:00:00Z", 0.3),
            _event("2024-01-15T10:00:00Z", 0.1),
            _event("2024-01-15T10:30:00Z", 0.2),
        ]
        result = aggregate_ticks_to_candles(events, interval_minutes=15)
        assert len(result) == 3
        for i in range(len(result) - 1):
            assert result[i].ts_start <= result[i + 1].ts_start
        # Buckets: 10:00 (event 10:00), 10:30 (event 10:30), 11:00 (event 11:00)
        assert result[0].ts_start == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert result[1].ts_start == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert result[2].ts_start == datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)
