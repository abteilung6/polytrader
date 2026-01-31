"""Control API routes (state and command endpoints).

Per Platform_Proposal.md: Elite-style API design with separation of
state endpoints (/state/*) and command endpoints (/commands/*).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from polytrader.api.dependencies import (
    get_control_command_repo,
    get_event_repository,
    get_execution_control_repo,
    get_in_memory_strategy_registry,
    get_live_strategy_repo,
    get_strategy_registry,
)
from polytrader.api.models import (
    ActivateStrategyRequest,
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
    LiveStrategiesResponse,
    RunIdentityResponse,
    StrategiesResponse,
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
from polytrader.db.repository import EventRepository
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
) -> ExecutionStateResponse:
    """Get execution control state (with version for optimistic concurrency)."""
    control = await execution_repo.get_control()
    return ExecutionStateResponse(
        execution_enabled=control.execution_enabled,
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


def _strategy_record_to_response(s: StrategyRecordModel) -> StrategyResponse:
    """Map DB StrategyRecord to API StrategyResponse (single source of truth)."""
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
    )


@router.get("/state/strategies", response_model=StrategiesResponse)
async def get_strategies(
    registry: StrategyRegistry = Depends(get_strategy_registry),  # noqa: B008
) -> StrategiesResponse:
    """Get all strategies in registry."""
    strategies = await registry.list_strategies()
    return StrategiesResponse(strategies=[_strategy_record_to_response(s) for s in strategies])


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
) -> StrategyResponse:
    """Get a single strategy by ID.

    Returns 404 if the strategy is not in the registry.
    """
    strategy = await registry.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    return _strategy_record_to_response(strategy)


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

    return StrategyResponse(
        strategy_id=strategy.strategy_id,
        name=strategy.name,
        description=strategy.description,
        config=strategy.config,
        template_type_id=strategy.template_type_id,
        template_version=strategy.template_version,
        desired_state=strategy.desired_state,
        actual_state=strategy.actual_state,
        last_transition_at=strategy.last_transition_at,
        last_error=strategy.last_error,
        run_identity=(
            RunIdentityResponse(
                template_code_ref=strategy.template_code_ref,
                config_hash=strategy.config_hash,
                dependency_set=strategy.dependency_set,
                market_data_snapshot_ref=strategy.market_data_snapshot_ref,
            )
            if (
                strategy.template_code_ref
                or strategy.dependency_set
                or strategy.market_data_snapshot_ref
            )
            else None
        ),
        deployment_id=str(strategy.deployment_id) if strategy.deployment_id else None,
        run_id=strategy.run_id,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
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
) -> StrategyResponse:
    """Update an existing strategy in registry."""
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
        # Update desired_state (lifecycle manager will handle actual_state transition)
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

    return StrategyResponse(
        strategy_id=updated_strategy.strategy_id,
        name=updated_strategy.name,
        description=updated_strategy.description,
        config=updated_strategy.config,
        template_type_id=updated_strategy.template_type_id,
        template_version=updated_strategy.template_version,
        desired_state=updated_strategy.desired_state,
        actual_state=updated_strategy.actual_state,
        last_transition_at=updated_strategy.last_transition_at,
        last_error=updated_strategy.last_error,
        run_identity=(
            RunIdentityResponse(
                template_code_ref=updated_strategy.template_code_ref,
                config_hash=updated_strategy.config_hash,
                dependency_set=updated_strategy.dependency_set,
                market_data_snapshot_ref=updated_strategy.market_data_snapshot_ref,
            )
            if updated_strategy.template_code_ref
            or updated_strategy.dependency_set
            or updated_strategy.market_data_snapshot_ref
            else None
        ),
        deployment_id=(
            str(updated_strategy.deployment_id) if updated_strategy.deployment_id else None
        ),
        run_id=updated_strategy.run_id,
        created_at=updated_strategy.created_at,
        updated_at=updated_strategy.updated_at,
    )
