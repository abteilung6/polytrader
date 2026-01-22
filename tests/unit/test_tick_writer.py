"""Unit tests for BufferedTickWriter."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from polytrader.db.tick_writer import (
    BufferedTickWriter,
    TickDbFields,
    _convert_event_to_db_format,
)
from polytrader.events.types import EventSource, MarketDataEvent


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
    repo.bulk_create_ticks = AsyncMock(return_value=5)
    return repo


@pytest.fixture
def sample_event() -> MarketDataEvent:
    """Create sample MarketDataEvent."""
    return MarketDataEvent(
        event_id=str(uuid4()),
        ts_wall=datetime.now(UTC).isoformat(),
        ts_mono=12345.678,
        correlation_id="test-correlation",
        run_id="test-run",
        schema_version="1.0",
        source=EventSource.MDP,
        market_slug="btc-updown-15m",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.50,
    )


class TestConvertEventToDbFormat:
    """Test event to database format conversion."""

    def test_converts_event_to_db_format(self, sample_event: MarketDataEvent) -> None:
        """Test that event is converted correctly."""
        result = _convert_event_to_db_format(sample_event)

        assert isinstance(result, TickDbFields)
        assert result.tick_id == UUID(sample_event.event_id)
        assert result.market_slug == "btc-updown-15m"
        assert result.outcome == "UP"
        assert result.ts_mono == 12345.678
        assert result.run_id == "test-run"
        assert result.best_bid == Decimal("0.45")
        assert result.best_ask == Decimal("0.50")
        assert result.mid == Decimal("0.475")  # (0.45 + 0.50) / 2
        assert result.spread == Decimal("0.05")  # 0.50 - 0.45
        assert result.spread_bps == Decimal("500.00")  # 0.05 * 10000

    def test_converts_iso_timestamp(self, sample_event: MarketDataEvent) -> None:
        """Test that ISO timestamp is parsed correctly."""
        from datetime import datetime

        result = _convert_event_to_db_format(sample_event)
        ts_wall = result.ts_wall
        assert isinstance(ts_wall, datetime)
        assert ts_wall.tzinfo is not None

    def test_handles_zero_prices(self) -> None:
        """Test that zero prices are handled correctly."""
        event = MarketDataEvent(
            event_id=str(uuid4()),
            ts_wall=datetime.now(UTC).isoformat(),
            ts_mono=12345.678,
            market_slug="test-market",
            outcome="DOWN",
            best_bid=0.0,
            best_ask=0.0,
        )
        result = _convert_event_to_db_format(event)
        assert result.best_bid == Decimal("0")
        assert result.best_ask == Decimal("0")
        assert result.mid == Decimal("0")
        assert result.spread == Decimal("0")


class TestBufferedTickWriter:
    """Test BufferedTickWriter."""

    @pytest.mark.asyncio
    async def test_add_flushes_on_size_threshold(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that buffer flushes when batch_size is reached."""
        writer = BufferedTickWriter(mock_repository, batch_size=3, flush_interval=10.0)

        # Add 3 events (should trigger flush)
        await writer.add(sample_event)
        await writer.add(sample_event)
        await writer.add(sample_event)

        # Wait for flush to complete
        await asyncio.sleep(0.1)

        # Verify flush was called
        mock_repository.bulk_create_ticks.assert_called_once()
        assert mock_repository.bulk_create_ticks.call_count == 1

        await writer.close()

    @pytest.mark.asyncio
    async def test_add_flushes_on_time_threshold(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that buffer flushes after flush_interval."""
        writer = BufferedTickWriter(mock_repository, batch_size=1000, flush_interval=0.1)

        # Add one event
        await writer.add(sample_event)

        # Wait for flush interval
        await asyncio.sleep(0.15)

        # Verify flush was called
        mock_repository.bulk_create_ticks.assert_called()

        await writer.close()

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that flush clears the buffer."""
        writer = BufferedTickWriter(mock_repository, batch_size=1000, flush_interval=10.0)

        # Add events
        await writer.add(sample_event)
        await writer.add(sample_event)

        # Flush manually
        await writer.flush()

        # Verify flush was called
        mock_repository.bulk_create_ticks.assert_called_once()
        call_args = mock_repository.bulk_create_ticks.call_args[0][0]
        assert len(call_args) == 2

        # Buffer should be empty
        await writer.flush()
        # Should not call again (buffer empty)
        assert mock_repository.bulk_create_ticks.call_count == 1

        await writer.close()

    @pytest.mark.asyncio
    async def test_close_flushes_remaining_ticks(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that close() flushes remaining ticks."""
        writer = BufferedTickWriter(mock_repository, batch_size=1000, flush_interval=10.0)

        # Add events
        await writer.add(sample_event)
        await writer.add(sample_event)

        # Close (should flush)
        await writer.close()

        # Verify flush was called
        mock_repository.bulk_create_ticks.assert_called_once()
        call_args = mock_repository.bulk_create_ticks.call_args[0][0]
        assert len(call_args) == 2

    @pytest.mark.asyncio
    async def test_close_is_idempotent(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that close() can be called multiple times safely."""
        writer = BufferedTickWriter(mock_repository, batch_size=1000, flush_interval=10.0)

        await writer.add(sample_event)
        await writer.close()
        await writer.close()  # Should not raise

        # Should only flush once
        mock_repository.bulk_create_ticks.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_ignored_after_close(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that add() is ignored after close()."""
        writer = BufferedTickWriter(mock_repository, batch_size=1000, flush_interval=10.0)

        await writer.close()
        await writer.add(sample_event)

        # Should not flush (event was ignored)
        await asyncio.sleep(0.1)
        mock_repository.bulk_create_ticks.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_flush_errors_gracefully(
        self, mock_repository: AsyncMock, sample_event: MarketDataEvent
    ) -> None:
        """Test that flush errors don't crash the writer."""
        mock_repository.bulk_create_ticks.side_effect = Exception("Database error")

        writer = BufferedTickWriter(mock_repository, batch_size=1, flush_interval=10.0)

        # Add event (should trigger flush with error)
        await writer.add(sample_event)

        # Wait for flush
        await asyncio.sleep(0.1)

        # Should not raise, writer should still work
        await writer.add(sample_event)
        await writer.close()
