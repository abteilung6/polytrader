"""Market data API routes.

Per PROPOSAL_MARKET_DATA_API.md: REST API endpoints for market tick data.
Provides endpoints for querying market data (latest ticks, historical ticks, market list).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from polytrader.api.dependencies import get_market_tick_repository
from polytrader.api.models import ErrorResponse, HistoricalTicksResponse, MarketTickResponse
from polytrader.db.models import MarketTickRecord
from polytrader.db.repository import MarketTickRepository


def _convert_record_to_response(record: MarketTickRecord) -> MarketTickResponse:
    """Convert MarketTickRecord to MarketTickResponse.

    Args:
        record: MarketTickRecord from database

    Returns:
        MarketTickResponse object

    Note:
        - Decimal fields are preserved (Pydantic handles serialization)
        - All fields map directly from record to response
    """
    return MarketTickResponse(
        tick_id=record.tick_id,
        ts_wall=record.ts_wall,
        ts_mono=record.ts_mono,
        market_slug=record.market_slug,
        outcome=record.outcome,
        best_bid=record.best_bid,
        best_ask=record.best_ask,
        mid=record.mid,
        spread=record.spread,
        spread_bps=record.spread_bps,
    )


router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get(
    "/ticks/latest",
    response_model=MarketTickResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        404: {"model": ErrorResponse, "description": "Market/outcome not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_latest_tick(
    market_slug: str = Query(
        ..., description="Market identifier (e.g., 'btc-updown-15m-1767900600')"
    ),
    outcome: str = Query(..., description="Market outcome: UP or DOWN"),
    repository: MarketTickRepository = Depends(get_market_tick_repository),  # noqa: B008
) -> MarketTickResponse:
    """Get latest tick for a market/outcome.

    Returns the most recent market tick for the specified market and outcome.
    Used for quick price checks and initial UI state.

    Args:
        market_slug: Market identifier (e.g., "btc-updown-15m-1767900600")
        outcome: Market outcome ("UP" or "DOWN")
        repository: MarketTickRepository (injected via FastAPI)

    Returns:
        MarketTickResponse with latest tick data

    Raises:
        HTTPException: 400 if outcome is invalid, 404 if no data found, 500 on database error
    """
    # Validate outcome
    if outcome not in ("UP", "DOWN"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Invalid outcome",
                detail=f"Outcome must be 'UP' or 'DOWN', got: {outcome}",
                code="INVALID_OUTCOME",
            ).model_dump(),
        )

    try:
        # Get latest tick from repository
        record = await repository.get_latest(market_slug, outcome)

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="Market not found",
                    detail=(
                        f"No tick data found for market '{market_slug}' with outcome '{outcome}'"
                    ),
                    code="MARKET_NOT_FOUND",
                ).model_dump(),
            )

        # Convert record to response
        return _convert_record_to_response(record)

    except HTTPException:
        # Re-raise HTTP exceptions (400, 404)
        raise
    except Exception as e:
        # Handle database errors and other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="Internal server error",
                detail=f"Database error: {str(e)}",
                code="DATABASE_ERROR",
            ).model_dump(),
        ) from e


@router.get(
    "/ticks/history",
    response_model=HistoricalTicksResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_historical_ticks(
    market_slug: str = Query(
        ..., description="Market identifier (e.g., 'btc-updown-15m-1767900600')"
    ),
    outcome: str = Query(..., description="Market outcome: UP or DOWN"),
    from_ts: datetime | None = Query(None, description="Start timestamp (ISO 8601 UTC, inclusive)"),  # noqa: B008
    to_ts: datetime | None = Query(None, description="End timestamp (ISO 8601 UTC, inclusive)"),  # noqa: B008
    limit: int = Query(5000, ge=1, le=10000, description="Maximum number of ticks to return"),  # noqa: B008
    repository: MarketTickRepository = Depends(get_market_tick_repository),  # noqa: B008
) -> HistoricalTicksResponse:
    """Get historical ticks for a market/outcome.

    Returns a list of market ticks for the specified market and outcome,
    optionally filtered by time range. Used for charting and historical analysis.

    Args:
        market_slug: Market identifier (e.g., "btc-updown-15m-1767900600")
        outcome: Market outcome ("UP" or "DOWN")
        from_ts: Start timestamp (inclusive, optional)
        to_ts: End timestamp (inclusive, optional)
        limit: Maximum number of ticks to return (default: 5000, max: 10000)
        repository: MarketTickRepository (injected via FastAPI)

    Returns:
        HistoricalTicksResponse with list of ticks and count

    Raises:
        HTTPException: 400 if outcome is invalid, 500 on database error

    Note:
        - For a 15-minute market window, all ticks should typically fit within the default limit
        - Ticks are ordered by ts_wall ascending, ts_mono ascending
        - Use from_ts/to_ts to narrow the time range if needed
    """
    # Validate outcome
    if outcome not in ("UP", "DOWN"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Invalid outcome",
                detail=f"Outcome must be 'UP' or 'DOWN', got: {outcome}",
                code="INVALID_OUTCOME",
            ).model_dump(),
        )

    # Validate time range
    if from_ts is not None and to_ts is not None and from_ts > to_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Invalid time range",
                detail="from_ts must be less than or equal to to_ts",
                code="INVALID_TIME_RANGE",
            ).model_dump(),
        )

    try:
        # Get historical ticks from repository
        records = await repository.get_history(
            market_slug=market_slug,
            outcome=outcome,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
        )

        # Convert records to responses
        ticks = [_convert_record_to_response(record) for record in records]

        return HistoricalTicksResponse(ticks=ticks, count=len(ticks))

    except HTTPException:
        # Re-raise HTTP exceptions (400)
        raise
    except Exception as e:
        # Handle database errors and other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="Internal server error",
                detail=f"Database error: {str(e)}",
                code="DATABASE_ERROR",
            ).model_dump(),
        ) from e
