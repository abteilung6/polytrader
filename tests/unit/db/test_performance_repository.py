"""Unit tests for PerformanceOverviewRepository.

Tests the contract:
- Correct SQL parameters passed to session.execute
- Evidence tier computed correctly from trade_count vs MIN_TRADES_THRESHOLD
- Derived metrics (win_rate_pct, profit_factor) computed correctly
- Strategies with zero trades get INSUFFICIENT_DATA
- until defaults to now() when None

Per unit_testing_technical.mdc: No DB, no network, no wall-clock.
We mock the AsyncSession and verify the Python logic layer.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.db.performance_repository import (
    MIN_TRADES_THRESHOLD,
    PerformanceOverviewRepository,
)


def _make_row(
    strategy_id: str = "strat-1",
    name: str = "Test Strategy",
    template_type_id: str = "vfmr",
    template_version: str = "1.0.0",
    actual_state: str = "RUNNING",
    trade_count: int = 10,
    wins: int = 7,
    losses: int = 2,
    breakevens: int = 1,
    total_realized_pnl: float = 15.0,
    avg_trade_pnl: float | None = 1.5,
    last_trade_exit_ts_wall: datetime | None = None,
    sum_positive_pnl: float = 20.0,
    sum_negative_pnl: float = -5.0,
) -> MagicMock:
    """Create a mock row matching the SQL result set."""
    row = MagicMock()
    row.strategy_id = strategy_id
    row.name = name
    row.template_type_id = template_type_id
    row.template_version = template_version
    row.actual_state = actual_state
    row.trade_count = trade_count
    row.wins = wins
    row.losses = losses
    row.breakevens = breakevens
    row.total_realized_pnl = total_realized_pnl
    row.avg_trade_pnl = avg_trade_pnl
    row.last_trade_exit_ts_wall = last_trade_exit_ts_wall or datetime(2026, 1, 15, tzinfo=UTC)
    row.sum_positive_pnl = sum_positive_pnl
    row.sum_negative_pnl = sum_negative_pnl
    return row


def _make_zero_trade_row(strategy_id: str = "strat-empty") -> MagicMock:
    """Create a row for a strategy with zero trades (LEFT JOIN null)."""
    return _make_row(
        strategy_id=strategy_id,
        name="Empty Strategy",
        trade_count=0,
        wins=0,
        losses=0,
        breakevens=0,
        total_realized_pnl=0.0,
        avg_trade_pnl=None,
        last_trade_exit_ts_wall=None,
        sum_positive_pnl=0.0,
        sum_negative_pnl=0.0,
    )


def _mock_session(rows: list[MagicMock]) -> AsyncMock:
    """Create a mock AsyncSession that returns the given rows."""
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


class TestPerformanceOverviewRepository:
    """Unit tests for PerformanceOverviewRepository."""

    @pytest.mark.asyncio
    async def test_returns_items_from_sql_rows(self) -> None:
        """Repository converts SQL rows to PerformanceOverviewItem."""
        rows = [_make_row(strategy_id="s1", wins=5, losses=3, trade_count=8)]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(
            until=datetime(2026, 2, 1, tzinfo=UTC),
        )

        assert len(items) == 1
        assert items[0].strategy_id == "s1"
        assert items[0].trade_count == 8
        assert items[0].wins == 5
        assert items[0].losses == 3

    @pytest.mark.asyncio
    async def test_win_rate_computed_correctly(self) -> None:
        """win_rate_pct = (wins / trade_count) * 100."""
        rows = [_make_row(wins=3, trade_count=10)]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items[0].win_rate_pct == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_win_rate_none_when_no_trades(self) -> None:
        """win_rate_pct is None when trade_count = 0."""
        rows = [_make_zero_trade_row()]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items[0].win_rate_pct is None

    @pytest.mark.asyncio
    async def test_profit_factor_computed_correctly(self) -> None:
        """profit_factor = sum_positive / abs(sum_negative)."""
        rows = [_make_row(sum_positive_pnl=30.0, sum_negative_pnl=-10.0)]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items[0].profit_factor == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_profit_factor_none_when_no_losses(self) -> None:
        """profit_factor is None when sum_negative_pnl = 0 (no losses)."""
        rows = [_make_row(sum_positive_pnl=10.0, sum_negative_pnl=0.0)]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items[0].profit_factor is None

    @pytest.mark.asyncio
    async def test_evidence_tier_tracking_when_above_threshold(self) -> None:
        """evidence_tier = TRACKING when trade_count >= MIN_TRADES_THRESHOLD."""
        rows = [_make_row(trade_count=MIN_TRADES_THRESHOLD)]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items[0].evidence_tier == "TRACKING"

    @pytest.mark.asyncio
    async def test_evidence_tier_insufficient_when_below_threshold(self) -> None:
        """evidence_tier = INSUFFICIENT_DATA when trade_count < MIN_TRADES_THRESHOLD."""
        rows = [_make_zero_trade_row()]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items[0].evidence_tier == "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_multiple_strategies_sorted(self) -> None:
        """Multiple strategies are returned correctly."""
        rows = [
            _make_row(strategy_id="top", total_realized_pnl=100.0),
            _make_row(strategy_id="mid", total_realized_pnl=10.0),
            _make_zero_trade_row(strategy_id="new"),
        ]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert len(items) == 3
        assert items[0].strategy_id == "top"
        assert items[1].strategy_id == "mid"
        assert items[2].strategy_id == "new"

    @pytest.mark.asyncio
    async def test_sql_params_include_filters(self) -> None:
        """Verify that filter parameters are passed to SQL."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)
        since = datetime(2026, 1, 1, tzinfo=UTC)
        until = datetime(2026, 2, 1, tzinfo=UTC)

        await repo.get_overview(
            since=since,
            until=until,
            execution_mode="paper",
            template_type_id="vfmr",
            state="RUNNING",
            limit=50,
        )

        session.execute.assert_awaited_once()
        params = session.execute.call_args[0][1]
        assert params["since"] == since
        assert params["until"] == until
        assert params["execution_mode"] == "paper"
        assert params["template_type_id"] == "vfmr"
        assert params["state"] == "RUNNING"
        assert params["lim"] == 50

    @pytest.mark.asyncio
    async def test_limit_clamped_to_range(self) -> None:
        """Limit is clamped to [1, 1000]."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        # Over 1000 → clamped to 1000
        await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC), limit=5000)
        params = session.execute.call_args[0][1]
        assert params["lim"] == 1000

        # Under 1 → clamped to 1
        await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC), limit=0)
        params = session.execute.call_args[0][1]
        assert params["lim"] == 1

    @pytest.mark.asyncio
    async def test_until_defaults_to_now_when_none(self) -> None:
        """until defaults to ~now() when not provided."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        before = datetime.now(UTC)
        await repo.get_overview()
        after = datetime.now(UTC)

        params = session.execute.call_args[0][1]
        assert before <= params["until"] <= after

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self) -> None:
        """Empty result set returns empty list."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items == []

    @pytest.mark.asyncio
    async def test_sql_does_not_contain_conflicting_cast_syntax(self) -> None:
        """Regression: :param::type cast syntax conflicts with SQLAlchemy text().

        psycopg interprets :since as a bind parameter, so :since::timestamptz
        produces a syntax error. The SQL must use :since IS NULL instead.
        See: psycopg.errors.SyntaxError at `:since::timestamptz`.
        """
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        await repo.get_overview(since=None, until=datetime(2026, 2, 1, tzinfo=UTC))

        # Extract the SQL text that was passed to session.execute
        sql_clause = session.execute.call_args[0][0]
        sql_text = sql_clause.text

        # Must NOT contain :param::type (bind param followed by PG cast)
        assert "::timestamptz" not in sql_text, (
            "SQL contains ::timestamptz cast on a bind parameter — "
            "this conflicts with SQLAlchemy text() parameter syntax"
        )
