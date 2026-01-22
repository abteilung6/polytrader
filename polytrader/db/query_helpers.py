"""Query utilities for market tick data.

Per architecture: Query utilities are pure functions (no side effects).
This module provides common queries for historical analysis and backtesting.

Per architecture: Query utilities leverage existing indexes (BRIN on ts_wall).
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from polytrader.db.models import MarketTickRecord
    from polytrader.db.repository import MarketTickRepository


class PriceStatistics(BaseModel):
    """Price statistics for a time range.

    Per architecture: Query utilities return typed models.

    Attributes:
        min_price: Minimum price in range
        max_price: Maximum price in range
        avg_price: Average price in range
        first_price: First price in range
        last_price: Last price in range
        tick_count: Number of ticks in range
    """

    min_price: Decimal = Field(description="Minimum price in range")
    max_price: Decimal = Field(description="Maximum price in range")
    avg_price: Decimal = Field(description="Average price in range")
    first_price: Decimal = Field(description="First price in range (oldest)")
    last_price: Decimal = Field(description="Last price in range (newest)")
    tick_count: int = Field(description="Number of ticks in range")


async def get_ticks_in_range(
    repository: "MarketTickRepository",
    market_slug: str,
    outcome: str,
    from_ts: datetime,
    to_ts: datetime,
    limit: int | None = None,
) -> list["MarketTickRecord"]:
    """Get ticks in time range (inclusive).

    Per architecture: Query utilities are pure functions.

    Args:
        repository: MarketTickRepository instance
        market_slug: Market identifier
        outcome: Market outcome ("UP" or "DOWN")
        from_ts: Start time (inclusive)
        to_ts: End time (inclusive)
        limit: Maximum number of ticks to return (None for no limit)

    Returns:
        List of MarketTickRecord objects (ordered by ts_wall, ts_mono ascending)

    Example:
        >>> from datetime import datetime, UTC, timedelta
        >>> to_ts = datetime.now(UTC)
        >>> from_ts = to_ts - timedelta(hours=1)
        >>> ticks = await get_ticks_in_range(
        ...     repo, "btc-updown-15m", "UP", from_ts, to_ts
        ... )
        >>> assert len(ticks) > 0
    """
    return await repository.get_history(
        market_slug=market_slug,
        outcome=outcome,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


async def get_tick_count(
    repository: "MarketTickRepository",
    market_slug: str,
    outcome: str,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> int:
    """Get count of ticks in time range.

    Per architecture: Query utilities are pure functions.

    Args:
        repository: MarketTickRepository instance
        market_slug: Market identifier
        outcome: Market outcome ("UP" or "DOWN")
        from_ts: Start time (inclusive, None for no lower bound)
        to_ts: End time (inclusive, None for no upper bound)

    Returns:
        Number of ticks in range

    Example:
        >>> count = await get_tick_count(repo, "btc-updown-15m", "UP")
        >>> assert count >= 0
    """
    from sqlalchemy import and_, func, select

    from polytrader.db.models import MarketTickRecord

    # Build query
    conditions = [
        MarketTickRecord.market_slug == market_slug,
        MarketTickRecord.outcome == outcome,
    ]

    if from_ts is not None:
        conditions.append(MarketTickRecord.ts_wall >= from_ts)
    if to_ts is not None:
        conditions.append(MarketTickRecord.ts_wall <= to_ts)

    query = select(func.count(MarketTickRecord.tick_id)).where(and_(*conditions))

    result = await repository.session.execute(query)
    count = result.scalar_one()
    return count


async def get_price_statistics(
    repository: "MarketTickRepository",
    market_slug: str,
    outcome: str,
    from_ts: datetime,
    to_ts: datetime,
) -> PriceStatistics:
    """Get price statistics for a time range.

    Per architecture: Query utilities return typed models.

    Args:
        repository: MarketTickRepository instance
        market_slug: Market identifier
        outcome: Market outcome ("UP" or "DOWN")
        from_ts: Start time (inclusive)
        to_ts: End time (inclusive)

    Returns:
        PriceStatistics with min/max/avg/first/last prices and tick count

    Example:
        >>> from datetime import datetime, UTC, timedelta
        >>> to_ts = datetime.now(UTC)
        >>> from_ts = to_ts - timedelta(hours=1)
        >>> stats = await get_price_statistics(
        ...     repo, "btc-updown-15m", "UP", from_ts, to_ts
        ... )
        >>> assert stats.min_price <= stats.max_price
        >>> assert stats.tick_count > 0
    """
    from sqlalchemy import and_, func, select

    from polytrader.db.models import MarketTickRecord

    # Build query for statistics
    conditions = [
        MarketTickRecord.market_slug == market_slug,
        MarketTickRecord.outcome == outcome,
        MarketTickRecord.ts_wall >= from_ts,
        MarketTickRecord.ts_wall <= to_ts,
    ]

    # Aggregate query
    stats_query = select(
        func.min(MarketTickRecord.mid).label("min_price"),
        func.max(MarketTickRecord.mid).label("max_price"),
        func.avg(MarketTickRecord.mid).label("avg_price"),
        func.count(MarketTickRecord.tick_id).label("tick_count"),
    ).where(and_(*conditions))

    result = await repository.session.execute(stats_query)
    stats_row = result.one()

    # Get first and last prices (separate queries for ordering)
    first_query = (
        select(MarketTickRecord.mid)
        .where(and_(*conditions))
        .order_by(MarketTickRecord.ts_wall.asc(), MarketTickRecord.ts_mono.asc())
        .limit(1)
    )

    last_query = (
        select(MarketTickRecord.mid)
        .where(and_(*conditions))
        .order_by(MarketTickRecord.ts_wall.desc(), MarketTickRecord.ts_mono.desc())
        .limit(1)
    )

    first_result = await repository.session.execute(first_query)
    last_result = await repository.session.execute(last_query)

    first_price = first_result.scalar_one_or_none()
    last_price = last_result.scalar_one_or_none()

    # Handle empty range
    if stats_row.tick_count == 0:
        return PriceStatistics(
            min_price=Decimal("0"),
            max_price=Decimal("0"),
            avg_price=Decimal("0"),
            first_price=Decimal("0"),
            last_price=Decimal("0"),
            tick_count=0,
        )

    return PriceStatistics(
        min_price=stats_row.min_price or Decimal("0"),
        max_price=stats_row.max_price or Decimal("0"),
        avg_price=stats_row.avg_price or Decimal("0"),
        first_price=first_price or Decimal("0"),
        last_price=last_price or Decimal("0"),
        tick_count=stats_row.tick_count or 0,
    )


async def get_latest_ticks_by_market(
    repository: "MarketTickRepository",
    limit_per_market: int = 1,
) -> dict[tuple[str, str], "MarketTickRecord"]:
    """Get latest ticks for each market/outcome pair.

    Per architecture: Query utilities are pure functions.

    Args:
        repository: MarketTickRepository instance
        limit_per_market: Number of latest ticks per market/outcome (default: 1)

    Returns:
        Dictionary mapping (market_slug, outcome) -> MarketTickRecord
        Only includes markets that have data

    Example:
        >>> latest = await get_latest_ticks_by_market(repo, limit_per_market=1)
        >>> assert ("btc-updown-15m", "UP") in latest
        >>> tick = latest[("btc-updown-15m", "UP")]
        >>> assert tick.market_slug == "btc-updown-15m"
    """
    from sqlalchemy import and_, desc, select

    from polytrader.db.models import MarketTickRecord

    # Get all unique market/outcome pairs
    markets = await repository.get_markets()

    result: dict[tuple[str, str], MarketTickRecord] = {}

    # For each market/outcome, get latest ticks
    for market_slug, outcome in markets:
        query = (
            select(MarketTickRecord)
            .where(
                and_(
                    MarketTickRecord.market_slug == market_slug,
                    MarketTickRecord.outcome == outcome,
                )
            )
            .order_by(desc(MarketTickRecord.ts_wall), desc(MarketTickRecord.ts_mono))
            .limit(limit_per_market)
        )

        query_result = await repository.session.execute(query)
        ticks = query_result.scalars().all()

        if ticks:
            # Store the latest tick (first in result)
            result[(market_slug, outcome)] = ticks[0]

    return result
