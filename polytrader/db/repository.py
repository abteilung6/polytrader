"""Repository pattern for event database operations using SQLAlchemy.

This module provides type-safe database operations using SQLAlchemy ORM.
Per architecture.mdc: Database operations are separated from business logic.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.db.models import ControlCommandRecord, EventRecord, PlatformStateRecord, StrategyRecord


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


class StrategyRepository:
    """Repository for strategy registry operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_strategy(
        self,
        strategy_id: str,
        name: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        """Insert or update a strategy record."""
        config = config or {}
        stmt = (
            insert(StrategyRecord)
            .values(
                strategy_id=strategy_id,
                name=name,
                description=description,
                config=config,
                enabled=enabled,
            )
            .on_conflict_do_update(
                index_elements=["strategy_id"],
                set_={
                    "name": name,
                    "description": description,
                    "config": config,
                    "enabled": enabled,
                    "updated_at": func.now(),
                },
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def list_strategies(self) -> list[StrategyRecord]:
        """List all strategies."""
        result = await self.session.execute(select(StrategyRecord).order_by(StrategyRecord.strategy_id))
        return list(result.scalars().all())

    async def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        """Get a strategy by id."""
        result = await self.session.execute(
            select(StrategyRecord).where(StrategyRecord.strategy_id == strategy_id)
        )
        return result.scalar_one_or_none()


class PlatformStateRepository:
    """Repository for platform state (active strategy, execution)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_state(self) -> PlatformStateRecord:
        """Get platform state, create default if missing."""
        result = await self.session.execute(
            select(PlatformStateRecord).where(PlatformStateRecord.id == 1)
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = PlatformStateRecord(id=1, execution_enabled=False)
            self.session.add(state)
            await self.session.commit()
        return state

    async def set_active_strategy(
        self, strategy_id: str | None, updated_by: str | None = None, reason: str | None = None
    ) -> None:
        """Set active strategy id."""
        await self.get_state()
        stmt = (
            update(PlatformStateRecord)
            .where(PlatformStateRecord.id == 1)
            .values(
                active_strategy_id=strategy_id,
                updated_by=updated_by,
                reason=reason,
                updated_at=func.now(),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def set_execution_enabled(
        self, enabled: bool, updated_by: str | None = None, reason: str | None = None
    ) -> None:
        """Set execution enabled flag."""
        await self.get_state()
        stmt = (
            update(PlatformStateRecord)
            .where(PlatformStateRecord.id == 1)
            .values(
                execution_enabled=enabled,
                updated_by=updated_by,
                reason=reason,
                updated_at=func.now(),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()


class ControlCommandRepository:
    """Repository for control command queue."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_command(
        self,
        command_id: UUID,
        command_type: str,
        strategy_id: str | None,
        reason: str | None,
        issued_by: str,
    ) -> None:
        record = ControlCommandRecord(
            command_id=command_id,
            command_type=command_type,
            strategy_id=strategy_id,
            reason=reason,
            issued_by=issued_by,
            status="pending",
        )
        self.session.add(record)
        await self.session.commit()

    async def read_pending(self, limit: int = 50) -> list[ControlCommandRecord]:
        result = await self.session.execute(
            select(ControlCommandRecord)
            .where(ControlCommandRecord.status == "pending")
            .order_by(ControlCommandRecord.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_applied(self, command_id: UUID | str) -> None:
        if isinstance(command_id, str):
            command_id = UUID(command_id)
        stmt = (
            update(ControlCommandRecord)
            .where(ControlCommandRecord.command_id == command_id)
            .values(status="applied", applied_at=func.now())
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def mark_failed(self, command_id: UUID | str, error_message: str) -> None:
        if isinstance(command_id, str):
            command_id = UUID(command_id)
        stmt = (
            update(ControlCommandRecord)
            .where(ControlCommandRecord.command_id == command_id)
            .values(status="failed", applied_at=func.now(), error_message=error_message)
        )
        await self.session.execute(stmt)
        await self.session.commit()
