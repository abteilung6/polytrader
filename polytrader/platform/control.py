"""Control plane repositories.

Provides type-safe operations for execution control, live strategy activation,
and control command queue using SQLAlchemy ORM.

Per architecture.mdc: Database operations are separated from business logic.
Per Platform_Proposal.md: These repositories support the control plane service
that manages execution state and strategy activation.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.db.models import (
    ControlCommandRecord,
    ExecutionControlRecord,
    LiveStrategyActivationRecord,
)


class ExecutionControlRepository:
    """Repository for execution control operations.

    Provides type-safe operations for execution control singleton.
    Supports optimistic concurrency control via version field.

    Example:
        >>> async with Session() as session:
        ...     repo = ExecutionControlRepository(session)
        ...     control = await repo.get_control()
        ...     updated = await repo.update_control(
        ...         execution_enabled=True,
        ...         updated_by="operator",
        ...         reason="Enable for testing"
        ...     )
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_control(self) -> ExecutionControlRecord:
        """Get execution control singleton record.

        Returns:
            ExecutionControlRecord with current state and version

        Raises:
            RuntimeError: If execution_control record does not exist
                (should never happen if migrations ran correctly)

        Example:
            >>> control = await repo.get_control()
            >>> print(f"Execution enabled: {control.execution_enabled}, version: {control.version}")
        """
        query = select(ExecutionControlRecord).where(ExecutionControlRecord.id == 1)
        result = await self.session.execute(query)
        record = result.scalar_one_or_none()

        if record is None:
            raise RuntimeError(
                "execution_control record not found. "
                "This should never happen if migrations ran correctly."
            )

        return record

    async def update_control(
        self,
        execution_enabled: bool,
        updated_by: str,
        reason: str,
    ) -> ExecutionControlRecord:
        """Update execution control state.

        Increments version field for optimistic concurrency control.
        Updates updated_at timestamp automatically.

        Args:
            execution_enabled: New execution enabled state
            updated_by: User/system making the update
            reason: Reason for the update

        Returns:
            Updated ExecutionControlRecord with new version

        Example:
            >>> updated = await repo.update_control(
            ...     execution_enabled=True,
            ...     updated_by="operator",
            ...     reason="Enable for live trading"
            ... )
            >>> assert updated.version == 2  # Version incremented
        """
        # Get current record to read version
        current = await self.get_control()

        # Update with version increment
        current.execution_enabled = execution_enabled
        current.version = current.version + 1
        current.updated_by = updated_by
        current.reason = reason
        current.updated_at = datetime.now(UTC)

        await self.session.commit()
        return current


class LiveStrategyRepository:
    """Repository for live strategy activation operations.

    Provides type-safe operations for managing which strategies are active
    for live trading.

    Example:
        >>> async with Session() as session:
        ...     repo = LiveStrategyRepository(session)
        ...     await repo.activate("simple_threshold", "operator", "Enable for testing")
        ...     active = await repo.list_active()
        ...     assert "simple_threshold" in active
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def list_active(self) -> set[str]:
        """List all active strategy IDs.

        Returns:
            Set of strategy_id strings that are active for live trading

        Example:
            >>> active = await repo.list_active()
            >>> if "simple_threshold" in active:
            ...     print("Strategy is active for live trading")
        """
        query = select(LiveStrategyActivationRecord.strategy_id).where(
            LiveStrategyActivationRecord.active == True  # noqa: E712
        )
        result = await self.session.execute(query)
        return {row[0] for row in result.all()}

    async def activate(
        self,
        strategy_id: str,
        activated_by: str,
        reason: str,
    ) -> None:
        """Activate strategy for live trading.

        Creates or updates live_strategy_activation record to set active=true.
        Sets activated_at timestamp and audit fields.

        Args:
            strategy_id: Strategy identifier (must exist in strategies table)
            activated_by: User/system activating the strategy
            reason: Reason for activation

        Raises:
            sqlalchemy.exc.IntegrityError: If strategy_id does not exist in strategies table

        Example:
            >>> await repo.activate(
            ...     "simple_threshold",
            ...     "operator",
            ...     "Enable for live trading after paper testing"
            ... )
        """
        now = datetime.now(UTC)

        # Use INSERT ... ON CONFLICT UPDATE for idempotency
        stmt = (
            insert(LiveStrategyActivationRecord)
            .values(
                strategy_id=strategy_id,
                active=True,
                activated_at=now,
                activated_by=activated_by,
                reason=reason,
            )
            .on_conflict_do_update(
                index_elements=["strategy_id"],
                set_={
                    "active": True,
                    "activated_at": now,
                    "activated_by": activated_by,
                    "reason": reason,
                    "updated_at": now,
                },
            )
        )

        await self.session.execute(stmt)
        await self.session.commit()

    async def deactivate(
        self,
        strategy_id: str,
        activated_by: str,
        reason: str,
    ) -> None:
        """Deactivate strategy for live trading.

        Updates live_strategy_activation record to set active=false.
        Clears activated_at timestamp but preserves audit fields.

        Args:
            strategy_id: Strategy identifier
            activated_by: User/system deactivating the strategy
            reason: Reason for deactivation

        Example:
            >>> await repo.deactivate(
            ...     "simple_threshold",
            ...     "operator",
            ...     "Disable due to poor performance"
            ... )
        """
        query = select(LiveStrategyActivationRecord).where(
            LiveStrategyActivationRecord.strategy_id == strategy_id
        )
        result = await self.session.execute(query)
        record = result.scalar_one_or_none()

        if record is None:
            # Create record with active=false (strategy was never activated)
            record = LiveStrategyActivationRecord(
                strategy_id=strategy_id,
                active=False,
                activated_at=None,
                activated_by=None,
                reason=None,
            )
            self.session.add(record)
        else:
            # Update existing record
            record.active = False
            record.activated_at = None
            record.activated_by = activated_by
            record.reason = reason
            record.updated_at = datetime.now(UTC)

        await self.session.commit()


class ControlCommandRepository:
    """Repository for control command queue operations.

    Provides type-safe operations for control command queue.
    Supports idempotency via client_request_id and optimistic concurrency
    control via expected_version.

    Example:
        >>> async with Session() as session:
        ...     repo = ControlCommandRepository(session)
        ...     command_id = await repo.create_command(command_record)
        ...     pending = await repo.list_pending()
        ...     await repo.mark_applied(command_id)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_command(self, cmd: ControlCommandRecord) -> str:
        """Create new control command in queue.

        Args:
            cmd: ControlCommandRecord to create (command_id will be generated if not set)

        Returns:
            Command ID (UUID as string)

        Raises:
            sqlalchemy.exc.IntegrityError: If idempotency constraint violated
                (same command_type, strategy_id, client_request_id already exists)

        Example:
            >>> from polytrader.db.models import ControlCommandRecord
            >>> cmd = ControlCommandRecord(
            ...     command_type="enable_execution",
            ...     reason="Enable for testing",
            ...     issued_by="operator",
            ...     client_request_id="req-123",
            ... )
            >>> command_id = await repo.create_command(cmd)
        """
        self.session.add(cmd)
        await self.session.commit()
        return str(cmd.command_id)

    async def find_by_client_request_id(
        self,
        command_type: str,
        strategy_id: str | None,
        client_request_id: str,
    ) -> ControlCommandRecord | None:
        """Find command by idempotency key.

        Used to check if a command with the same idempotency key already exists.
        This enables idempotent command creation.

        Args:
            command_type: Command type
            strategy_id: Strategy ID (None for enable/disable commands)
            client_request_id: Client request ID for idempotency

        Returns:
            ControlCommandRecord if found, None otherwise

        Example:
            >>> existing = await repo.find_by_client_request_id(
            ...     "enable_execution",
            ...     None,
            ...     "req-123"
            ... )
            >>> if existing:
            ...     print(f"Command already exists: {existing.command_id}")
        """
        conditions = [
            ControlCommandRecord.command_type == command_type,
            ControlCommandRecord.client_request_id == client_request_id,
        ]

        if strategy_id is None:
            conditions.append(ControlCommandRecord.strategy_id.is_(None))
        else:
            conditions.append(ControlCommandRecord.strategy_id == strategy_id)

        query = select(ControlCommandRecord).where(and_(*conditions))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_pending(self) -> list[ControlCommandRecord]:
        """List all pending commands.

        Returns:
            List of ControlCommandRecord objects with status='pending',
            ordered by created_at ASC

        Example:
            >>> pending = await repo.list_pending()
            >>> for cmd in pending:
            ...     print(f"{cmd.command_type}: {cmd.reason}")
        """
        query = (
            select(ControlCommandRecord)
            .where(ControlCommandRecord.status == "pending")
            .order_by(ControlCommandRecord.created_at)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_applied(self, command_id: str) -> None:
        """Mark command as applied.

        Updates status to 'applied' and sets applied_at timestamp.

        Args:
            command_id: Command ID (UUID as string)

        Raises:
            ValueError: If command_id not found

        Example:
            >>> await repo.mark_applied("123e4567-e89b-12d3-a456-426614174000")
        """
        cmd_uuid = UUID(command_id)
        query = select(ControlCommandRecord).where(ControlCommandRecord.command_id == cmd_uuid)
        result = await self.session.execute(query)
        record = result.scalar_one_or_none()

        if record is None:
            raise ValueError(f"Command not found: {command_id}")

        record.status = "applied"
        record.applied_at = datetime.now(UTC)
        await self.session.commit()

    async def get_command(self, command_id: str) -> ControlCommandRecord | None:
        """Get command by ID.

        Args:
            command_id: Command ID (UUID as string)

        Returns:
            ControlCommandRecord if found, None otherwise

        Example:
            >>> cmd = await repo.get_command("123e4567-e89b-12d3-a456-426614174000")
            >>> if cmd:
            ...     print(f"Status: {cmd.status}")
        """
        try:
            cmd_uuid = UUID(command_id)
        except ValueError:
            return None

        query = select(ControlCommandRecord).where(ControlCommandRecord.command_id == cmd_uuid)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def mark_failed(self, command_id: str, error_message: str) -> None:
        """Mark command as failed.

        Updates status to 'failed' and sets error_message.

        Args:
            command_id: Command ID (UUID as string)
            error_message: Error message describing the failure

        Raises:
            ValueError: If command_id not found

        Example:
            >>> await repo.mark_failed(
            ...     "123e4567-e89b-12d3-a456-426614174000",
            ...     "Health gates failed"
            ... )
        """
        cmd_uuid = UUID(command_id)
        query = select(ControlCommandRecord).where(ControlCommandRecord.command_id == cmd_uuid)
        result = await self.session.execute(query)
        record = result.scalar_one_or_none()

        if record is None:
            raise ValueError(f"Command not found: {command_id}")

        record.status = "failed"
        record.error_message = error_message
        await self.session.commit()
