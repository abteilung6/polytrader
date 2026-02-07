"""Unit tests for ClosedTradeSink.

Tests the contract:
- Subscribes to STRATEGY_CLOSED_TRADES topic
- Persists StrategyClosedTradeEvent to strategy_closed_trades table
- Idempotent via ON CONFLICT (event_id) DO NOTHING
- Graceful error handling (never crashes the sink)

Per unit_testing_technical.mdc: No DB, no network, no wall-clock.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.common.ids import reset_run_id
from polytrader.events.bus import EventBus
from polytrader.events.closed_trade_sink import _INSERT_SQL, ClosedTradeSink
from polytrader.events.types import EventSource, StrategyClosedTradeEvent


def _make_closed_trade_event(
    strategy_id: str = "strat-1",
    pnl: float = 1.5,
    result: str = "WIN",
    execution_mode: str = "paper",
) -> StrategyClosedTradeEvent:
    """Factory for deterministic StrategyClosedTradeEvent."""
    reset_run_id()
    return StrategyClosedTradeEvent(
        source=EventSource.POSTTRADE,
        strategy_id=strategy_id,
        market_slug="will-x-happen",
        outcome="UP",
        entry_price=0.40,
        exit_price=0.60,
        size=10.0,
        pnl=pnl,
        pnl_pct=50.0,
        entry_time=1000.0,
        exit_time=1010.0,
        result=result,
        execution_mode=execution_mode,
        order_id="",
        fill_id="",
    )


class TestClosedTradeSink:
    """ClosedTradeSink unit tests."""

    @pytest.fixture
    def bus(self) -> EventBus:
        """Create a fresh EventBus."""
        return EventBus()

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        """Create a mock async session factory.

        Returns an async_sessionmaker-like callable that yields
        an AsyncMock session via async context manager.
        """
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        # Make the factory callable and return an async context manager
        factory = MagicMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory.return_value = ctx

        # Attach session reference for assertions
        factory._mock_session = mock_session
        return factory

    def test_init_sets_defaults(self, bus: EventBus, mock_session_factory: MagicMock) -> None:
        """ClosedTradeSink initializes with correct defaults."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)

        assert sink._running is False
        assert sink._queue is None

    @pytest.mark.asyncio
    async def test_persist_calls_execute_with_correct_params(
        self, bus: EventBus, mock_session_factory: MagicMock
    ) -> None:
        """_persist sends correct SQL and parameters to session."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)
        event = _make_closed_trade_event(strategy_id="strat-abc", pnl=2.5, result="WIN")

        await sink._persist(event)

        session = mock_session_factory._mock_session
        session.execute.assert_awaited_once()
        call_args = session.execute.call_args

        # Verify SQL statement
        assert call_args[0][0] is _INSERT_SQL

        # Verify parameters
        params = call_args[0][1]
        assert params["event_id"] == event.event_id
        assert params["strategy_id"] == "strat-abc"
        assert params["execution_mode"] == "paper"
        assert params["exit_ts_wall"] == event.ts_wall
        assert params["entry_time"] == 1000.0
        assert params["exit_time"] == 1010.0
        assert params["pnl"] == 2.5
        assert params["pnl_pct"] == 50.0
        assert params["result"] == "WIN"
        assert params["size"] == 10.0
        assert params["duration_seconds"] == 10.0  # exit - entry
        assert params["market_slug"] == "will-x-happen"
        assert params["outcome"] == "UP"
        assert params["entry_price"] == 0.40
        assert params["exit_price"] == 0.60

        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_handles_db_error_gracefully(
        self, bus: EventBus, mock_session_factory: MagicMock
    ) -> None:
        """_persist logs and continues on database error (never crashes)."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)
        mock_session_factory._mock_session.execute.side_effect = RuntimeError("DB down")

        event = _make_closed_trade_event()

        # Must not raise
        await sink._persist(event)

    @pytest.mark.asyncio
    async def test_run_subscribes_and_processes_event(
        self, bus: EventBus, mock_session_factory: MagicMock
    ) -> None:
        """run() subscribes to STRATEGY_CLOSED_TRADES and processes events."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)

        # Start sink in background
        task = asyncio.create_task(sink.run())

        # Give it a moment to subscribe
        await asyncio.sleep(0.1)

        assert sink._running is True
        assert sink._queue is not None

        # Publish a closed-trade event
        import polytrader.events as events_module

        topic = events_module.STRATEGY_CLOSED_TRADES
        event = _make_closed_trade_event(strategy_id="strat-run-test", pnl=3.0)
        await bus.publish(topic, event)

        # Give time for consumption
        await asyncio.sleep(0.8)

        # Verify persistence was called
        session = mock_session_factory._mock_session
        session.execute.assert_awaited_once()
        params = session.execute.call_args[0][1]
        assert params["strategy_id"] == "strat-run-test"
        assert params["pnl"] == 3.0

        # Stop cleanly
        await sink.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(
        self, bus: EventBus, mock_session_factory: MagicMock
    ) -> None:
        """stop() sets _running to False."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)
        sink._running = True

        await sink.stop()

        assert sink._running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_noop(
        self, bus: EventBus, mock_session_factory: MagicMock
    ) -> None:
        """stop() is a no-op when sink is not running."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)

        # Must not raise
        await sink.stop()
        assert sink._running is False

    @pytest.mark.asyncio
    async def test_duration_seconds_computed_correctly(
        self, bus: EventBus, mock_session_factory: MagicMock
    ) -> None:
        """duration_seconds = exit_time - entry_time."""
        sink = ClosedTradeSink(bus=bus, session_factory=mock_session_factory)
        reset_run_id()
        event = StrategyClosedTradeEvent(
            source=EventSource.POSTTRADE,
            strategy_id="strat-dur",
            market_slug="market-a",
            outcome="DOWN",
            entry_price=0.70,
            exit_price=0.30,
            size=5.0,
            pnl=-2.0,
            pnl_pct=-40.0,
            entry_time=500.0,
            exit_time=987.5,
            result="LOSS",
            execution_mode="live",
            order_id="",
            fill_id="",
        )

        await sink._persist(event)

        params = mock_session_factory._mock_session.execute.call_args[0][1]
        assert params["duration_seconds"] == pytest.approx(487.5)
        assert params["execution_mode"] == "live"
        assert params["outcome"] == "DOWN"
