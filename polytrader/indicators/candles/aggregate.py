"""Aggregate tick-level MarketDataEvents into OHLC candles.

Pure function: no I/O, no system clock. Uses event ts_wall for bucketing.
Per VFMR roadmap Commit 2: deterministic; reusable for strategy-internal aggregation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from polytrader.indicators.candles.models import Candle

if TYPE_CHECKING:
    from polytrader.events.types import MarketDataEvent


def _parse_ts_wall(ts_wall: str) -> datetime:
    """Parse ISO ts_wall to datetime (UTC).

    Handles 'Z' suffix for compatibility.
    """
    normalized = ts_wall.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _truncate_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    """Truncate datetime to interval boundary (e.g. 15m)."""
    total_minutes = dt.hour * 60 + dt.minute
    truncated = (total_minutes // interval_minutes) * interval_minutes
    return dt.replace(
        hour=truncated // 60,
        minute=truncated % 60,
        second=0,
        microsecond=0,
    )


def aggregate_ticks_to_candles(
    events: list[MarketDataEvent],
    interval_minutes: int = 15,
) -> list[Candle]:
    """Convert tick-level market data events into OHLC candles.

    Events are sorted by ts_wall for determinism, then grouped by interval.
    For each bucket: open=first mid, high=max(mid), low=min(mid), close=last mid.
    Uses event ts_wall only (no system clock).

    Args:
        events: List of MarketDataEvent (e.g. from store.history()). Assumed
            single market/outcome when called by strategy.
        interval_minutes: Candle interval in minutes (default 15).

    Returns:
        List of Candle sorted by ts_start; empty if no events or interval < 1.

    Note:
        Pure function; deterministic. Empty list returns [].
    """
    if interval_minutes < 1:
        raise ValueError(f"interval_minutes must be >= 1, got {interval_minutes}")
    if not events:
        return []

    # Sort by ts_wall for deterministic grouping
    sorted_events = sorted(events, key=lambda e: e.ts_wall)

    # Group by truncated interval start
    buckets: dict[datetime, list[MarketDataEvent]] = defaultdict(list)
    for event in sorted_events:
        dt = _parse_ts_wall(event.ts_wall)
        bucket_start = _truncate_to_interval(dt, interval_minutes)
        buckets[bucket_start].append(event)

    # Build OHLC per bucket
    candles: list[Candle] = []
    for ts_start in sorted(buckets.keys()):
        group = buckets[ts_start]
        mids = [e.mid for e in group]
        candles.append(
            Candle(
                open=mids[0],
                high=max(mids),
                low=min(mids),
                close=mids[-1],
                ts_start=ts_start,
            )
        )
    return candles
