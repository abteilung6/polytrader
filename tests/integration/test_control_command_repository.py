"""Integration tests for ControlCommandRepository.

Tests verify that ControlCommandRepository provides correct operations
for control command queue using real database.
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import ControlCommandRecord, StrategyRecord
from polytrader.platform.control import ControlCommandRepository


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    # Convert URL to SQLAlchemy async format
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def repository(db_session: AsyncSession) -> ControlCommandRepository:
    """Create ControlCommandRepository for testing."""
    return ControlCommandRepository(db_session)


@pytest.fixture
async def test_strategy(db_session: AsyncSession) -> str:
    """Create test strategy and return its ID."""
    strategy = StrategyRecord(
        strategy_id="test_strategy",
        name="Test Strategy",
        config={"type": "simple_threshold"},
        enabled=True,
    )
    db_session.add(strategy)
    await db_session.commit()
    return strategy.strategy_id


class TestCreateCommand:
    """Test create_command() method."""

    @pytest.mark.asyncio
    async def test_create_command_creates_command_with_status_pending(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that create_command() creates command with status='pending'."""
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable for testing",
            issued_by="operator",
            client_request_id="req-123",
        )

        command_id = await repository.create_command(cmd)

        assert command_id is not None
        assert cmd.status == "pending"
        assert cmd.command_id == UUID(command_id)

    @pytest.mark.asyncio
    async def test_create_command_with_strategy_id(
        self,
        repository: ControlCommandRepository,
        test_strategy: str,
    ) -> None:
        """Test that create_command() works with strategy_id."""
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id=test_strategy,
            reason="Add strategy to active set",
            issued_by="operator",
            client_request_id="req-456",
        )

        command_id = await repository.create_command(cmd)
        assert command_id is not None


class TestFindByClientRequestId:
    """Test find_by_client_request_id() method."""

    @pytest.mark.asyncio
    async def test_find_by_client_request_id_finds_existing_command(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that find_by_client_request_id() finds existing command."""
        # Create command
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable for testing",
            issued_by="operator",
            client_request_id="req-find-test",
        )
        await repository.create_command(cmd)

        # Find command
        found = await repository.find_by_client_request_id(
            "enable_execution",
            None,
            "req-find-test",
        )

        assert found is not None
        assert found.command_id == cmd.command_id
        assert found.client_request_id == "req-find-test"

    @pytest.mark.asyncio
    async def test_find_by_client_request_id_returns_none_for_non_existent(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that find_by_client_request_id() returns None for non-existent."""
        found = await repository.find_by_client_request_id(
            "enable_execution",
            None,
            "req-non-existent",
        )

        assert found is None

    @pytest.mark.asyncio
    async def test_find_by_client_request_id_with_strategy_id(
        self,
        repository: ControlCommandRepository,
        test_strategy: str,
    ) -> None:
        """Test that find_by_client_request_id() works with strategy_id."""
        # Create command with strategy_id
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id=test_strategy,
            reason="Add strategy",
            issued_by="operator",
            client_request_id="req-strategy-test",
        )
        await repository.create_command(cmd)

        # Find command
        found = await repository.find_by_client_request_id(
            "add_active_strategy",
            test_strategy,
            "req-strategy-test",
        )

        assert found is not None
        assert found.strategy_id == test_strategy


class TestListPending:
    """Test list_pending() method."""

    @pytest.mark.asyncio
    async def test_list_pending_returns_only_pending_commands(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that list_pending() returns only pending commands."""
        # Create pending command
        cmd1 = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable",
            issued_by="operator",
            client_request_id="req-pending-1",
        )
        command_id1 = await repository.create_command(cmd1)

        # Create and mark as applied
        cmd2 = ControlCommandRecord(
            command_type="disable_execution",
            reason="Disable",
            issued_by="operator",
            client_request_id="req-pending-2",
        )
        command_id2 = await repository.create_command(cmd2)
        await repository.mark_applied(command_id2)

        # List pending
        pending = await repository.list_pending()

        pending_ids = {str(cmd.command_id) for cmd in pending}
        assert command_id1 in pending_ids
        assert command_id2 not in pending_ids

    @pytest.mark.asyncio
    async def test_list_pending_returns_empty_list_when_no_pending(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that list_pending() returns empty list when no pending commands."""
        pending = await repository.list_pending()
        assert pending == []


class TestMarkApplied:
    """Test mark_applied() method."""

    @pytest.mark.asyncio
    async def test_mark_applied_updates_status_and_applied_at(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that mark_applied() updates status and applied_at."""
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable",
            issued_by="operator",
            client_request_id="req-mark-applied",
        )
        command_id = await repository.create_command(cmd)

        # Mark as applied
        await repository.mark_applied(command_id)

        # Verify status updated
        found = await repository.find_by_client_request_id(
            "enable_execution",
            None,
            "req-mark-applied",
        )
        assert found is not None
        assert found.status == "applied"
        assert found.applied_at is not None
        assert isinstance(found.applied_at, datetime)

    @pytest.mark.asyncio
    async def test_mark_applied_raises_for_non_existent_command(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that mark_applied() raises ValueError for non-existent command."""
        non_existent_id = str(uuid4())

        with pytest.raises(ValueError, match="Command not found"):
            await repository.mark_applied(non_existent_id)


class TestMarkFailed:
    """Test mark_failed() method."""

    @pytest.mark.asyncio
    async def test_mark_failed_updates_status_and_error_message(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that mark_failed() updates status and error_message."""
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable",
            issued_by="operator",
            client_request_id="req-mark-failed",
        )
        command_id = await repository.create_command(cmd)

        # Mark as failed
        error_msg = "Health gates failed"
        await repository.mark_failed(command_id, error_msg)

        # Verify status updated
        found = await repository.find_by_client_request_id(
            "enable_execution",
            None,
            "req-mark-failed",
        )
        assert found is not None
        assert found.status == "failed"
        assert found.error_message == error_msg

    @pytest.mark.asyncio
    async def test_mark_failed_raises_for_non_existent_command(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that mark_failed() raises ValueError for non-existent command."""
        non_existent_id = str(uuid4())

        with pytest.raises(ValueError, match="Command not found"):
            await repository.mark_failed(non_existent_id, "Error message")


class TestIdempotency:
    """Test idempotency constraint."""

    @pytest.mark.asyncio
    async def test_idempotency_constraint_prevents_duplicate_commands(
        self, repository: ControlCommandRepository
    ) -> None:
        """Test that idempotency constraint prevents duplicate commands."""
        # Create first command
        cmd1 = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable",
            issued_by="operator",
            client_request_id="req-idempotency",
        )
        await repository.create_command(cmd1)

        # Try to create duplicate (should fail)
        cmd2 = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable again",
            issued_by="operator",
            client_request_id="req-idempotency",
        )

        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await repository.create_command(cmd2)
