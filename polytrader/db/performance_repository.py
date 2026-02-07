"""Repository for Performance Overview aggregation.

Per PERFORMANCE_OVERVIEW_PROPOSAL.md §6:
- DB-side GROUP BY aggregation on strategy_closed_trades.
- LEFT JOIN strategy_instances to include strategies with zero trades.
- Evidence tier (INSUFFICIENT_DATA / TRACKING) computed in Python.
- Derived metrics (win_rate_pct, profit_factor) computed in Python.

Architecture (purity & isolation):
- build_overview_query() is a pure function (no IO) returning a Select.
- map_row_to_item() is a pure function mapping DB row → domain model.
- PerformanceOverviewRepository is a thin orchestrator (execute + map).

This repository reads from persisted data only — it does NOT require
the trading runtime to be running.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Float, Select, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.db.models import StrategyClosedTradeRecord as SCT
from polytrader.db.models import StrategyRecord as SI
from polytrader.logging_config import logger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Configurable evidence threshold (per proposal §6.3 and §11)
MIN_TRADES_THRESHOLD: int = int(os.environ.get("PERF_MIN_TRADES_THRESHOLD", "1"))

EvidenceTier = Literal["INSUFFICIENT_DATA", "TRACKING"]

SortByField = Literal["total_realized_pnl", "win_rate_pct", "trade_count"]

# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


class PerformanceOverviewItem(BaseModel):
    """One row per strategy instance."""

    strategy_id: str
    name: str
    template_type_id: str
    template_version: str
    actual_state: str

    # Aggregates
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    total_realized_pnl: float = 0.0
    avg_trade_pnl: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    last_trade_exit_ts_wall: datetime | None = None

    # Evidence
    evidence_tier: EvidenceTier = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Table references (module-level for reuse across pure functions)
# ---------------------------------------------------------------------------

_ct = SCT.__table__  # strategy_closed_trades
_si = SI.__table__  # strategy_instances

# ---------------------------------------------------------------------------
# Pure functions (no IO, fully testable)
# ---------------------------------------------------------------------------


def build_overview_query(
    *,
    since: datetime | None,
    until: datetime,
    execution_mode: str | None = None,
    state: str | None = None,
    template_type_id: str | None = None,
    sort_by: SortByField = "total_realized_pnl",
    limit: int = 200,
) -> Select[Any]:
    """Build the performance overview query.

    Pure function — no IO, no session. Returns a SQLAlchemy Select that can
    be executed against an AsyncSession or compiled to SQL for testing.

    Conditional WHERE clauses are only added when the filter value is not None.
    This avoids psycopg AmbiguousParameter errors that occur when NULL bind
    parameters are used in IS NULL patterns.

    Args:
        since: Inclusive lower bound on exit_ts_wall (None = all time).
        until: Inclusive upper bound on exit_ts_wall.
        execution_mode: Filter closed trades by 'paper' or 'live' (None = all).
        state: Filter strategy_instances by actual_state (None = all).
        template_type_id: Filter strategy_instances by template (None = all).
        sort_by: Column to sort descending.
        limit: Max rows (clamped to [1, 1000]).

    Returns:
        SQLAlchemy Select object ready for execution.
    """
    # --- Aggregation subquery on strategy_closed_trades ---
    agg_subquery = (
        select(
            _ct.c.strategy_id,
            func.count().label("trade_count"),
            func.sum(case((_ct.c.result == "WIN", 1), else_=0)).label("wins"),
            func.sum(case((_ct.c.result == "LOSS", 1), else_=0)).label("losses"),
            func.sum(case((_ct.c.result == "BREAKEVEN", 1), else_=0)).label("breakevens"),
            func.sum(_ct.c.pnl).label("total_realized_pnl"),
            func.avg(_ct.c.pnl).label("avg_trade_pnl"),
            func.max(_ct.c.exit_ts_wall).label("last_trade_exit_ts_wall"),
            func.sum(case((_ct.c.pnl > 0, _ct.c.pnl), else_=0)).label("sum_positive_pnl"),
            func.sum(case((_ct.c.pnl < 0, _ct.c.pnl), else_=0)).label("sum_negative_pnl"),
        )
        .where(_ct.c.exit_ts_wall <= until)
        .group_by(_ct.c.strategy_id)
    )

    if since is not None:
        agg_subquery = agg_subquery.where(_ct.c.exit_ts_wall >= since)
    if execution_mode is not None:
        agg_subquery = agg_subquery.where(_ct.c.execution_mode == execution_mode)

    agg = agg_subquery.subquery("agg")

    # --- Main query: LEFT JOIN strategy_instances → aggregation ---
    query = select(
        _si.c.strategy_id,
        _si.c.name,
        _si.c.template_type_id,
        _si.c.template_version,
        _si.c.actual_state,
        func.coalesce(agg.c.trade_count, 0).label("trade_count"),
        func.coalesce(agg.c.wins, 0).label("wins"),
        func.coalesce(agg.c.losses, 0).label("losses"),
        func.coalesce(agg.c.breakevens, 0).label("breakevens"),
        func.coalesce(agg.c.total_realized_pnl, 0).label("total_realized_pnl"),
        agg.c.avg_trade_pnl,
        agg.c.last_trade_exit_ts_wall,
        func.coalesce(agg.c.sum_positive_pnl, 0).label("sum_positive_pnl"),
        func.coalesce(agg.c.sum_negative_pnl, 0).label("sum_negative_pnl"),
    ).select_from(_si.outerjoin(agg, _si.c.strategy_id == agg.c.strategy_id))

    # Outer filters (strategy_instances) — only when provided
    if state is not None:
        query = query.where(_si.c.actual_state == state)
    if template_type_id is not None:
        query = query.where(_si.c.template_type_id == template_type_id)

    # Dynamic ORDER BY
    sort_exprs: dict[SortByField, Any] = {
        "total_realized_pnl": func.coalesce(agg.c.total_realized_pnl, 0).desc(),
        "win_rate_pct": case(
            (
                func.coalesce(agg.c.trade_count, 0) > 0,
                cast(func.coalesce(agg.c.wins, 0), Float) / agg.c.trade_count,
            ),
            else_=0,
        ).desc(),
        "trade_count": func.coalesce(agg.c.trade_count, 0).desc(),
    }
    query = query.order_by(sort_exprs.get(sort_by, sort_exprs["total_realized_pnl"]))

    # Clamped LIMIT
    clamped = min(max(limit, 1), 1000)
    query = query.limit(clamped)

    return query


def map_row_to_item(
    row: Any,
    *,
    min_trades_threshold: int = MIN_TRADES_THRESHOLD,
) -> PerformanceOverviewItem:
    """Map a database result row to a PerformanceOverviewItem.

    Pure function — no IO. Computes derived metrics:
    - win_rate_pct = (wins / trade_count) * 100 if trade_count > 0
    - profit_factor = sum_positive / |sum_negative| if sum_negative != 0
    - evidence_tier based on trade_count vs threshold

    Args:
        row: A database row with named columns matching the overview query.
        min_trades_threshold: Minimum trades for TRACKING tier.

    Returns:
        PerformanceOverviewItem with all derived metrics computed.
    """
    trade_count = int(row.trade_count)
    wins = int(row.wins)
    losses = int(row.losses)
    breakevens = int(row.breakevens)
    total_realized_pnl = float(row.total_realized_pnl)
    avg_trade_pnl = float(row.avg_trade_pnl) if row.avg_trade_pnl is not None else None
    sum_positive = float(row.sum_positive_pnl)
    sum_negative = float(row.sum_negative_pnl)

    # Derived metrics (Python, per proposal §6.4)
    win_rate_pct: float | None = None
    if trade_count > 0:
        win_rate_pct = (wins / trade_count) * 100.0

    profit_factor: float | None = None
    if sum_negative != 0:
        profit_factor = sum_positive / abs(sum_negative)

    # Evidence tier (per proposal §6.3)
    evidence_tier: EvidenceTier = (
        "TRACKING" if trade_count >= min_trades_threshold else "INSUFFICIENT_DATA"
    )

    return PerformanceOverviewItem(
        strategy_id=row.strategy_id,
        name=row.name,
        template_type_id=row.template_type_id,
        template_version=row.template_version,
        actual_state=row.actual_state,
        trade_count=trade_count,
        wins=wins,
        losses=losses,
        breakevens=breakevens,
        total_realized_pnl=total_realized_pnl,
        avg_trade_pnl=avg_trade_pnl,
        win_rate_pct=win_rate_pct,
        profit_factor=profit_factor,
        last_trade_exit_ts_wall=row.last_trade_exit_ts_wall,
        evidence_tier=evidence_tier,
    )


# ---------------------------------------------------------------------------
# Repository (thin orchestrator — delegates to pure functions above)
# ---------------------------------------------------------------------------


class PerformanceOverviewRepository:
    """Reads performance overview aggregation from strategy_closed_trades.

    Thin orchestrator: delegates query building to build_overview_query()
    and row mapping to map_row_to_item(). Designed to be injected with an
    AsyncSession (per existing repository pattern in this codebase).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_overview(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        execution_mode: str | None = None,
        template_type_id: str | None = None,
        state: str | None = None,
        sort_by: SortByField = "total_realized_pnl",
        limit: int = 200,
    ) -> list[PerformanceOverviewItem]:
        """Return per-strategy performance aggregates for the given window.

        Args:
            since: Inclusive lower bound on exit_ts_wall (None = all time).
            until: Inclusive upper bound on exit_ts_wall (None = now()).
            execution_mode: Filter by 'paper' or 'live' (None = all).
            template_type_id: Filter by strategy template (None = all).
            state: Filter by actual_state (None = all).
            sort_by: Column to sort descending.
            limit: Max rows (1-1000).

        Returns:
            List of PerformanceOverviewItem with evidence tier and derived metrics.
        """
        if until is None:
            until = datetime.now(UTC)

        query = build_overview_query(
            since=since,
            until=until,
            execution_mode=execution_mode,
            state=state,
            template_type_id=template_type_id,
            sort_by=sort_by,
            limit=limit,
        )

        result = await self._session.execute(query)
        rows = result.fetchall()

        items = [map_row_to_item(row) for row in rows]

        logger.debug(
            "PerformanceOverviewRepository returned {count} items (since={since}, until={until})",
            count=len(items),
            since=str(since) if since else "all",
            until=str(until),
        )
        return items
