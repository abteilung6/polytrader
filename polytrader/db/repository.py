"""Repository pattern for event database operations using SQLAlchemy.

This module provides type-safe database operations using SQLAlchemy ORM.
Per architecture.mdc: Database operations are separated from business logic.
"""

import base64
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.db.models import EventRecord, MarketTickRecord

if TYPE_CHECKING:
    pass


class EventRepository:
    """Repository for event database operations.

    Provides type-safe CRUD operations using SQLAlchemy ORM.
    All type conversions (UUID, datetime, JSONB) are handled automatically.

    Example:
        >>> async with Session() as session:
        ...     repo = EventRepository(session)
        ...     await repo.create_event(...)
        ...     events = await repo.read_events(event_type="OrderCreatedEvent")
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_event(
        self,
        event_id: UUID,
        ts_wall: datetime,
        ts_mono: float,
        correlation_id: str | None,
        run_id: str,
        schema_version: str,
        source: str,
        event_type: str,
        event_data: dict[str, Any],
    ) -> None:
        """Insert event into database (idempotent).

        Type conversions are handled automatically by SQLAlchemy:
        - UUID: automatic conversion from UUID object
        - datetime: automatic conversion from datetime object
        - JSONB: automatic conversion from dict

        Args:
            event_id: Unique event identifier (UUID)
            ts_wall: Wall-clock time (datetime, UTC)
            ts_mono: Monotonic timestamp (float)
            correlation_id: Correlation ID (optional)
            run_id: Process run ID
            schema_version: Event schema version
            source: Event source (EventSource enum value as string)
            event_type: Event class name
            event_data: Event-specific fields (dict, automatically converted to JSONB)

        Note:
            Uses merge() for idempotency. Duplicate events (same event_id)
            are silently ignored.

        Example:
            >>> await repo.create_event(
            ...     event_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            ...     ts_wall=datetime.now(UTC),
            ...     ts_mono=12345.678,
            ...     correlation_id="corr-123",
            ...     run_id="run-456",
            ...     schema_version="1.0",
            ...     source="oms",
            ...     event_type="OrderCreatedEvent",
            ...     event_data={"order_id": "order-123"},
            ... )
        """
        # Use PostgreSQL-specific INSERT ... ON CONFLICT DO NOTHING for idempotency
        # This is equivalent to the old raw SQL approach but type-safe
        stmt = (
            insert(EventRecord)
            .values(
                event_id=event_id,
                ts_wall=ts_wall,
                ts_mono=ts_mono,
                correlation_id=correlation_id,
                run_id=run_id,
                schema_version=schema_version,
                source=source,
                event_type=event_type,
                event_data=event_data,
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
        )

        await self.session.execute(stmt)
        await self.session.commit()

    async def read_events(
        self,
        event_type: str | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
        correlation_id: str | None = None,
        limit: int | None = None,
    ) -> list[EventRecord]:
        """Read events from database with type-safe query building.

        Args:
            event_type: Filter by event type (class name)
            from_ts: Filter by ts_mono >= from_ts
            to_ts: Filter by ts_mono <= to_ts
            correlation_id: Filter by correlation_id
            limit: Maximum number of events to return (None = no limit)

        Returns:
            List of EventRecord objects (ORM models)

        Example:
            >>> events = await repo.read_events(
            ...     event_type="OrderCreatedEvent",
            ...     from_ts=1000.0,
            ...     to_ts=2000.0,
            ...     limit=10,
            ... )
        """
        query = select(EventRecord)
        conditions = []

        if event_type:
            conditions.append(EventRecord.event_type == event_type)
        if from_ts is not None:
            conditions.append(EventRecord.ts_mono >= from_ts)
        if to_ts is not None:
            conditions.append(EventRecord.ts_mono <= to_ts)
        if correlation_id:
            conditions.append(EventRecord.correlation_id == correlation_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(EventRecord.ts_mono, EventRecord.created_at)

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def read_signal_events_by_strategy(
        self,
        strategy_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[EventRecord], str | None]:
        """Read SignalEvent records for a strategy, newest-first, with cursor pagination.

        Filters by event_type=SignalEvent and event_data->>'model_id' = strategy_id.
        Order: ts_mono DESC, event_id DESC. Returns at most `limit` items (capped at 500)
        and an optional next_cursor for the following page.

        Args:
            strategy_id: Strategy/model identifier (model_id in SignalEvent)
            limit: Max items to return (default 100, max 500)
            cursor: Opaque cursor from previous response (optional)

        Returns:
            (records, next_cursor). next_cursor is set if there are more rows.
        """
        cap = min(max(1, limit), 500)
        conditions = [
            EventRecord.event_type == "SignalEvent",
            EventRecord.event_data["model_id"].astext == strategy_id,
        ]
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
                parts = decoded.split(":", 1)
                if len(parts) == 2:
                    cursor_ts = float(parts[0])
                    cursor_id = UUID(parts[1])
                    conditions.append(
                        or_(
                            EventRecord.ts_mono < cursor_ts,
                            (EventRecord.ts_mono == cursor_ts) & (EventRecord.event_id < cursor_id),
                        )
                    )
            except (ValueError, TypeError):
                pass  # Invalid cursor: ignore and return first page

        query = (
            select(EventRecord)
            .where(and_(*conditions))
            .order_by(desc(EventRecord.ts_mono), desc(EventRecord.event_id))
            .limit(cap + 1)
        )
        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > cap:
            rows = rows[:cap]
            last_returned = rows[-1]
            next_cursor = base64.urlsafe_b64encode(
                f"{last_returned.ts_mono}:{last_returned.event_id}".encode()
            ).decode()
        return (rows, next_cursor)

    async def read_order_events_by_strategy(
        self,
        strategy_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[EventRecord], str | None]:
        """Read OrderCreatedEvent records for a strategy, newest-first, with cursor pagination.

        Filters by event_type=OrderCreatedEvent and intent.strategy_id in event_data.
        Order: ts_mono DESC, event_id DESC. Returns at most `limit` items (capped at 500)
        and an optional next_cursor for the following page.

        Args:
            strategy_id: Strategy identifier (intent.strategy_id in OrderCreatedEvent)
            limit: Max items to return (default 100, max 500)
            cursor: Opaque cursor from previous response (optional)

        Returns:
            (records, next_cursor). next_cursor is set if there are more rows.
        """
        cap = min(max(1, limit), 500)
        conditions = [
            EventRecord.event_type == "OrderCreatedEvent",
            EventRecord.event_data["intent"]["strategy_id"].astext == strategy_id,
        ]
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
                parts = decoded.split(":", 1)
                if len(parts) == 2:
                    cursor_ts = float(parts[0])
                    cursor_id = UUID(parts[1])
                    conditions.append(
                        or_(
                            EventRecord.ts_mono < cursor_ts,
                            (EventRecord.ts_mono == cursor_ts) & (EventRecord.event_id < cursor_id),
                        )
                    )
            except (ValueError, TypeError):
                pass  # Invalid cursor: ignore and return first page

        query = (
            select(EventRecord)
            .where(and_(*conditions))
            .order_by(desc(EventRecord.ts_mono), desc(EventRecord.event_id))
            .limit(cap + 1)
        )
        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > cap:
            rows = rows[:cap]
            last_returned = rows[-1]
            next_cursor = base64.urlsafe_b64encode(
                f"{last_returned.ts_mono}:{last_returned.event_id}".encode()
            ).decode()
        return (rows, next_cursor)

    async def event_exists(self, event_id: UUID) -> bool:
        """Check if event with given event_id exists.

        Args:
            event_id: Event ID to check (UUID)

        Returns:
            True if event exists, False otherwise

        Example:
            >>> exists = await repo.event_exists(UUID("123e4567-..."))
            >>> assert isinstance(exists, bool)
        """
        query = select(EventRecord.event_id).where(EventRecord.event_id == event_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None


class IMarketTickRepository(Protocol):
    """Protocol for market tick repository implementations.

    Provides type-safe interface for market tick database operations.
    """

    async def create_tick(
        self,
        tick_id: UUID,
        ts_wall: datetime,
        ts_mono: float,
        market_slug: str,
        outcome: str,
        best_bid: Decimal,
        best_ask: Decimal,
        mid: Decimal,
        spread: Decimal,
        spread_bps: Decimal,
        event_id: UUID | None,
        run_id: str,
    ) -> None:
        """Insert single tick (idempotent)."""
        ...

    async def bulk_create_ticks(
        self,
        ticks: list[dict[str, Any]],
    ) -> int:
        """Bulk insert ticks (idempotent). Returns count inserted."""
        ...

    async def get_latest(
        self,
        market_slug: str,
        outcome: str,
    ) -> MarketTickRecord | None:
        """Get latest tick for market/outcome."""
        ...

    async def get_history(
        self,
        market_slug: str | None = None,
        outcome: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int | None = None,
    ) -> list[MarketTickRecord]:
        """Get historical ticks with filters."""
        ...

    async def get_markets(self) -> list[tuple[str, str]]:
        """Get all (market_slug, outcome) pairs with data."""
        ...

    async def tick_exists(self, tick_id: UUID, ts_wall: datetime) -> bool:
        """Check if tick exists."""
        ...


class MarketTickRepository:
    """Repository for market tick database operations.

    Provides type-safe CRUD operations using SQLAlchemy ORM.
    All type conversions (UUID, datetime, NUMERIC) are handled automatically.

    Example:
        >>> async with Session() as session:
        ...     repo = MarketTickRepository(session)
        ...     await repo.create_tick(...)
        ...     latest = await repo.get_latest("btc-updown-15m", "UP")
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_tick(
        self,
        tick_id: UUID,
        ts_wall: datetime,
        ts_mono: float,
        market_slug: str,
        outcome: str,
        best_bid: Decimal,
        best_ask: Decimal,
        mid: Decimal,
        spread: Decimal,
        spread_bps: Decimal,
        event_id: UUID | None,
        run_id: str,
    ) -> None:
        """Insert single tick into database (idempotent).

        Type conversions are handled automatically by SQLAlchemy:
        - UUID: automatic conversion from UUID object
        - datetime: automatic conversion from datetime object
        - NUMERIC: automatic conversion from Decimal

        Args:
            tick_id: Unique tick identifier (UUID)
            ts_wall: Wall-clock time (datetime, UTC)
            ts_mono: Monotonic timestamp (float)
            market_slug: Polymarket market identifier
            outcome: Market outcome ("UP" or "DOWN")
            best_bid: Best bid price (Decimal, 0-1 range)
            best_ask: Best ask price (Decimal, 0-1 range)
            mid: Mid-market price (Decimal)
            spread: Bid-ask spread (Decimal)
            spread_bps: Spread in basis points (Decimal)
            event_id: Reference to events.event_id (optional)
            run_id: Process run ID

        Note:
            Uses ON CONFLICT DO NOTHING for idempotency. Duplicate ticks
            (same tick_id and ts_wall) are silently ignored.

        Example:
            >>> from decimal import Decimal
            >>> await repo.create_tick(
            ...     tick_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            ...     ts_wall=datetime.now(UTC),
            ...     ts_mono=12345.678,
            ...     market_slug="btc-updown-15m",
            ...     outcome="UP",
            ...     best_bid=Decimal("0.45"),
            ...     best_ask=Decimal("0.50"),
            ...     mid=Decimal("0.475"),
            ...     spread=Decimal("0.05"),
            ...     spread_bps=Decimal("500.00"),
            ...     event_id=None,
            ...     run_id="run-456",
            ... )
        """
        # Use PostgreSQL-specific INSERT ... ON CONFLICT DO NOTHING for idempotency
        # Primary key is (tick_id, ts_wall)
        stmt = (
            insert(MarketTickRecord)
            .values(
                tick_id=tick_id,
                ts_wall=ts_wall,
                ts_mono=ts_mono,
                market_slug=market_slug,
                outcome=outcome,
                best_bid=best_bid,
                best_ask=best_ask,
                mid=mid,
                spread=spread,
                spread_bps=spread_bps,
                event_id=event_id,
                run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=["tick_id", "ts_wall"])
        )

        try:
            await self.session.execute(stmt)
            await self.session.commit()
        except Exception:
            # Rollback on error to prevent invalid transaction state
            await self.session.rollback()
            raise

    async def bulk_create_ticks(
        self,
        ticks: list[dict[str, Any]],
    ) -> int:
        """Bulk insert ticks (idempotent).

        Args:
            ticks: List of tick dictionaries. Each dict must contain:
                - tick_id: UUID
                - ts_wall: datetime
                - ts_mono: float
                - market_slug: str
                - outcome: str
                - best_bid: Decimal
                - best_ask: Decimal
                - mid: Decimal
                - spread: Decimal
                - spread_bps: Decimal
                - event_id: UUID | None
                - run_id: str

                Note: This accepts dict for SQLAlchemy compatibility.
                Use TickDbFields.model_dump() to convert typed models to dict.

        Returns:
            Number of ticks actually inserted (duplicates are ignored)

        Example:
            >>> from polytrader.db.tick_writer import TickDbFields
            >>> from datetime import UTC, datetime
            >>> ticks = [
            ...     TickDbFields(
            ...         tick_id=UUID("..."),
            ...         ts_wall=datetime.now(UTC),
            ...         ts_mono=12345.678,
            ...         market_slug="btc-updown-15m",
            ...         outcome="UP",
            ...         best_bid=Decimal("0.45"),
            ...         best_ask=Decimal("0.50"),
            ...         mid=Decimal("0.475"),
            ...         spread=Decimal("0.05"),
            ...         spread_bps=Decimal("500.00"),
            ...         event_id=None,
            ...         run_id="run-456",
            ...     ),
            ... ]
            >>> ticks_dicts = [tick.model_dump() for tick in ticks]
            >>> count = await repo.bulk_create_ticks(ticks_dicts)
            >>> assert count >= 0
        """
        if not ticks:
            return 0

        # Use bulk insert with ON CONFLICT DO NOTHING
        # Use RETURNING to get actual count of inserted rows
        # (rowcount returns -1 for ON CONFLICT DO NOTHING in async SQLAlchemy)
        stmt = (
            insert(MarketTickRecord)
            .values(ticks)
            .on_conflict_do_nothing(index_elements=["tick_id", "ts_wall"])
            .returning(MarketTickRecord.tick_id)
        )

        try:
            result = await self.session.execute(stmt)
            await self.session.commit()

            # Count returned rows (these are the actually inserted rows)
            inserted_rows = result.fetchall()
            return len(inserted_rows)
        except Exception:
            # Rollback on error to prevent invalid transaction state
            try:
                await self.session.rollback()
            except Exception:
                # If rollback fails, session is likely already closed/invalid
                pass
            raise

    async def get_latest(
        self,
        market_slug: str,
        outcome: str,
    ) -> MarketTickRecord | None:
        """Get latest tick for market/outcome.

        Args:
            market_slug: Polymarket market identifier
            outcome: Market outcome ("UP" or "DOWN")

        Returns:
            Latest MarketTickRecord, or None if no ticks exist

        Example:
            >>> latest = await repo.get_latest("btc-updown-15m", "UP")
            >>> if latest:
            ...     print(f"Latest price: {latest.mid}")
        """
        query = (
            select(MarketTickRecord)
            .where(
                and_(
                    MarketTickRecord.market_slug == market_slug,
                    MarketTickRecord.outcome == outcome,
                )
            )
            .order_by(desc(MarketTickRecord.ts_wall), desc(MarketTickRecord.ts_mono))
            .limit(1)
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_history(
        self,
        market_slug: str | None = None,
        outcome: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int | None = None,
    ) -> list[MarketTickRecord]:
        """Get historical ticks with filters.

        Args:
            market_slug: Filter by market slug (optional)
            outcome: Filter by outcome (optional)
            from_ts: Filter by ts_wall >= from_ts (optional)
            to_ts: Filter by ts_wall <= to_ts (optional)
            limit: Maximum number of ticks to return (None = no limit)

        Returns:
            List of MarketTickRecord objects, ordered by ts_wall ASC, ts_mono ASC

        Example:
            >>> from datetime import datetime, timedelta, UTC
            >>> now = datetime.now(UTC)
            >>> hour_ago = now - timedelta(hours=1)
            >>> ticks = await repo.get_history(
            ...     market_slug="btc-updown-15m",
            ...     outcome="UP",
            ...     from_ts=hour_ago,
            ...     to_ts=now,
            ...     limit=100,
            ... )
        """
        query = select(MarketTickRecord)
        conditions = []

        if market_slug:
            conditions.append(MarketTickRecord.market_slug == market_slug)
        if outcome:
            conditions.append(MarketTickRecord.outcome == outcome)
        if from_ts is not None:
            conditions.append(MarketTickRecord.ts_wall >= from_ts)
        if to_ts is not None:
            conditions.append(MarketTickRecord.ts_wall <= to_ts)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(MarketTickRecord.ts_wall, MarketTickRecord.ts_mono)

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_markets(self) -> list[tuple[str, str]]:
        """Get all (market_slug, outcome) pairs that have data.

        Returns:
            List of (market_slug, outcome) tuples

        Example:
            >>> markets = await repo.get_markets()
            >>> for market_slug, outcome in markets:
            ...     print(f"{market_slug}/{outcome}")
        """
        query = select(
            MarketTickRecord.market_slug,
            MarketTickRecord.outcome,
        ).distinct()

        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def tick_exists(self, tick_id: UUID, ts_wall: datetime) -> bool:
        """Check if tick with given tick_id and ts_wall exists.

        Args:
            tick_id: Tick ID to check (UUID)
            ts_wall: Wall-clock time to check (datetime)

        Returns:
            True if tick exists, False otherwise

        Example:
            >>> exists = await repo.tick_exists(
            ...     UUID("123e4567-..."),
            ...     datetime.now(UTC)
            ... )
        """
        query = select(MarketTickRecord.tick_id).where(
            and_(
                MarketTickRecord.tick_id == tick_id,
                MarketTickRecord.ts_wall == ts_wall,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None
