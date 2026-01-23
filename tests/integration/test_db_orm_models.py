"""Integration tests for platform ORM models.

Per Commit 1.2: Test that ORM models work correctly with type conversions,
create/read/update operations, and relationships.
"""

from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polytrader.db.models import (
    ControlCommandRecord,
    ExecutionControlRecord,
    LiveStrategyActivationRecord,
    StrategyRecord,
)


@pytest.mark.integration
class TestStrategyRecord:
    """Test StrategyRecord ORM model."""

    async def test_create_strategy_record(self, postgres_test_url: str, postgres_db: None) -> None:
        """Test creating a StrategyRecord."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            strategy = StrategyRecord(
                strategy_id="test_strategy",
                name="Test Strategy",
                description="A test strategy",
                config={"buy_threshold": 0.3, "min_history": 30},
                enabled=True,
            )
            session.add(strategy)
            await session.commit()

            # Read back
            result = await session.execute(
                select(StrategyRecord).where(StrategyRecord.strategy_id == "test_strategy")
            )
            loaded = result.scalar_one()

            assert loaded.strategy_id == "test_strategy"
            assert loaded.name == "Test Strategy"
            assert loaded.description == "A test strategy"
            assert loaded.config == {"buy_threshold": 0.3, "min_history": 30}
            assert loaded.enabled is True
            assert isinstance(loaded.created_at, datetime)
            assert isinstance(loaded.updated_at, datetime)

        await engine.dispose()

    async def test_update_strategy_record(self, postgres_test_url: str, postgres_db: None) -> None:
        """Test updating a StrategyRecord."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            strategy = StrategyRecord(
                strategy_id="test_strategy",
                name="Test Strategy",
                config={},
                enabled=True,
            )
            session.add(strategy)
            await session.commit()

            # Update
            strategy.name = "Updated Strategy"
            strategy.config = {"new_param": 42}
            await session.commit()

            # Read back
            result = await session.execute(
                select(StrategyRecord).where(StrategyRecord.strategy_id == "test_strategy")
            )
            loaded = result.scalar_one()

            assert loaded.name == "Updated Strategy"
            assert loaded.config == {"new_param": 42}

        await engine.dispose()


@pytest.mark.integration
class TestExecutionControlRecord:
    """Test ExecutionControlRecord ORM model."""

    async def test_create_execution_control_record(
        self, postgres_test_url: str, postgres_db: None
    ) -> None:
        """Test that ExecutionControlRecord works with version field."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            # Read existing (created by migration)
            result = await session.execute(
                select(ExecutionControlRecord).where(ExecutionControlRecord.id == 1)
            )
            control = result.scalar_one()

            assert control.id == 1
            assert control.execution_enabled is False
            assert control.version == 1
            assert isinstance(control.updated_at, datetime)

            # Update with version increment
            control.execution_enabled = True
            control.version = 2
            control.updated_by = "test_user"
            control.reason = "Test update"
            await session.commit()

            # Read back
            result = await session.execute(
                select(ExecutionControlRecord).where(ExecutionControlRecord.id == 1)
            )
            loaded = result.scalar_one()

            assert loaded.execution_enabled is True
            assert loaded.version == 2
            assert loaded.updated_by == "test_user"
            assert loaded.reason == "Test update"

        await engine.dispose()


@pytest.mark.integration
class TestLiveStrategyActivationRecord:
    """Test LiveStrategyActivationRecord ORM model."""

    async def test_create_live_strategy_activation_record(
        self, postgres_test_url: str, postgres_db: None
    ) -> None:
        """Test creating a LiveStrategyActivationRecord."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            # Create strategy first (required for FK)
            strategy = StrategyRecord(
                strategy_id="test_strategy",
                name="Test Strategy",
                config={},
            )
            session.add(strategy)
            await session.commit()

            # Create activation
            activation = LiveStrategyActivationRecord(
                strategy_id="test_strategy",
                active=True,
                activated_by="test_user",
                reason="Test activation",
            )
            activation.activated_at = datetime.now()
            session.add(activation)
            await session.commit()

            # Read back
            result = await session.execute(
                select(LiveStrategyActivationRecord).where(
                    LiveStrategyActivationRecord.strategy_id == "test_strategy"
                )
            )
            loaded = result.scalar_one()

            assert loaded.strategy_id == "test_strategy"
            assert loaded.active is True
            assert loaded.activated_by == "test_user"
            assert loaded.reason == "Test activation"
            assert isinstance(loaded.activated_at, datetime)
            assert isinstance(loaded.created_at, datetime)
            assert isinstance(loaded.updated_at, datetime)

        await engine.dispose()

    async def test_live_strategy_activation_foreign_key_cascade(
        self, postgres_test_url: str, postgres_db: None
    ) -> None:
        """Test that deleting strategy cascades to activation."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            # Create strategy and activation
            strategy = StrategyRecord(
                strategy_id="test_strategy",
                name="Test Strategy",
                config={},
            )
            session.add(strategy)
            await session.commit()

            activation = LiveStrategyActivationRecord(
                strategy_id="test_strategy",
                active=True,
                activated_by="test_user",
                reason="Test",
            )
            session.add(activation)
            await session.commit()

            # Delete strategy (should cascade)
            await session.delete(strategy)
            await session.commit()

            # Verify activation is deleted
            result = await session.execute(
                select(LiveStrategyActivationRecord).where(
                    LiveStrategyActivationRecord.strategy_id == "test_strategy"
                )
            )
            loaded = result.scalar_one_or_none()

            assert loaded is None

        await engine.dispose()


@pytest.mark.integration
class TestControlCommandRecord:
    """Test ControlCommandRecord ORM model."""

    async def test_create_control_command_record(
        self, postgres_test_url: str, postgres_db: None
    ) -> None:
        """Test creating a ControlCommandRecord with client_request_id."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            # Create strategy first (for FK)
            strategy = StrategyRecord(
                strategy_id="test_strategy",
                name="Test Strategy",
                config={},
            )
            session.add(strategy)
            await session.commit()

            # Create command
            command = ControlCommandRecord(
                command_type="add_active_strategy",
                strategy_id="test_strategy",
                client_request_id="req-123",
                expected_version=1,
                reason="Test command",
                issued_by="test_user",
                status="pending",
            )
            session.add(command)
            await session.commit()

            # Read back
            result = await session.execute(
                select(ControlCommandRecord).where(
                    ControlCommandRecord.client_request_id == "req-123"
                )
            )
            loaded = result.scalar_one()

            assert isinstance(loaded.command_id, UUID)
            assert loaded.command_type == "add_active_strategy"
            assert loaded.strategy_id == "test_strategy"
            assert loaded.client_request_id == "req-123"
            assert loaded.expected_version == 1
            assert loaded.reason == "Test command"
            assert loaded.issued_by == "test_user"
            assert loaded.status == "pending"
            assert loaded.error_message is None
            assert isinstance(loaded.created_at, datetime)
            assert loaded.applied_at is None

        await engine.dispose()

    async def test_control_command_record_without_strategy_id(
        self, postgres_test_url: str, postgres_db: None
    ) -> None:
        """Test ControlCommandRecord for enable/disable commands (no strategy_id)."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            command = ControlCommandRecord(
                command_type="enable_execution",
                strategy_id=None,  # NULL for enable/disable commands
                client_request_id="req-456",
                expected_version=1,
                reason="Enable execution",
                issued_by="test_user",
                status="pending",
            )
            session.add(command)
            await session.commit()

            # Read back
            result = await session.execute(
                select(ControlCommandRecord).where(
                    ControlCommandRecord.client_request_id == "req-456"
                )
            )
            loaded = result.scalar_one()

            assert loaded.command_type == "enable_execution"
            assert loaded.strategy_id is None
            assert loaded.client_request_id == "req-456"

        await engine.dispose()

    async def test_control_command_record_type_conversions(
        self, postgres_test_url: str, postgres_db: None
    ) -> None:
        """Test that ORM model handles type conversions correctly (UUID, JSONB, timestamps)."""
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            # Create command
            command = ControlCommandRecord(
                command_type="disable_execution",
                strategy_id=None,
                client_request_id="req-789",
                reason="Disable execution",
                issued_by="test_user",
                status="applied",
            )
            command.applied_at = datetime.now()
            session.add(command)
            await session.commit()

            # Read back and verify types
            result = await session.execute(
                select(ControlCommandRecord).where(
                    ControlCommandRecord.client_request_id == "req-789"
                )
            )
            loaded = result.scalar_one()

            # Verify UUID is properly converted
            assert isinstance(loaded.command_id, UUID)

            # Verify timestamps are datetime objects
            assert isinstance(loaded.created_at, datetime)
            assert isinstance(loaded.applied_at, datetime)

            # Verify string fields
            assert isinstance(loaded.command_type, str)
            assert isinstance(loaded.reason, str)
            assert isinstance(loaded.issued_by, str)
            assert isinstance(loaded.status, str)

        await engine.dispose()
