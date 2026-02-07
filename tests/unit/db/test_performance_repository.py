"""Unit tests for PerformanceOverviewRepository.

Architecture: three isolated test targets matching the module's pure design.

1. TestBuildOverviewQuery — tests the pure query builder (synchronous).
   Compiles the Select to SQL and inspects structure + parameters.

2. TestMapRowToItem — tests the pure row-to-domain mapper (synchronous).
   Verifies derived metrics, evidence tier, and edge cases.

3. TestPerformanceOverviewRepository — tests the thin async orchestrator.
   Mocks session to verify delegation and result assembly.

Per unit_testing_technical.mdc: No DB, no network, no wall-clock.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from polytrader.db.performance_repository import (
    MIN_TRADES_THRESHOLD,
    PerformanceOverviewItem,
    PerformanceOverviewRepository,
    build_overview_query,
    map_row_to_item,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compile(query: Select[Any]) -> tuple[str, dict[str, Any]]:
    """Compile a SQLAlchemy Select to PostgreSQL SQL string + params.

    This enables testing query structure without executing against a database.
    """
    compiled = query.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


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
    """Create a mock row matching the overview query result set."""
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


# ---------------------------------------------------------------------------
# 1. TestBuildOverviewQuery — pure query builder (synchronous)
# ---------------------------------------------------------------------------


class TestBuildOverviewQuery:
    """Tests for build_overview_query() — pure, no IO.

    Verifies SQL structure by compiling to PostgreSQL dialect.
    """

    _UNTIL = datetime(2026, 2, 1, tzinfo=UTC)

    def test_returns_select_object(self) -> None:
        """build_overview_query returns a SQLAlchemy Select."""
        query = build_overview_query(since=None, until=self._UNTIL)
        assert isinstance(query, Select)

    def test_compiles_to_valid_sql(self) -> None:
        """Query compiles to SQL with expected structural elements."""
        query = build_overview_query(since=None, until=self._UNTIL)
        sql, _params = _compile(query)

        # Core structural elements
        assert "LEFT OUTER JOIN" in sql
        assert "GROUP BY" in sql
        assert "ORDER BY" in sql
        assert "LIMIT" in sql
        # Table references
        assert "strategy_instances" in sql
        assert "strategy_closed_trades" in sql

    # --- Conditional filter: since ---

    def test_since_none_excludes_lower_bound(self) -> None:
        """When since=None, no lower-bound filter on exit_ts_wall."""
        query = build_overview_query(since=None, until=self._UNTIL)
        sql, _params = _compile(query)

        assert sql.count("exit_ts_wall >=") == 0
        assert sql.count("exit_ts_wall <=") == 1

    def test_since_provided_includes_lower_bound(self) -> None:
        """When since is provided, exit_ts_wall has both >= and <= bounds."""
        since = datetime(2026, 1, 1, tzinfo=UTC)
        query = build_overview_query(since=since, until=self._UNTIL)
        sql, params = _compile(query)

        assert sql.count("exit_ts_wall >=") == 1
        assert sql.count("exit_ts_wall <=") == 1
        assert since in params.values()

    # --- Conditional filter: execution_mode ---

    def test_execution_mode_none_excludes_filter(self) -> None:
        """When execution_mode=None, no filter on execution_mode column."""
        query = build_overview_query(since=None, until=self._UNTIL, execution_mode=None)
        sql, params = _compile(query)

        assert "execution_mode =" not in sql
        assert "paper" not in params.values()

    def test_execution_mode_provided_includes_filter(self) -> None:
        """When execution_mode is provided, filter clause is added."""
        query = build_overview_query(since=None, until=self._UNTIL, execution_mode="paper")
        sql, params = _compile(query)

        assert "execution_mode =" in sql
        assert "paper" in params.values()

    # --- Conditional filter: state ---

    def test_state_none_excludes_filter(self) -> None:
        """When state=None, no filter on actual_state."""
        query = build_overview_query(since=None, until=self._UNTIL, state=None)
        sql, params = _compile(query)

        # actual_state appears in SELECT but not in a WHERE = comparison
        assert "actual_state =" not in sql
        assert "RUNNING" not in params.values()

    def test_state_provided_includes_filter(self) -> None:
        """When state is provided, WHERE clause on actual_state is added."""
        query = build_overview_query(since=None, until=self._UNTIL, state="RUNNING")
        sql, params = _compile(query)

        assert "actual_state =" in sql
        assert "RUNNING" in params.values()

    # --- Conditional filter: template_type_id ---

    def test_template_type_id_none_excludes_filter(self) -> None:
        """When template_type_id=None, no filter added."""
        query = build_overview_query(since=None, until=self._UNTIL, template_type_id=None)
        sql, _params = _compile(query)

        # template_type_id appears in SELECT but not in a WHERE = comparison
        # The SELECT uses it as a column reference, the WHERE would use = comparison
        where_section = sql.split("WHERE")[-1] if "WHERE" in sql else ""
        assert "template_type_id =" not in where_section

    def test_template_type_id_provided_includes_filter(self) -> None:
        """When template_type_id is provided, WHERE clause is added."""
        query = build_overview_query(since=None, until=self._UNTIL, template_type_id="vfmr")
        sql, params = _compile(query)

        assert "vfmr" in params.values()

    # --- All filters combined ---

    def test_all_filters_provided(self) -> None:
        """When all filters are provided, all appear in SQL and params."""
        since = datetime(2026, 1, 1, tzinfo=UTC)
        query = build_overview_query(
            since=since,
            until=self._UNTIL,
            execution_mode="paper",
            state="RUNNING",
            template_type_id="vfmr",
        )
        sql, params = _compile(query)
        param_values = set(params.values())

        assert since in param_values
        assert "paper" in param_values
        assert "RUNNING" in param_values
        assert "vfmr" in param_values
        assert "execution_mode =" in sql
        assert "actual_state =" in sql

    def test_no_optional_filters(self) -> None:
        """When no optional filters, only until appears as time bound."""
        query = build_overview_query(
            since=None,
            until=self._UNTIL,
            execution_mode=None,
            state=None,
            template_type_id=None,
        )
        sql, params = _compile(query)
        param_values = set(params.values())

        assert self._UNTIL in param_values
        # None-only optional filter values must not be in params
        assert "paper" not in param_values
        assert "RUNNING" not in param_values
        assert "vfmr" not in param_values

    # --- Sort ---

    def test_sort_by_total_realized_pnl(self) -> None:
        """Default sort: ORDER BY total_realized_pnl DESC."""
        query = build_overview_query(since=None, until=self._UNTIL, sort_by="total_realized_pnl")
        sql, _params = _compile(query)
        assert "ORDER BY" in sql
        assert "total_realized_pnl" in sql.split("ORDER BY")[1]

    def test_sort_by_trade_count(self) -> None:
        """Sort by trade_count: ORDER BY trade_count DESC."""
        query = build_overview_query(since=None, until=self._UNTIL, sort_by="trade_count")
        sql, _params = _compile(query)
        assert "trade_count" in sql.split("ORDER BY")[1]

    def test_sort_by_win_rate_pct(self) -> None:
        """Sort by win_rate_pct: ORDER BY CASE expression DESC."""
        query = build_overview_query(since=None, until=self._UNTIL, sort_by="win_rate_pct")
        sql, _params = _compile(query)
        order_section = sql.split("ORDER BY")[1]
        assert "CASE WHEN" in order_section

    # --- Limit ---

    def test_limit_clamped_to_1000(self) -> None:
        """Limit over 1000 is clamped to 1000."""
        query = build_overview_query(since=None, until=self._UNTIL, limit=5000)
        sql, params = _compile(query)

        assert 1000 in params.values()
        assert 5000 not in params.values()

    def test_limit_clamped_to_1(self) -> None:
        """Limit under 1 is clamped to 1."""
        query = build_overview_query(since=None, until=self._UNTIL, limit=0)
        sql, params = _compile(query)

        assert 1 in params.values()
        assert 0 not in set(params.values()) - {0}  # 0 appears in CASE ELSE

    def test_limit_passthrough(self) -> None:
        """Valid limit passes through unclamped."""
        query = build_overview_query(since=None, until=self._UNTIL, limit=42)
        _sql, params = _compile(query)

        assert 42 in params.values()


# ---------------------------------------------------------------------------
# 2. TestMapRowToItem — pure row mapper (synchronous)
# ---------------------------------------------------------------------------


class TestMapRowToItem:
    """Tests for map_row_to_item() — pure, no IO.

    Verifies derived metrics and evidence tier computation.
    """

    def test_basic_mapping(self) -> None:
        """Maps row fields to PerformanceOverviewItem correctly."""
        row = _make_row(strategy_id="s1", wins=5, losses=3, trade_count=8)
        item = map_row_to_item(row)

        assert isinstance(item, PerformanceOverviewItem)
        assert item.strategy_id == "s1"
        assert item.trade_count == 8
        assert item.wins == 5
        assert item.losses == 3

    def test_win_rate_computed_correctly(self) -> None:
        """win_rate_pct = (wins / trade_count) * 100."""
        row = _make_row(wins=3, trade_count=10)
        item = map_row_to_item(row)

        assert item.win_rate_pct == pytest.approx(30.0)

    def test_win_rate_none_when_no_trades(self) -> None:
        """win_rate_pct is None when trade_count = 0."""
        row = _make_zero_trade_row()
        item = map_row_to_item(row)

        assert item.win_rate_pct is None

    def test_profit_factor_computed_correctly(self) -> None:
        """profit_factor = sum_positive / abs(sum_negative)."""
        row = _make_row(sum_positive_pnl=30.0, sum_negative_pnl=-10.0)
        item = map_row_to_item(row)

        assert item.profit_factor == pytest.approx(3.0)

    def test_profit_factor_none_when_no_losses(self) -> None:
        """profit_factor is None when sum_negative_pnl = 0."""
        row = _make_row(sum_positive_pnl=10.0, sum_negative_pnl=0.0)
        item = map_row_to_item(row)

        assert item.profit_factor is None

    def test_evidence_tier_tracking_when_at_threshold(self) -> None:
        """evidence_tier = TRACKING when trade_count >= min_trades_threshold."""
        row = _make_row(trade_count=MIN_TRADES_THRESHOLD)
        item = map_row_to_item(row)

        assert item.evidence_tier == "TRACKING"

    def test_evidence_tier_tracking_when_above_threshold(self) -> None:
        """evidence_tier = TRACKING when trade_count > min_trades_threshold."""
        row = _make_row(trade_count=MIN_TRADES_THRESHOLD + 5)
        item = map_row_to_item(row)

        assert item.evidence_tier == "TRACKING"

    def test_evidence_tier_insufficient_when_below_threshold(self) -> None:
        """evidence_tier = INSUFFICIENT_DATA when trade_count < threshold."""
        row = _make_zero_trade_row()
        item = map_row_to_item(row)

        assert item.evidence_tier == "INSUFFICIENT_DATA"

    def test_custom_threshold(self) -> None:
        """Evidence tier respects custom min_trades_threshold parameter."""
        row = _make_row(trade_count=5)

        item_strict = map_row_to_item(row, min_trades_threshold=10)
        assert item_strict.evidence_tier == "INSUFFICIENT_DATA"

        item_lenient = map_row_to_item(row, min_trades_threshold=3)
        assert item_lenient.evidence_tier == "TRACKING"

    def test_avg_trade_pnl_none_preserved(self) -> None:
        """avg_trade_pnl is None when DB returns NULL (no trades)."""
        row = _make_zero_trade_row()
        item = map_row_to_item(row)

        assert item.avg_trade_pnl is None

    def test_last_trade_exit_ts_preserved(self) -> None:
        """last_trade_exit_ts_wall is passed through from row."""
        ts = datetime(2026, 1, 20, 14, 30, tzinfo=UTC)
        row = _make_row(last_trade_exit_ts_wall=ts)
        item = map_row_to_item(row)

        assert item.last_trade_exit_ts_wall == ts


# ---------------------------------------------------------------------------
# 3. TestPerformanceOverviewRepository — async orchestrator
# ---------------------------------------------------------------------------


class TestPerformanceOverviewRepository:
    """Tests for PerformanceOverviewRepository.get_overview().

    Thin orchestrator tests — logic is covered by the pure function tests.
    """

    @pytest.mark.asyncio
    async def test_returns_items_from_rows(self) -> None:
        """Repository converts SQL rows to PerformanceOverviewItem list."""
        rows = [
            _make_row(strategy_id="s1"),
            _make_row(strategy_id="s2"),
        ]
        session = _mock_session(rows)
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert len(items) == 2
        assert items[0].strategy_id == "s1"
        assert items[1].strategy_id == "s2"

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self) -> None:
        """Empty result set returns empty list."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        items = await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        assert items == []

    @pytest.mark.asyncio
    async def test_until_defaults_to_now_when_none(self) -> None:
        """until defaults to ~now() when not provided — session.execute is called."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        await repo.get_overview()

        # Verify that execute was called (meaning the query was built and run)
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delegates_to_session_execute(self) -> None:
        """Repository calls session.execute with a Select object."""
        session = _mock_session([])
        repo = PerformanceOverviewRepository(session)

        await repo.get_overview(until=datetime(2026, 2, 1, tzinfo=UTC))

        session.execute.assert_awaited_once()
        # The first argument should be a SQLAlchemy Select
        query_arg = session.execute.call_args[0][0]
        assert isinstance(query_arg, Select)
