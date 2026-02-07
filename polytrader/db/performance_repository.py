"""Repository for Performance Overview aggregation.

Per PERFORMANCE_OVERVIEW_PROPOSAL.md §6:
- DB-side GROUP BY aggregation on strategy_closed_trades.
- LEFT JOIN strategy_instances to include strategies with zero trades.
- Evidence tier (INSUFFICIENT_DATA / TRACKING) computed in Python.
- Derived metrics (win_rate_pct, profit_factor) computed in Python.

This repository reads from persisted data only — it does NOT require
the trading runtime to be running.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.logging_config import logger

# Configurable evidence threshold (per proposal §6.3 and §11)
MIN_TRADES_THRESHOLD: int = int(os.environ.get("PERF_MIN_TRADES_THRESHOLD", "1"))

EvidenceTier = Literal["INSUFFICIENT_DATA", "TRACKING"]

SortByField = Literal["total_realized_pnl", "win_rate_pct", "trade_count"]


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


# --- SQL -----------------------------------------------------------------

_OVERVIEW_SQL = text("""
SELECT
    si.strategy_id,
    si.name,
    si.template_type_id,
    si.template_version,
    si.actual_state,
    COALESCE(agg.trade_count, 0)              AS trade_count,
    COALESCE(agg.wins, 0)                     AS wins,
    COALESCE(agg.losses, 0)                   AS losses,
    COALESCE(agg.breakevens, 0)               AS breakevens,
    COALESCE(agg.total_realized_pnl, 0)       AS total_realized_pnl,
    agg.avg_trade_pnl,
    agg.last_trade_exit_ts_wall,
    COALESCE(agg.sum_positive_pnl, 0)         AS sum_positive_pnl,
    COALESCE(agg.sum_negative_pnl, 0)         AS sum_negative_pnl
FROM strategy_instances si
LEFT JOIN (
    SELECT
        ct.strategy_id,
        COUNT(*)                                                     AS trade_count,
        SUM(CASE WHEN ct.result = 'WIN'       THEN 1 ELSE 0 END)   AS wins,
        SUM(CASE WHEN ct.result = 'LOSS'      THEN 1 ELSE 0 END)   AS losses,
        SUM(CASE WHEN ct.result = 'BREAKEVEN' THEN 1 ELSE 0 END)   AS breakevens,
        SUM(ct.pnl)                                                  AS total_realized_pnl,
        AVG(ct.pnl)                                                  AS avg_trade_pnl,
        MAX(ct.exit_ts_wall)                                         AS last_trade_exit_ts_wall,
        SUM(CASE WHEN ct.pnl > 0 THEN ct.pnl ELSE 0 END)           AS sum_positive_pnl,
        SUM(CASE WHEN ct.pnl < 0 THEN ct.pnl ELSE 0 END)           AS sum_negative_pnl
    FROM strategy_closed_trades ct
    WHERE (:since::timestamptz IS NULL OR ct.exit_ts_wall >= :since)
      AND ct.exit_ts_wall <= :until
      AND (:execution_mode IS NULL OR ct.execution_mode = :execution_mode)
    GROUP BY ct.strategy_id
) agg ON si.strategy_id = agg.strategy_id
WHERE (:state IS NULL OR si.actual_state = :state)
  AND (:template_type_id IS NULL OR si.template_type_id = :template_type_id)
ORDER BY
    CASE WHEN :sort_by = 'win_rate_pct'       THEN NULL END,
    CASE WHEN :sort_by = 'trade_count'        THEN NULL END,
    COALESCE(agg.total_realized_pnl, 0) DESC
LIMIT :lim
""")

# Sort-specific variants to keep SQL clean.
# The default uses total_realized_pnl DESC (above).
# We swap ORDER BY in Python before executing.
_ORDER_CLAUSES: dict[SortByField, str] = {
    "total_realized_pnl": "ORDER BY COALESCE(agg.total_realized_pnl, 0) DESC",
    "win_rate_pct": (
        "ORDER BY "
        "CASE WHEN COALESCE(agg.trade_count, 0) > 0 "
        "THEN COALESCE(agg.wins, 0)::float / agg.trade_count ELSE 0 END DESC"
    ),
    "trade_count": "ORDER BY COALESCE(agg.trade_count, 0) DESC",
}

# We build the SQL dynamically per sort_by to avoid CASE hacks in a single text.
_OVERVIEW_SQL_TEMPLATE = """
SELECT
    si.strategy_id,
    si.name,
    si.template_type_id,
    si.template_version,
    si.actual_state,
    COALESCE(agg.trade_count, 0)              AS trade_count,
    COALESCE(agg.wins, 0)                     AS wins,
    COALESCE(agg.losses, 0)                   AS losses,
    COALESCE(agg.breakevens, 0)               AS breakevens,
    COALESCE(agg.total_realized_pnl, 0)       AS total_realized_pnl,
    agg.avg_trade_pnl,
    agg.last_trade_exit_ts_wall,
    COALESCE(agg.sum_positive_pnl, 0)         AS sum_positive_pnl,
    COALESCE(agg.sum_negative_pnl, 0)         AS sum_negative_pnl
FROM strategy_instances si
LEFT JOIN (
    SELECT
        ct.strategy_id,
        COUNT(*)                                                     AS trade_count,
        SUM(CASE WHEN ct.result = 'WIN'       THEN 1 ELSE 0 END)   AS wins,
        SUM(CASE WHEN ct.result = 'LOSS'      THEN 1 ELSE 0 END)   AS losses,
        SUM(CASE WHEN ct.result = 'BREAKEVEN' THEN 1 ELSE 0 END)   AS breakevens,
        SUM(ct.pnl)                                                  AS total_realized_pnl,
        AVG(ct.pnl)                                                  AS avg_trade_pnl,
        MAX(ct.exit_ts_wall)                                         AS last_trade_exit_ts_wall,
        SUM(CASE WHEN ct.pnl > 0 THEN ct.pnl ELSE 0 END)           AS sum_positive_pnl,
        SUM(CASE WHEN ct.pnl < 0 THEN ct.pnl ELSE 0 END)           AS sum_negative_pnl
    FROM strategy_closed_trades ct
    WHERE (:since::timestamptz IS NULL OR ct.exit_ts_wall >= :since)
      AND ct.exit_ts_wall <= :until
      AND (:execution_mode IS NULL OR ct.execution_mode = :execution_mode)
    GROUP BY ct.strategy_id
) agg ON si.strategy_id = agg.strategy_id
WHERE (:state IS NULL OR si.actual_state = :state)
  AND (:template_type_id IS NULL OR si.template_type_id = :template_type_id)
{order_clause}
LIMIT :lim
"""


class PerformanceOverviewRepository:
    """Reads performance overview aggregation from strategy_closed_trades.

    Designed to be injected with an AsyncSession (per existing repo pattern).
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

        # Build SQL with the correct ORDER BY clause
        order_clause = _ORDER_CLAUSES.get(sort_by, _ORDER_CLAUSES["total_realized_pnl"])
        sql = text(_OVERVIEW_SQL_TEMPLATE.format(order_clause=order_clause))

        params: dict[str, Any] = {
            "since": since,
            "until": until,
            "execution_mode": execution_mode,
            "state": state,
            "template_type_id": template_type_id,
            "lim": min(max(limit, 1), 1000),
        }

        result = await self._session.execute(sql, params)
        rows = result.fetchall()

        items: list[PerformanceOverviewItem] = []
        for row in rows:
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
                "TRACKING" if trade_count >= MIN_TRADES_THRESHOLD else "INSUFFICIENT_DATA"
            )

            items.append(
                PerformanceOverviewItem(
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
            )

        logger.debug(
            "PerformanceOverviewRepository returned {count} items (since={since}, until={until})",
            count=len(items),
            since=str(since) if since else "all",
            until=str(until),
        )
        return items
