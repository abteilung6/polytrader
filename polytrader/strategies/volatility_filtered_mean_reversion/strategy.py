"""Volatility-Filtered Mean Reversion strategy implementation.

Per VFMR_STRATEGY_ROADMAP §4: regime gate, entry (UP/DOWN), exit (no signal when z
crosses exit_z). Uses only polytrader.indicators and polytrader.indicators.candles.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.indicators import (
    atr,
    deviation_z,
    fair_price_anchor,
    trend_strength_ema_gap,
)
from polytrader.indicators.candles import aggregate_ticks_to_candles
from polytrader.obs.metrics import record_strategy_eval, record_strategy_eval_latency
from polytrader.store import IMarketDataStore
from polytrader.strategies.base import IStrategy
from polytrader.types import Position


class WallClock(Protocol):
    """Protocol for wall-clock time (candle boundaries, throttle)."""

    def now(self) -> datetime:
        """Current UTC datetime."""
        ...


def _default_now() -> datetime:
    """Default now when no clock injected (production)."""
    return datetime.now(UTC)


class VolatilityFilteredMeanReversionStrategy(IStrategy):
    """Volatility-Filtered Mean Reversion: mean reversion with trend gate.

    Trades only when trend_strength <= trend_threshold. Entry: z >= entry_z -> DOWN;
    z <= -entry_z -> UP. Exit: no new signal when z crosses exit_z (close deferred).
    """

    def __init__(
        self,
        market_slug: str,
        store: IMarketDataStore,
        interval_minutes: int = 15,
        interval_seconds: int = 0,
        anchor_window: int = 96,
        atr_window: int = 14,
        ema_fast: int = 20,
        ema_slow: int = 80,
        trend_threshold: float = 0.5,
        entry_z: float = 1.5,
        exit_z: float = 0.3,
        risk_per_trade_pct: float = 0.25,
        max_position_notional_pct: float = 100.0,
        max_trades_per_hour: int = 4,
        cooldown_candles_after_loss: int = 1,
        clock: WallClock | None = None,
    ) -> None:
        """Initialize VFMR strategy.

        Args:
            market_slug: Market to trade
            store: Market data store for tick history
            interval_minutes: Candle interval in minutes (used when interval_seconds=0)
            interval_seconds: Candle interval in seconds (e.g. 5 for ~20s warmup); 0=use minutes
            anchor_window: Rolling window for fair-price anchor
            atr_window: ATR period
            ema_fast: EMA fast period for trend filter
            ema_slow: EMA slow period (must be > ema_fast)
            trend_threshold: Max trend_strength to allow trading
            entry_z: |z| >= entry_z to trigger entry
            exit_z: |z| <= exit_z to consider exit (must be < entry_z)
            risk_per_trade_pct: Risk per trade (0.05–1.0)
            max_position_notional_pct: Cap position size
            max_trades_per_hour: Throttle
            cooldown_candles_after_loss: Candles after loss (deferred v1)
            clock: Optional wall clock for throttle; None = datetime.now(UTC)
        """
        if ema_slow <= ema_fast:
            raise ValueError(
                f"ema_slow must be > ema_fast, got ema_slow={ema_slow} ema_fast={ema_fast}"
            )
        if exit_z >= entry_z:
            raise ValueError(f"exit_z must be < entry_z, got exit_z={exit_z} entry_z={entry_z}")
        if interval_seconds <= 0 and interval_minutes < 1:
            raise ValueError(
                f"interval_minutes must be >= 1 when interval_seconds=0, got {interval_minutes}"
            )
        if interval_seconds > 0 and interval_seconds < 1:
            raise ValueError(f"interval_seconds must be >= 1 when used, got {interval_seconds}")

        self.market_slug = market_slug
        self.store = store
        self.interval_minutes = interval_minutes
        self.interval_seconds = interval_seconds
        self.anchor_window = anchor_window
        self.atr_window = atr_window
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.trend_threshold = trend_threshold
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_position_notional_pct = max_position_notional_pct
        self.max_trades_per_hour = max_trades_per_hour
        self.cooldown_candles_after_loss = cooldown_candles_after_loss
        self._clock = clock
        self._signal_times: list[datetime] = []
        self._last_candle_ts_start: dict[tuple[str, str], datetime | None] = {}

    def _now(self) -> datetime:
        """Current UTC time (injected clock or default)."""
        if self._clock is not None:
            return self._clock.now()
        return _default_now()

    def _position_state(self, positions: dict[tuple[str, str], Position] | None) -> str:
        """Derive FLAT / LONG_UP / LONG_DOWN from positions."""
        if not positions:
            return "FLAT"
        key_up = (self.market_slug, "UP")
        key_down = (self.market_slug, "DOWN")
        if key_up in positions and positions[key_up].size > 0:
            return "LONG_UP"
        if key_down in positions and positions[key_down].size > 0:
            return "LONG_DOWN"
        return "FLAT"

    def _warmup_candles(self) -> int:
        """Minimum candles required before trading."""
        return max(self.anchor_window, self.atr_window, self.ema_slow)

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict[tuple[str, str], Position] | None = None,
    ) -> SignalEvent | None:
        """Evaluate market data and produce signal.

        Aggregates ticks to 15m candles, computes z and trend_strength via
        primitives, applies regime gate and entry/exit logic.
        """
        start_time = time.perf_counter()
        strategy_id = "volatility_filtered_mean_reversion"

        try:
            if market_data.market_slug != self.market_slug:
                return None

            history = self.store.history(market_data.market_slug, market_data.outcome)
            candles = aggregate_ticks_to_candles(
                history,
                interval_minutes=self.interval_minutes,
                interval_seconds=self.interval_seconds,
            )
            warmup = self._warmup_candles()
            n_candles = len(candles)

            if n_candles < warmup:
                return None

            high = [c.high for c in candles]
            low = [c.low for c in candles]
            close = [c.close for c in candles]

            vol_series = atr(high, low, close, self.atr_window)
            if not vol_series or vol_series[-1] <= 0:
                return None

            anchor_series = fair_price_anchor(
                candles, method="rolling_mean", window=self.anchor_window
            )
            trend_series = trend_strength_ema_gap(close, self.ema_fast, self.ema_slow, vol_series)

            z = deviation_z(close[-1], anchor_series[-1], vol_series[-1])
            trend_strength = trend_series[-1]
            trend_ok = trend_strength <= self.trend_threshold
            position_state = self._position_state(positions)

            # Exit logic: in position and z crossed exit_z -> no new signal
            if position_state == "LONG_DOWN" and z <= self.exit_z:
                return None
            if position_state == "LONG_UP" and z >= -self.exit_z:
                return None

            if not trend_ok:
                return None

            # Throttle: max_trades_per_hour
            now = self._now()
            cutoff = now - timedelta(hours=1)
            self._signal_times = [t for t in self._signal_times if t > cutoff]
            n_signals_last_hour = len(self._signal_times)
            if n_signals_last_hour >= self.max_trades_per_hour:
                return None

            # One signal per candle: deduplicate by last candle ts_start
            market_key = (market_data.market_slug, market_data.outcome)
            last_ts = candles[-1].ts_start
            if self._last_candle_ts_start.get(market_key) == last_ts:
                return None

            # Entry: FLAT only
            if position_state != "FLAT":
                return None

            outcome: str | None = None
            if z >= self.entry_z:
                outcome = "DOWN"
            elif z <= -self.entry_z:
                outcome = "UP"

            if outcome is None:
                return None

            # Probabilities: simple skew toward signaled outcome
            p_up = 0.2 if outcome == "DOWN" else 0.8
            p_down = 0.8 if outcome == "DOWN" else 0.2
            edge = abs(z) - self.exit_z
            confidence = min(abs(z) / max(self.entry_z, 1e-9), 1.0)

            signal = SignalEvent(
                market_slug=market_data.market_slug,
                outcome=outcome,
                p_up=p_up,
                p_down=p_down,
                edge=edge,
                confidence=confidence,
                model_id=strategy_id,
                model_version="1.0.0",
                rationale=(
                    f"z={z:.4f} trend_ok={trend_ok} trend_strength={trend_strength:.4f} "
                    f"anchor={anchor_series[-1]:.4f} atr={vol_series[-1]:.4f}"
                ),
                correlation_id=market_data.correlation_id,
            )

            self._signal_times.append(now)
            self._last_candle_ts_start[market_key] = last_ts

            return signal
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            record_strategy_eval(strategy_id=strategy_id)
            record_strategy_eval_latency(strategy_id=strategy_id, latency_ms=latency_ms)

    async def run(self) -> None:
        """Optional background tasks (not needed for v1)."""
        pass

    def stop(self) -> None:
        """Stop background tasks (not needed for v1)."""
        pass
