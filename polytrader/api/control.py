"""Control API routes (state and command endpoints).

Per Platform_Proposal.md: Elite-style API design with separation of
state endpoints (/state/*) and command endpoints (/commands/*).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from polytrader.platform.orchestrator import PlatformOrchestrator

from fastapi import APIRouter, Depends, HTTPException, status

from polytrader.api.dependencies import (
    get_control_command_repo,
    get_event_repository,
    get_execution_control,
    get_execution_control_repo,
    get_in_memory_strategy_registry,
    get_live_strategy_repo,
    get_orchestrator,
    get_performance_overview_repo,
    get_strategy_registry,
)
from polytrader.api.models import (
    ActivateStrategyRequest,
    ClosedTradeItem,
    CommandEnvelopeResponse,
    CommandStatusResponse,
    CreateStrategyRequest,
    DeactivateStrategyRequest,
    DisableExecutionRequest,
    EnableExecutionRequest,
    ErrorResponse,
    ExecutionStateResponse,
    HealthGates,
    HealthGateStatus,
    HealthResponse,
    KillSwitchRequest,
    KillSwitchResetRequest,
    LiveStrategiesResponse,
    PerformanceOverviewItemResponse,
    PerformanceOverviewResponse,
    PerformanceResponse,
    PerformanceSummary,
    RunIdentityResponse,
    StrategiesResponse,
    StrategyOrderItem,
    StrategyOrdersResponse,
    StrategyResponse,
    StrategySignalItem,
    StrategySignalsResponse,
    StrategyTypeResponse,
    StrategyTypesResponse,
    UpdateStrategyRequest,
    ValidateStrategyConfigRequest,
    ValidateStrategyConfigResponse,
    VersionConflictResponse,
)
from polytrader.db.models import ControlCommandRecord, EventRecord
from polytrader.db.models import StrategyRecord as StrategyRecordModel
from polytrader.db.performance_repository import (
    MIN_TRADES_THRESHOLD,
    PerformanceOverviewRepository,
    SortByField,
)
from polytrader.db.repository import EventRepository
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.registry import StrategyRegistry
from polytrader.strategies.registry import StrategyRegistry as InMemoryStrategyRegistry
from polytrader.strategies.registry import StrategyTemplate

router = APIRouter(prefix="/api/v1", tags=["control"])


# ============================================================================
# State Endpoints (Reads)
# ============================================================================


@router.get("/state/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Get system health with individual gate statuses.

    Returns overall status and individual gate statuses (db, market_data_freshness, etc.).
    Overall status = worst gate status (down > degraded > ok).

    Note: Health gates implementation is basic in this commit.
    Full health gate checks will be implemented in later commits.
    """
    # Basic health check: database connectivity
    # TODO: Add full health gate checks (market_data_freshness, event_bus_lag, etc.)
    try:
        # Try to get execution control (tests DB connectivity)
        from polytrader.api.dependencies import get_db_session

        async for session in get_db_session():
            from polytrader.platform.control import ExecutionControlRepository

            repo = ExecutionControlRepository(session)
            await repo.get_control()
            db_status = HealthGateStatus(status="ok", message="Database connected")
            break
    except Exception:
        db_status = HealthGateStatus(status="down", message="Database connection failed")

    # Placeholder for other gates (will be implemented in later commits)
    gates = HealthGates(
        db=db_status,
        market_data_freshness=HealthGateStatus(status="ok", message="Not implemented yet"),
        event_bus_lag=HealthGateStatus(status="ok", message="Not implemented yet"),
        venue_connectivity=HealthGateStatus(status="ok", message="Not implemented yet"),
        risk_engine=HealthGateStatus(status="ok", message="Not implemented yet"),
        clock_skew_ms=0,
    )

    # Overall status = worst gate status
    gate_statuses = [
        gates.db.status,
        gates.market_data_freshness.status,
        gates.event_bus_lag.status,
        gates.venue_connectivity.status,
        gates.risk_engine.status,
    ]
    if "down" in gate_statuses:
        overall = "down"
    elif "degraded" in gate_statuses:
        overall = "degraded"
    else:
        overall = "ok"

    return HealthResponse(overall=overall, gates=gates)


@router.get("/state/execution", response_model=ExecutionStateResponse)
async def get_execution_state(
    execution_repo: ExecutionControlRepository = Depends(get_execution_control_repo),  # noqa: B008
    exec_control: ExecutionControl | None = Depends(get_execution_control),  # noqa: B008
) -> ExecutionStateResponse:
    """Get execution control state (with version for optimistic concurrency).

    Per boot reconciliation fix: execution_enabled is read from the **in-memory
    runtime** state when the platform is running. This ensures the UI always
    shows what the execution router will actually do. The DB is used for
    metadata (version, updated_at, updated_by, reason) and as fallback when
    the platform is not running (exec_control is None).

    kill_switch_active is always in-memory only (not persisted in DB).
    """
    control = await execution_repo.get_control()

    # Runtime state is the source of truth for execution gating.
    # Fall back to DB state only when platform is not running.
    if exec_control is not None:
        execution_enabled = exec_control.execution_enabled
        kill_switch_active = exec_control.kill_switch_active
    else:
        execution_enabled = control.execution_enabled
        kill_switch_active = False

    return ExecutionStateResponse(
        execution_enabled=execution_enabled,
        kill_switch_active=kill_switch_active,
        version=control.version,
        updated_at=control.updated_at,
        updated_by=control.updated_by,
        reason=control.reason,
    )


@router.get("/state/live-strategies", response_model=LiveStrategiesResponse)
async def get_live_strategies(
    live_repo: LiveStrategyRepository = Depends(get_live_strategy_repo),  # noqa: B008
) -> LiveStrategiesResponse:
    """Get active live strategies."""
    active = await live_repo.list_active()
    return LiveStrategiesResponse(active_strategies=list(active))


def _strategy_record_to_response(
    s: StrategyRecordModel,
    *,
    is_live_activated: bool,
) -> StrategyResponse:
    """Map DB StrategyRecord to API StrategyResponse (single source of truth).

    is_live_activated: True iff strategy_id is in the active live strategies list
    (controls Mode badge Paper/Live). Distinct from lifecycle: Start = paper mode only.
    """
    return StrategyResponse(
        strategy_id=s.strategy_id,
        name=s.name,
        description=s.description,
        config=s.config,
        template_type_id=s.template_type_id,
        template_version=s.template_version,
        desired_state=s.desired_state,
        actual_state=s.actual_state,
        last_transition_at=s.last_transition_at,
        last_error=s.last_error,
        run_identity=(
            RunIdentityResponse(
                template_code_ref=s.template_code_ref,
                config_hash=s.config_hash,
                dependency_set=s.dependency_set,
                market_data_snapshot_ref=s.market_data_snapshot_ref,
            )
            if (s.template_code_ref or s.dependency_set or s.market_data_snapshot_ref)
            else None
        ),
        deployment_id=str(s.deployment_id) if s.deployment_id else None,
        run_id=s.run_id,
        created_at=s.created_at,
        updated_at=s.updated_at,
        enabled=is_live_activated,
    )


@router.get("/state/strategies", response_model=StrategiesResponse)
async def get_strategies(
    registry: StrategyRegistry = Depends(get_strategy_registry),  # noqa: B008
    live_repo: LiveStrategyRepository = Depends(get_live_strategy_repo),  # noqa: B008
) -> StrategiesResponse:
    """Get all strategies in registry.

    enabled (Mode Paper/Live) reflects activation for live trading, not lifecycle.
    """
    strategies = await registry.list_strategies()
    active_ids = await live_repo.list_active()
    return StrategiesResponse(
        strategies=[
            _strategy_record_to_response(s, is_live_activated=(s.strategy_id in active_ids))
            for s in strategies
        ]
    )


@router.get("/state/strategies/templates", response_model=StrategyTypesResponse)
async def list_strategy_templates(
    in_memory_registry: InMemoryStrategyRegistry = Depends(get_in_memory_strategy_registry),  # noqa: B008
) -> StrategyTypesResponse:
    """List all available strategy templates.

    Per Commit 15: Template discovery endpoint for clients to discover
    available strategy types and their versions.

    Returns:
        StrategyTypesResponse with list of all registered templates
    """
    templates = in_memory_registry.list_templates()

    # Group templates by type_id to get available versions
    type_map: dict[str, list[str]] = {}
    template_map: dict[str, StrategyTemplate] = {}

    for template in templates:
        if template.type_id not in type_map:
            type_map[template.type_id] = []
            # Use the first template we encounter for name/description
            # (all versions should have same name/description)
            template_map[template.type_id] = template
        type_map[template.type_id].append(template.version)

    # Sort versions for each type
    for type_id in type_map:
        type_map[type_id] = sorted(type_map[type_id])

    # Build response
    types = []
    for type_id, versions in type_map.items():
        template = template_map[type_id]
        types.append(
            StrategyTypeResponse(
                type_id=type_id,
                name=template.name,
                description=template.description,
                available_versions=versions,
                parameter_schema=template.parameter_schema.to_openapi_schema(),
            )
        )

    return StrategyTypesResponse(types=types)


@router.get(
    "/state/strategies/templates/{type_id}",
    response_model=StrategyTypeResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Template not found"},
    },
)
async def get_strategy_template(
    type_id: str,
    in_memory_registry: InMemoryStrategyRegistry = Depends(get_in_memory_strategy_registry),  # noqa: B008
) -> StrategyTypeResponse:
    """Get details for a specific strategy template type.

    Per Commit 15: Returns template information including all available versions
    and parameter schema.

    Args:
        type_id: Template type identifier (e.g., "simple_threshold")

    Returns:
        StrategyTypeResponse with template details

    Raises:
        HTTPException: 404 if template type not found
    """
    # Get all versions for this type
    versions = in_memory_registry.list_versions(type_id)
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                error="Template not found",
                detail=f"No template found with type_id: {type_id}",
            ).model_dump(),
        )

    # Get latest version template for name/description
    latest_version = versions[-1]
    template = in_memory_registry.get(type_id, latest_version)

    return StrategyTypeResponse(
        type_id=type_id,
        name=template.name,
        description=template.description,
        available_versions=versions,
        parameter_schema=template.parameter_schema.to_openapi_schema(),
    )


@router.get(
    "/state/strategies/templates/{type_id}/versions/{version}",
    response_model=StrategyTypeResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Template version not found"},
    },
)
async def get_strategy_template_version(
    type_id: str,
    version: str,
    in_memory_registry: InMemoryStrategyRegistry = Depends(get_in_memory_strategy_registry),  # noqa: B008
) -> StrategyTypeResponse:
    """Get details for a specific strategy template version.

    Per Commit 15: Returns template information for a specific version
    including parameter schema.

    Args:
        type_id: Template type identifier (e.g., "simple_threshold")
        version: Template version (e.g., "1.0.0")

    Returns:
        StrategyTypeResponse with template details (single version in available_versions)

    Raises:
        HTTPException: 404 if template version not found
    """
    try:
        template = in_memory_registry.get(type_id, version)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                error="Template version not found",
                detail=str(e),
            ).model_dump(),
        ) from e

    return StrategyTypeResponse(
        type_id=type_id,
        name=template.name,
        description=template.description,
        available_versions=[version],  # Single version
        parameter_schema=template.parameter_schema.to_openapi_schema(),
    )


def _event_record_to_signal_item(record: EventRecord) -> StrategySignalItem:
    """Map EventRecord (SignalEvent) to API StrategySignalItem."""
    data = record.event_data
    return StrategySignalItem(
        event_id=str(record.event_id),
        ts_wall=record.ts_wall,
        market_slug=data["market_slug"],
        outcome=data["outcome"],
        p_up=float(data["p_up"]),
        p_down=float(data["p_down"]),
        edge=float(data["edge"]),
        confidence=float(data["confidence"]),
        model_id=data["model_id"],
        model_version=data["model_version"],
        snapshot_hash=data.get("snapshot_hash"),
        rationale=data.get("rationale"),
    )


@router.get(
    "/state/strategies/{strategy_id}/signals",
    response_model=StrategySignalsResponse,
)
async def get_strategy_signals(
    strategy_id: str,
    event_repo: EventRepository = Depends(get_event_repository),  # noqa: B008
    limit: int = 100,
    cursor: str | None = None,
) -> StrategySignalsResponse:
    """Get paginated signals for a strategy (newest first).

    Query params: limit (default 100, max 500), cursor (optional).
    Returns empty list when strategy has no signals.
    """
    records, next_cursor = await event_repo.read_signal_events_by_strategy(
        strategy_id=strategy_id,
        limit=limit,
        cursor=cursor,
    )
    items = [_event_record_to_signal_item(r) for r in records]
    return StrategySignalsResponse(items=items, next_cursor=next_cursor)


def _event_record_to_order_item(record: EventRecord) -> StrategyOrderItem:
    """Map EventRecord (OrderCreatedEvent) to API StrategyOrderItem."""
    data = record.event_data
    intent = data["intent"]
    execution_mode_raw = data.get("execution_mode", "paper")
    execution_mode: Literal["paper", "live"] = (
        execution_mode_raw if execution_mode_raw in ("paper", "live") else "paper"
    )
    return StrategyOrderItem(
        order_id=data["order_id"],
        client_order_id=data["client_order_id"],
        ts_wall=record.ts_wall,
        market_slug=intent["market_slug"],
        side=intent["side"],
        size=float(intent["size"]),
        limit_price=float(intent["limit_price"]),
        status="PENDING_SUBMIT",
        execution_mode=execution_mode,
    )


@router.get(
    "/state/strategies/{strategy_id}/orders",
    response_model=StrategyOrdersResponse,
)
async def get_strategy_orders(
    strategy_id: str,
    event_repo: EventRepository = Depends(get_event_repository),  # noqa: B008
    limit: int = 100,
    cursor: str | None = None,
) -> StrategyOrdersResponse:
    """Get paginated orders for a strategy (newest first).

    Query params: limit (default 100, max 500), cursor (optional).
    Returns empty list when strategy has no orders.
    execution_mode (paper | live) is included per row for UI badge.
    """
    records, next_cursor = await event_repo.read_order_events_by_strategy(
        strategy_id=strategy_id,
        limit=limit,
        cursor=cursor,
    )
    items = [_event_record_to_order_item(r) for r in records]
    return StrategyOrdersResponse(items=items, next_cursor=next_cursor)


def _event_record_to_closed_trade_item(record: EventRecord) -> ClosedTradeItem:
    """Map EventRecord (StrategyClosedTradeEvent) to API ClosedTradeItem."""
    data = record.event_data
    entry_time = float(data["entry_time"])
    exit_time = float(data["exit_time"])
    execution_mode_raw = data.get("execution_mode", "paper")
    execution_mode: Literal["paper", "live"] = (
        execution_mode_raw if execution_mode_raw in ("paper", "live") else "paper"
    )
    outcome: Literal["UP", "DOWN"] = data["outcome"] if data["outcome"] in ("UP", "DOWN") else "UP"
    return ClosedTradeItem(
        market_slug=data["market_slug"],
        outcome=outcome,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_ts_wall=record.ts_wall,
        entry_price=float(data["entry_price"]),
        exit_price=float(data["exit_price"]),
        size=float(data["size"]),
        pnl=float(data["pnl"]),
        pnl_pct=float(data["pnl_pct"]),
        result=data["result"],
        execution_mode=execution_mode,
        duration_seconds=max(0.0, exit_time - entry_time),
    )


def _closed_trade_items_to_summary(
    items: list[ClosedTradeItem],
) -> PerformanceSummary:
    """Compute PerformanceSummary from a page of ClosedTradeItem."""
    total_trades = len(items)
    if total_trades == 0:
        return PerformanceSummary(
            total_realized_pnl=0.0,
            total_trades=0,
            win_rate_pct=None,
            current_drawdown=None,
            max_drawdown=None,
        )
    total_realized_pnl = sum(t.pnl for t in items)
    wins = sum(1 for t in items if t.result == "WIN")
    win_rate_pct = (wins / total_trades) * 100.0
    return PerformanceSummary(
        total_realized_pnl=total_realized_pnl,
        total_trades=total_trades,
        win_rate_pct=win_rate_pct,
        current_drawdown=None,
        max_drawdown=None,
    )


@router.get(
    "/state/strategies/performance/overview",
    response_model=PerformanceOverviewResponse,
)
async def get_performance_overview(
    repo: PerformanceOverviewRepository = Depends(get_performance_overview_repo),  # noqa: B008
    since: datetime | None = None,
    until: datetime | None = None,
    execution_mode: Literal["paper", "live"] | None = None,
    template_type_id: str | None = None,
    state: str | None = None,
    sort_by: SortByField = "total_realized_pnl",
    limit: int = 200,
) -> PerformanceOverviewResponse:
    """Get aggregated performance overview for all strategy instances.

    Per PERFORMANCE_OVERVIEW_PROPOSAL.md §7:
    - DB-side aggregation on strategy_closed_trades table.
    - LEFT JOIN to strategy_instances for registry metadata.
    - Evidence tier (INSUFFICIENT_DATA / TRACKING) per trade count threshold.
    - Does NOT require the trader runtime process.

    Query params:
        since: ISO 8601 UTC lower bound on exit_ts_wall (omit for all time).
        until: ISO 8601 UTC upper bound on exit_ts_wall (default: server now()).
        execution_mode: Filter by paper or live (omit for all).
        template_type_id: Filter by strategy template.
        state: Filter by lifecycle state (RUNNING, STOPPED, etc.).
        sort_by: Sort column descending (total_realized_pnl, win_rate_pct, trade_count).
        limit: Max rows (1-1000, default 200).
    """
    items = await repo.get_overview(
        since=since,
        until=until,
        execution_mode=execution_mode,
        template_type_id=template_type_id,
        state=state,
        sort_by=sort_by,
        limit=limit,
    )

    # Resolve the actual "until" that was used (repo defaults None → now())
    resolved_until = until if until is not None else datetime.now(UTC)

    response_items = [
        PerformanceOverviewItemResponse(
            strategy_id=item.strategy_id,
            name=item.name,
            template_type_id=item.template_type_id,
            template_version=item.template_version,
            actual_state=item.actual_state,
            trade_count=item.trade_count,
            wins=item.wins,
            losses=item.losses,
            breakevens=item.breakevens,
            total_realized_pnl=item.total_realized_pnl,
            avg_trade_pnl=item.avg_trade_pnl,
            win_rate_pct=item.win_rate_pct,
            profit_factor=item.profit_factor,
            last_trade_exit_ts_wall=item.last_trade_exit_ts_wall,
            evidence_tier=item.evidence_tier,
        )
        for item in items
    ]

    return PerformanceOverviewResponse(
        from_ts_wall=since,
        to_ts_wall=resolved_until,
        execution_mode=execution_mode,
        min_trades_threshold=MIN_TRADES_THRESHOLD,
        items=response_items,
    )


@router.get(
    "/state/strategies/{strategy_id}/performance",
    response_model=PerformanceResponse,
)
async def get_strategy_performance(
    strategy_id: str,
    event_repo: EventRepository = Depends(get_event_repository),  # noqa: B008
    from_ts: float | None = None,
    to_ts: float | None = None,
    execution_mode: Literal["paper", "live"] | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> PerformanceResponse:
    """Get past performance for a strategy: summary + paginated closed trades.

    Query params: from_ts, to_ts (optional ts_mono range), execution_mode
    (paper | live | omit for all), limit (default 100, max 500), cursor.
    Summary is computed from the returned page of items.
    """
    records, next_cursor = await event_repo.read_closed_trade_events_by_strategy(
        strategy_id=strategy_id,
        from_ts=from_ts,
        to_ts=to_ts,
        execution_mode=execution_mode,
        limit=limit,
        cursor=cursor,
    )
    items = [_event_record_to_closed_trade_item(r) for r in records]
    summary = _closed_trade_items_to_summary(items)
    return PerformanceResponse(summary=summary, items=items, next_cursor=next_cursor)


@router.get(
    "/state/strategies/{strategy_id}",
    response_model=StrategyResponse,
    responses={
        404: {"description": "Strategy not found"},
    },
)
async def get_strategy_by_id(
    strategy_id: str,
    registry: StrategyRegistry = Depends(get_strategy_registry),  # noqa: B008
    live_repo: LiveStrategyRepository = Depends(get_live_strategy_repo),  # noqa: B008
) -> StrategyResponse:
    """Get a single strategy by ID.

    Returns 404 if the strategy is not in the registry.
    enabled reflects activation for live trading (in active live strategies list).
    """
    strategy = await registry.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    active_ids = await live_repo.list_active()
    return _strategy_record_to_response(strategy, is_live_activated=(strategy_id in active_ids))


@router.post(
    "/state/strategies/validate",
    response_model=ValidateStrategyConfigResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Template not found or version resolution failed",
        },
    },
)
async def validate_strategy_config(
    request: ValidateStrategyConfigRequest,
    in_memory_registry: InMemoryStrategyRegistry = Depends(get_in_memory_strategy_registry),  # noqa: B008
) -> ValidateStrategyConfigResponse:
    """Validate a strategy configuration against a template schema.

    Per Commit 16: This endpoint allows clients to validate configurations
    before creating strategy instances. Returns validation results with
    clear error messages.

    Args:
        request: Validation request with template_type_id, version_selector, and config

    Returns:
        ValidateStrategyConfigResponse with validation results

    Raises:
        HTTPException: 400 if template not found or version resolution fails
    """
    from polytrader.strategies.version import VersionResolutionError, VersionSelector

    # Resolve version selector to exact version
    try:
        available_versions = in_memory_registry.list_versions(request.template_type_id)
        if not available_versions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error="Template not found",
                    detail=f"No template found with type_id: {request.template_type_id}",
                ).model_dump(),
            )

        # Convert VersionSelectorRequest to VersionSelector
        version_selector = VersionSelector(
            exact=request.version_selector.exact,
            channel=request.version_selector.channel,
            major=request.version_selector.major,
        )
        template_version = version_selector.resolve(available_versions)
    except (ValueError, VersionResolutionError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Version resolution failed",
                detail=str(e),
            ).model_dump(),
        ) from e

    # Get template and validate config
    try:
        template = in_memory_registry.get(request.template_type_id, template_version)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Template not found",
                detail=str(e),
            ).model_dump(),
        ) from e

    # Validate config against template's parameter schema
    validation_errors = template.parameter_schema.validate(request.config)

    # For now, we don't have warnings (could add in future for deprecations, etc.)
    warnings: list[str] = []

    return ValidateStrategyConfigResponse(
        valid=len(validation_errors) == 0,
        errors=validation_errors,
        warnings=warnings,
        template_type_id=request.template_type_id,
        template_version=template_version,
    )


@router.get(
    "/state/commands/{command_id}",
    response_model=CommandStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Command not found"},
    },
)
async def get_command_status(
    command_id: str,
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
) -> CommandStatusResponse:
    """Get command status by command_id."""
    cmd = await command_repo.get_command(command_id)

    if cmd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                error="Command not found",
                detail=f"No command found with command_id: {command_id}",
            ).model_dump(),
        )

    return CommandStatusResponse(
        command_id=str(cmd.command_id),
        type=cmd.command_type,
        status=cmd.status,
        error_message=cmd.error_message,
        created_at=cmd.created_at,
        applied_at=cmd.applied_at,
        reason=cmd.reason,
        issued_by=cmd.issued_by,
    )


# ============================================================================
# Command Endpoints (Writes)
# ============================================================================


@router.post(
    "/commands/execution/enable",
    response_model=CommandEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        409: {"model": VersionConflictResponse, "description": "Version conflict"},
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def enable_execution(
    request: EnableExecutionRequest,
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
    execution_repo: ExecutionControlRepository = Depends(get_execution_control_repo),  # noqa: B008
) -> CommandEnvelopeResponse:
    """Enable execution (creates command in queue).

    Idempotent: If client_request_id already exists, returns existing command_id.
    Version check: If expected_version != current version, returns 409 Conflict.
    """
    # Check idempotency
    existing = await command_repo.find_by_client_request_id(
        "enable_execution", None, request.client_request_id
    )
    if existing:
        # Return existing command, but always return "pending" status in envelope
        # (actual status can be checked via GET /state/commands/{command_id})
        return CommandEnvelopeResponse(
            command_id=str(existing.command_id),
            status="pending",  # Always return "pending" for idempotency (per API contract)
            submitted_at=existing.created_at,
            links={"status": f"/api/v1/state/commands/{existing.command_id}"},
        )

    # Check version if provided
    if request.expected_version is not None:
        current = await execution_repo.get_control()
        if current.version != request.expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=VersionConflictResponse(
                    expected_version=request.expected_version,
                    actual_version=current.version,
                    detail=(
                        f"Version mismatch: expected {request.expected_version}, "
                        f"got {current.version}"
                    ),
                ).model_dump(),
            )

    # Create command
    cmd = ControlCommandRecord(
        command_type="enable_execution",
        reason=request.reason,
        issued_by=request.issued_by,
        client_request_id=request.client_request_id,
        expected_version=request.expected_version,
    )
    command_id = await command_repo.create_command(cmd)

    return CommandEnvelopeResponse(
        command_id=command_id,
        status="pending",
        submitted_at=cmd.created_at,
        links={"status": f"/api/v1/state/commands/{command_id}"},
    )


@router.post(
    "/commands/execution/disable",
    response_model=CommandEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        409: {"model": VersionConflictResponse, "description": "Version conflict"},
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def disable_execution(
    request: DisableExecutionRequest,
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
    execution_repo: ExecutionControlRepository = Depends(get_execution_control_repo),  # noqa: B008
) -> CommandEnvelopeResponse:
    """Disable execution (creates command in queue).

    Idempotent: If client_request_id already exists, returns existing command_id.
    Version check: If expected_version != current version, returns 409 Conflict.
    """
    # Check idempotency
    existing = await command_repo.find_by_client_request_id(
        "disable_execution", None, request.client_request_id
    )
    if existing:
        # Return existing command, but always return "pending" status in envelope
        # (actual status can be checked via GET /state/commands/{command_id})
        return CommandEnvelopeResponse(
            command_id=str(existing.command_id),
            status="pending",  # Always return "pending" for idempotency (per API contract)
            submitted_at=existing.created_at,
            links={"status": f"/api/v1/state/commands/{existing.command_id}"},
        )

    # Check version if provided
    if request.expected_version is not None:
        current = await execution_repo.get_control()
        if current.version != request.expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=VersionConflictResponse(
                    expected_version=request.expected_version,
                    actual_version=current.version,
                    detail=(
                        f"Version mismatch: expected {request.expected_version}, "
                        f"got {current.version}"
                    ),
                ).model_dump(),
            )

    # Create command
    cmd = ControlCommandRecord(
        command_type="disable_execution",
        reason=request.reason,
        issued_by=request.issued_by,
        client_request_id=request.client_request_id,
        expected_version=request.expected_version,
    )
    command_id = await command_repo.create_command(cmd)

    return CommandEnvelopeResponse(
        command_id=command_id,
        status="pending",
        submitted_at=cmd.created_at,
        links={"status": f"/api/v1/state/commands/{command_id}"},
    )


@router.post(
    "/commands/execution/kill-switch",
    response_model=CommandEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Platform not running"},
    },
)
async def activate_kill_switch(
    request: KillSwitchRequest,
    exec_control: ExecutionControl | None = Depends(get_execution_control),  # noqa: B008
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
    execution_repo: ExecutionControlRepository = Depends(get_execution_control_repo),  # noqa: B008
) -> CommandEnvelopeResponse:
    """Activate kill switch (emergency stop — immediate, not queued).

    Per flows.mdc §13: Kill switch provides immediate stop-trading policy.
    This endpoint directly applies the kill switch to in-memory state,
    disables execution in the DB, and creates an audit command record.

    Unlike enable/disable which go through the command queue, the kill switch
    is applied immediately because it is a safety-critical emergency action.

    After activation:
    - execution_enabled = false
    - kill_switch_active = true
    - KillSwitchEvent emitted
    - All pending orders will be rejected by execution router

    Reset requires a separate call to /commands/execution/kill-switch/reset
    followed by /commands/execution/enable.
    """
    if exec_control is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="Platform not running",
                detail="Kill switch requires the platform runtime to be active. "
                "ExecutionControl is not available.",
            ).model_dump(),
        )

    # Apply immediately to in-memory state (not queued)
    await exec_control.set_kill_switch(
        active=True,
        reason=request.reason,
        cancel_open_orders=request.cancel_open_orders,
        triggered_by="operator",
    )

    # Persist execution_enabled=false in DB for consistency
    await execution_repo.update_control(
        execution_enabled=False,
        updated_by=request.issued_by,
        reason=f"Kill switch activated: {request.reason}",
    )

    # Create audit command record (marked as applied immediately)
    now = datetime.now(UTC)
    cmd = ControlCommandRecord(
        command_type="kill_switch_activate",
        reason=request.reason,
        issued_by=request.issued_by,
    )
    command_id = await command_repo.create_command(cmd)
    await command_repo.mark_applied(command_id)

    return CommandEnvelopeResponse(
        command_id=command_id,
        status="applied",
        submitted_at=now,
        links={"status": f"/api/v1/state/commands/{command_id}"},
    )


@router.post(
    "/commands/execution/kill-switch/reset",
    response_model=CommandEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Platform not running"},
    },
)
async def reset_kill_switch(
    request: KillSwitchResetRequest,
    exec_control: ExecutionControl | None = Depends(get_execution_control),  # noqa: B008
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
) -> CommandEnvelopeResponse:
    """Reset (deactivate) the kill switch.

    Resetting the kill switch does NOT re-enable execution. The operator must
    separately call /commands/execution/enable to resume trading. This is a
    deliberate safety measure to prevent accidental re-enablement.

    After reset:
    - kill_switch_active = false
    - execution_enabled remains false (unchanged)
    - KillSwitchEvent emitted (triggered=false)
    """
    if exec_control is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="Platform not running",
                detail="Kill switch reset requires the platform runtime to be active. "
                "ExecutionControl is not available.",
            ).model_dump(),
        )

    # Apply immediately to in-memory state
    await exec_control.set_kill_switch(
        active=False,
        reason=request.reason,
        cancel_open_orders=False,
        triggered_by="operator",
    )

    # Create audit command record (marked as applied immediately)
    now = datetime.now(UTC)
    cmd = ControlCommandRecord(
        command_type="kill_switch_reset",
        reason=request.reason,
        issued_by=request.issued_by,
    )
    command_id = await command_repo.create_command(cmd)
    await command_repo.mark_applied(command_id)

    return CommandEnvelopeResponse(
        command_id=command_id,
        status="applied",
        submitted_at=now,
        links={"status": f"/api/v1/state/commands/{command_id}"},
    )


@router.post(
    "/commands/live-strategies/{strategy_id}/activate",
    response_model=CommandEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def activate_strategy(
    strategy_id: str,
    request: ActivateStrategyRequest,
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
) -> CommandEnvelopeResponse:
    """Activate strategy for live trading (creates command in queue).

    Idempotent: If client_request_id already exists, returns existing command_id.
    """
    # Check idempotency
    existing = await command_repo.find_by_client_request_id(
        "add_active_strategy", strategy_id, request.client_request_id
    )
    if existing:
        # Return existing command, but always return "pending" status in envelope
        # (actual status can be checked via GET /state/commands/{command_id})
        return CommandEnvelopeResponse(
            command_id=str(existing.command_id),
            status="pending",  # Always return "pending" for idempotency (per API contract)
            submitted_at=existing.created_at,
            links={"status": f"/api/v1/state/commands/{existing.command_id}"},
        )

    # Create command
    cmd = ControlCommandRecord(
        command_type="add_active_strategy",
        strategy_id=strategy_id,
        reason=request.reason,
        issued_by=request.issued_by,
        client_request_id=request.client_request_id,
    )
    command_id = await command_repo.create_command(cmd)

    return CommandEnvelopeResponse(
        command_id=command_id,
        status="pending",
        submitted_at=cmd.created_at,
        links={"status": f"/api/v1/state/commands/{command_id}"},
    )


@router.post(
    "/commands/live-strategies/{strategy_id}/deactivate",
    response_model=CommandEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def deactivate_strategy(
    strategy_id: str,
    request: DeactivateStrategyRequest,
    command_repo: ControlCommandRepository = Depends(get_control_command_repo),  # noqa: B008
) -> CommandEnvelopeResponse:
    """Deactivate strategy for live trading (creates command in queue).

    Idempotent: If client_request_id already exists, returns existing command_id.
    """
    # Check idempotency
    existing = await command_repo.find_by_client_request_id(
        "remove_active_strategy", strategy_id, request.client_request_id
    )
    if existing:
        # Return existing command, but always return "pending" status in envelope
        # (actual status can be checked via GET /state/commands/{command_id})
        return CommandEnvelopeResponse(
            command_id=str(existing.command_id),
            status="pending",  # Always return "pending" for idempotency (per API contract)
            submitted_at=existing.created_at,
            links={"status": f"/api/v1/state/commands/{existing.command_id}"},
        )

    # Create command
    cmd = ControlCommandRecord(
        command_type="remove_active_strategy",
        strategy_id=strategy_id,
        reason=request.reason,
        issued_by=request.issued_by,
        client_request_id=request.client_request_id,
    )
    command_id = await command_repo.create_command(cmd)

    return CommandEnvelopeResponse(
        command_id=command_id,
        status="pending",
        submitted_at=cmd.created_at,
        links={"status": f"/api/v1/state/commands/{command_id}"},
    )


@router.post(
    "/commands/strategies",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        409: {"model": ErrorResponse, "description": "Strategy already exists"},
    },
)
async def create_strategy(
    request: CreateStrategyRequest,
    registry: StrategyRegistry = Depends(get_strategy_registry),  # noqa: B008
    in_memory_registry: InMemoryStrategyRegistry = Depends(get_in_memory_strategy_registry),  # noqa: B008
    orchestrator: "PlatformOrchestrator | None" = Depends(get_orchestrator),  # noqa: B008
    live_repo: LiveStrategyRepository = Depends(get_live_strategy_repo),  # noqa: B008
) -> StrategyResponse:
    """Create a new strategy in registry.

    Per Commit 17: This endpoint now:
    - Resolves version selector to exact version
    - Validates config before creation
    - Calculates config_hash for reproducibility
    - Generates deployment_id for correlation
    - Adds reproducibility metadata (run_identity)
    """
    import uuid

    from polytrader.strategies.reproducibility import (
        calculate_config_hash,
        create_run_identity,
    )
    from polytrader.strategies.version import VersionResolutionError, VersionSelector

    # Resolve version selector to exact version
    try:
        available_versions = in_memory_registry.list_versions(request.template_type_id)
        if not available_versions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error="Template not found",
                    detail=f"No template found with type_id: {request.template_type_id}",
                ).model_dump(),
            )

        # Convert VersionSelectorRequest to VersionSelector
        version_selector = VersionSelector(
            exact=request.version_selector.exact,
            channel=request.version_selector.channel,
            major=request.version_selector.major,
        )
        template_version = version_selector.resolve(available_versions)
    except (ValueError, VersionResolutionError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Version resolution failed",
                detail=str(e),
            ).model_dump(),
        ) from e

    # Get template and validate config before creation
    try:
        template = in_memory_registry.get(request.template_type_id, template_version)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Template not found",
                detail=str(e),
            ).model_dump(),
        ) from e

    # Validate config against template's parameter schema
    validation_errors = template.parameter_schema.validate(request.config)
    if validation_errors:
        error_msg = "; ".join(validation_errors)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="Config validation failed",
                detail=error_msg,
            ).model_dump(),
        )

    # Calculate config_hash for reproducibility
    config_hash = calculate_config_hash(request.config)

    # Create run_identity with reproducibility metadata
    # For now, use placeholder for template_code_ref (could be git SHA in production)
    run_identity = create_run_identity(
        template_code_ref="local_dev",  # TODO: Replace with actual git SHA in production
        config=request.config,
        market_data_snapshot_ref=None,  # Will be set when strategy is activated
        dependency_packages=["polytrader", "numpy", "pydantic"],
    )

    # Generate deployment_id for correlation
    deployment_id = uuid.uuid4()

    # Create strategy record with all metadata
    strategy = StrategyRecordModel(
        strategy_id=request.strategy_id,
        name=request.name,
        description=request.description,
        config=request.config,
        template_type_id=request.template_type_id,
        template_version=template_version,
        config_hash=config_hash,
        desired_state=request.desired_state,
        actual_state=request.desired_state,
        template_code_ref=run_identity.template_code_ref,
        dependency_set=run_identity.dependency_set,
        market_data_snapshot_ref=run_identity.market_data_snapshot_ref,
        deployment_id=deployment_id,
        run_id=None,  # Will be set when strategy is activated
    )

    try:
        await registry.create_strategy(strategy)
        # Re-fetch to ensure timestamps are loaded
        from sqlalchemy import select

        # Re-fetch to ensure timestamps are loaded
        query = select(StrategyRecordModel).where(
            StrategyRecordModel.strategy_id == strategy.strategy_id
        )
        result = await registry.session.execute(query)
        strategy = result.scalar_one()
    except Exception as e:
        # Check if it's a duplicate key error
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorResponse(
                    error="Strategy already exists",
                    detail=f"Strategy with strategy_id '{request.strategy_id}' already exists",
                ).model_dump(),
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(error="Failed to create strategy", detail=str(e)).model_dump(),
        ) from e

    # If created with desired_state=RUNNING and platform is running, add to orchestrator
    # so the strategy starts immediately and can produce signals
    if (
        orchestrator is not None
        and request.desired_state == "RUNNING"
        and strategy.desired_state == "RUNNING"
    ):
        try:
            await orchestrator.add_strategy(strategy.strategy_id)
        except Exception as e:
            from polytrader.logging_config import logger

            logger.warning(
                "Strategy created but could not add to orchestrator: {error}",
                strategy_id=strategy.strategy_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Still return 201; strategy is in DB and can be activated via command
    elif (
        orchestrator is None
        and request.desired_state == "RUNNING"
        and strategy.desired_state == "RUNNING"
    ):
        from polytrader.logging_config import logger

        logger.info(
            "Strategy created with RUNNING but no live orchestrator: {strategy_id} "
            "will not produce signals until platform is started and strategy is activated.",
            strategy_id=strategy.strategy_id,
        )

    active_ids = await live_repo.list_active()
    return _strategy_record_to_response(
        strategy, is_live_activated=(strategy.strategy_id in active_ids)
    )


@router.patch(
    "/commands/strategies/{strategy_id}",
    response_model=StrategyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse, "description": "Strategy not found"},
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def update_strategy(
    strategy_id: str,
    request: UpdateStrategyRequest,
    registry: StrategyRegistry = Depends(get_strategy_registry),  # noqa: B008
    live_repo: LiveStrategyRepository = Depends(get_live_strategy_repo),  # noqa: B008
    orchestrator: "PlatformOrchestrator | None" = Depends(get_orchestrator),  # noqa: B008
) -> StrategyResponse:
    """Update an existing strategy in registry.

    When desired_state is set to RUNNING, the strategy is added to the running
    orchestrator so it starts (paper tracking). When set to STOPPED, it is
    removed from the orchestrator so it stops.
    """
    # Get existing strategy
    strategy = await registry.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                error="Strategy not found",
                detail=f"No strategy found with strategy_id: {strategy_id}",
            ).model_dump(),
        )

    # Update fields (only if provided)
    if request.name is not None:
        strategy.name = request.name
    if request.description is not None:
        strategy.description = request.description
    if request.config is not None:
        strategy.config = request.config
    if request.desired_state is not None:
        strategy.desired_state = request.desired_state

    try:
        await registry.update_strategy(strategy)
        # Re-fetch to ensure timestamps are loaded
        from sqlalchemy import select

        query = select(StrategyRecordModel).where(
            StrategyRecordModel.strategy_id == strategy.strategy_id
        )
        result = await registry.session.execute(query)
        updated_strategy = result.scalar_one()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(error="Failed to update strategy", detail=str(e)).model_dump(),
        ) from e

    # Apply lifecycle to running orchestrator so actual_state transitions
    if request.desired_state is not None and orchestrator is not None and orchestrator.is_running():
        from polytrader.logging_config import logger

        if request.desired_state == "RUNNING":
            try:
                await orchestrator.add_strategy(strategy_id)
            except Exception as e:
                logger.warning(
                    "Strategy set RUNNING but could not add to orchestrator: {error}",
                    strategy_id=strategy_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
        elif request.desired_state == "STOPPED":
            try:
                await orchestrator.remove_strategy(strategy_id)
            except Exception as e:
                logger.warning(
                    "Strategy set STOPPED but could not remove from orchestrator: {error}",
                    strategy_id=strategy_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    active_ids = await live_repo.list_active()
    return _strategy_record_to_response(
        updated_strategy, is_live_activated=(strategy_id in active_ids)
    )
