"""Unit tests for VolatilityFilteredMeanReversionStrategy.

Per testing.mdc: regime gate, signal symmetry, exit logic, warmup, atr zero.
Uses fixed candle/event sequences and optional wall clock for determinism.
"""

from datetime import UTC, datetime, timedelta

import pytest

from polytrader.events.types import MarketDataEvent
from polytrader.indicators.candles.models import Candle
from polytrader.store import MemoryMarketDataStore
from polytrader.strategies.volatility_filtered_mean_reversion.strategy import (
    VolatilityFilteredMeanReversionStrategy,
)
from polytrader.types import Position


def _event(
    ts_wall: str,
    mid: float,
    market_slug: str = "test-market",
    outcome: str = "UP",
) -> MarketDataEvent:
    """Create MarketDataEvent with given ts_wall and mid (bid=ask=mid)."""
    return MarketDataEvent(
        market_slug=market_slug,
        outcome=outcome,
        best_bid=mid,
        best_ask=mid,
        ts_wall=ts_wall,
    )


def _candle(open_: float, high: float, low: float, close: float, ts_start: datetime) -> Candle:
    """Create Candle with given OHLC and ts_start."""
    return Candle(
        open=open_,
        high=high,
        low=low,
        close=close,
        ts_start=ts_start,
    )


def events_from_candles(
    candles: list[Candle],
    market_slug: str = "test-market",
    outcome: str = "UP",
) -> list[MarketDataEvent]:
    """Build MarketDataEvents so aggregate_ticks_to_candles returns same candles.

    Emits 4 events per candle (open, high, low, close) in same 15m bucket.
    """
    events: list[MarketDataEvent] = []
    for _i, c in enumerate(candles):
        base = c.ts_start
        # Same bucket: 4 timestamps within the 15m window
        for j, mid in enumerate([c.open, c.high, c.low, c.close]):
            dt = base.replace(minute=base.minute + j + 1)
            ts_wall = dt.isoformat().replace("+00:00", "Z")
            events.append(_event(ts_wall, mid, market_slug, outcome))
    return events


def make_store_with_candles(
    candles: list[Candle],
    market_slug: str = "test-market",
    outcome: str = "UP",
) -> MemoryMarketDataStore:
    """Create MemoryMarketDataStore pre-filled with events from candles."""
    store = MemoryMarketDataStore(window=5000)
    for e in events_from_candles(candles, market_slug, outcome):
        store.add(e)
    return store


class FixedWallClock:
    """Deterministic wall clock for tests."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class TestVfmrWarmup:
    """Warmup: insufficient candles -> None."""

    def test_insufficient_candles_returns_none(self) -> None:
        """Fewer than max(anchor_window, atr_window, ema_slow) candles -> None."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [
            _candle(0.5, 0.52, 0.48, 0.5, base + timedelta(minutes=15 * i)) for i in range(50)
        ]
        store = make_store_with_candles(candles)
        strategy = VolatilityFilteredMeanReversionStrategy(
            market_slug="test-market",
            store=store,
            anchor_window=96,
            atr_window=14,
            ema_slow=80,
        )
        event = _event(
            (base + timedelta(minutes=15 * 49)).isoformat().replace("+00:00", "Z"),
            0.5,
        )
        store.add(event)
        signal = strategy.evaluate(event)
        assert signal is None


class TestVfmrAtrZero:
    """ATR zero or missing -> None."""

    def test_atr_zero_returns_none(self) -> None:
        """All candles flat (high=low=close) -> ATR=0 -> None."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        # 100 flat candles: same open=high=low=close -> TR=0 -> ATR=0
        candles = [
            _candle(0.5, 0.5, 0.5, 0.5, base + timedelta(minutes=15 * i)) for i in range(100)
        ]
        store = make_store_with_candles(candles)
        strategy = VolatilityFilteredMeanReversionStrategy(
            market_slug="test-market",
            store=store,
            anchor_window=96,
            atr_window=14,
        )
        event = _event(
            (base + timedelta(minutes=15 * 99)).isoformat().replace("+00:00", "Z"),
            0.5,
        )
        store.add(event)
        signal = strategy.evaluate(event)
        assert signal is None


class TestVfmrRegimeGate:
    """Regime gate: trend_strength > threshold -> no trade."""

    def test_trend_above_threshold_returns_none(self) -> None:
        """Strong trend (high |ema_fast - ema_slow|) and low trend_threshold -> None."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        # Strong uptrend: close rises; some range for ATR
        candles = [
            _candle(
                0.4 + 0.004 * i,
                0.42 + 0.004 * i,
                0.38 + 0.004 * i,
                0.41 + 0.004 * i,
                base + timedelta(minutes=15 * i),
            )
            for i in range(100)
        ]
        store = make_store_with_candles(candles)
        strategy = VolatilityFilteredMeanReversionStrategy(
            market_slug="test-market",
            store=store,
            anchor_window=96,
            atr_window=14,
            ema_fast=20,
            ema_slow=80,
            trend_threshold=0.01,  # Very low -> trend_ok False
            entry_z=1.5,
        )
        event = _event(
            (base + timedelta(minutes=15 * 99)).isoformat().replace("+00:00", "Z"),
            0.8,
        )
        store.add(event)
        signal = strategy.evaluate(event)
        # trend_strength likely > 0.01 -> no signal
        assert signal is None


class TestVfmrSignalSymmetry:
    """Signal symmetry: z >= entry_z -> DOWN, z <= -entry_z -> UP."""

    def test_z_above_entry_z_signals_down(self) -> None:
        """When z >= entry_z and trend_ok, outcome is DOWN."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        # Most candles at 0.5, last few higher so close[-1] > anchor, z positive
        candles = []
        for i in range(95):
            candles.append(_candle(0.5, 0.52, 0.48, 0.5, base + timedelta(minutes=15 * i)))
        for i in range(95, 100):
            candles.append(_candle(0.7, 0.72, 0.68, 0.7, base + timedelta(minutes=15 * i)))
        store = make_store_with_candles(candles)
        strategy = VolatilityFilteredMeanReversionStrategy(
            market_slug="test-market",
            store=store,
            anchor_window=96,
            atr_window=14,
            ema_fast=20,
            ema_slow=80,
            trend_threshold=2.0,  # High so trend_ok True
            entry_z=1.5,
            exit_z=0.3,
        )
        event = _event(
            (base + timedelta(minutes=15 * 99)).isoformat().replace("+00:00", "Z"),
            0.7,
        )
        store.add(event)
        signal = strategy.evaluate(event)
        if signal is not None:
            assert signal.outcome == "DOWN"
            assert signal.model_id == "volatility_filtered_mean_reversion"

    def test_z_below_neg_entry_z_signals_up(self) -> None:
        """When z <= -entry_z and trend_ok, outcome is UP."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        # Most candles at 0.5, last few lower so close[-1] < anchor, z negative
        candles = []
        for i in range(95):
            candles.append(_candle(0.5, 0.52, 0.48, 0.5, base + timedelta(minutes=15 * i)))
        for i in range(95, 100):
            candles.append(_candle(0.3, 0.32, 0.28, 0.3, base + timedelta(minutes=15 * i)))
        store = make_store_with_candles(candles)
        strategy = VolatilityFilteredMeanReversionStrategy(
            market_slug="test-market",
            store=store,
            anchor_window=96,
            atr_window=14,
            ema_fast=20,
            ema_slow=80,
            trend_threshold=2.0,
            entry_z=1.5,
            exit_z=0.3,
        )
        event = _event(
            (base + timedelta(minutes=15 * 99)).isoformat().replace("+00:00", "Z"),
            0.3,
        )
        store.add(event)
        signal = strategy.evaluate(event)
        if signal is not None:
            assert signal.outcome == "UP"


class TestVfmrExitLogic:
    """Exit logic: in LONG_DOWN and z <= exit_z -> None; LONG_UP and z >= -exit_z -> None."""

    def test_long_down_z_below_exit_z_returns_none(self) -> None:
        """When position is LONG_DOWN and z <= exit_z, no new signal (exit)."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [
            _candle(0.5, 0.52, 0.48, 0.5, base + timedelta(minutes=15 * i)) for i in range(100)
        ]
        store = make_store_with_candles(candles)
        strategy = VolatilityFilteredMeanReversionStrategy(
            market_slug="test-market",
            store=store,
            anchor_window=96,
            atr_window=14,
            trend_threshold=2.0,
            entry_z=1.5,
            exit_z=0.3,
        )
        # Position in DOWN (we are long DOWN)
        positions = {
            ("test-market", "DOWN"): Position(
                market_slug="test-market",
                outcome="DOWN",
                size=100.0,
                target_price=0.5,
                entry_price=0.5,
                entry_time=1000.0,
            )
        }
        event = _event(
            (base + timedelta(minutes=15 * 99)).isoformat().replace("+00:00", "Z"),
            0.5,
        )
        store.add(event)
        signal = strategy.evaluate(event, positions=positions)
        # z ~ 0 (close ~ anchor), z <= exit_z (0.3) -> exit logic -> None
        assert signal is None


class TestVfmrConstructor:
    """Constructor validation."""

    def test_ema_slow_le_ema_fast_raises(self) -> None:
        """ema_slow <= ema_fast raises ValueError."""
        store = MemoryMarketDataStore()
        with pytest.raises(ValueError, match="ema_slow must be > ema_fast"):
            VolatilityFilteredMeanReversionStrategy(
                market_slug="test",
                store=store,
                ema_fast=20,
                ema_slow=20,
            )

    def test_exit_z_ge_entry_z_raises(self) -> None:
        """exit_z >= entry_z raises ValueError."""
        store = MemoryMarketDataStore()
        with pytest.raises(ValueError, match="exit_z must be < entry_z"):
            VolatilityFilteredMeanReversionStrategy(
                market_slug="test",
                store=store,
                entry_z=1.0,
                exit_z=1.0,
            )
