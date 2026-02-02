"""Control plane service: processes control commands from database queue.

Per Platform_Proposal.md §2.5: Control plane service polls control_commands table
for pending commands and applies them to execution_control and live_strategy_activation.

Responsibilities:
- Poll control_commands for pending commands
- Apply commands to DB (execution_control, live_strategy_activation)
- Handle version checks (optimistic concurrency)
- Increment version on state changes
- Update in-memory ExecutionControl state
- Emit ControlCommandEvent for audit trail
- Handle validation and errors
"""

import asyncio
from typing import TYPE_CHECKING, Literal

from polytrader.events import SYSTEM_LIFECYCLE
from polytrader.events.bus import EventBus
from polytrader.events.types import ControlCommandEvent
from polytrader.logging_config import logger
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.registry import StrategyRegistry
from polytrader.strategies.lifecycle_models import StrategyLifecycleState

if TYPE_CHECKING:
    from polytrader.db.models import ControlCommandRecord


class ControlPlaneService:
    """Control plane service that processes control commands.

    Polls control_commands table for pending commands and applies them to
    execution_control and live_strategy_activation tables. Handles optimistic
    concurrency control via version checks and emits ControlCommandEvent for
    audit trail.

    Per Platform_Proposal.md §2.5: This service runs as a background task
    and processes commands asynchronously.

    Example:
        >>> async with Session() as session:
        ...     command_repo = ControlCommandRepository(session)
        ...     execution_repo = ExecutionControlRepository(session)
        ...     live_repo = LiveStrategyRepository(session)
        ...     strategy_registry = StrategyRegistry(session)
        ...     service = ControlPlaneService(
        ...         command_repo=command_repo,
        ...         execution_repo=execution_repo,
        ...         live_repo=live_repo,
        ...         strategy_registry=strategy_registry,
        ...         execution_control=execution_control,
        ...         bus=event_bus,
        ...     )
        ...     await service.start()
        ...     # Service runs in background, processing commands
        ...     await service.stop()
    """

    def __init__(
        self,
        command_repo: ControlCommandRepository,
        execution_repo: ExecutionControlRepository,
        live_repo: LiveStrategyRepository,
        strategy_registry: StrategyRegistry,
        execution_control: ExecutionControl,
        bus: EventBus,
        poll_interval_s: float = 1.0,
    ) -> None:
        """Initialize control plane service.

        Args:
            command_repo: Repository for control commands
            execution_repo: Repository for execution control
            live_repo: Repository for live strategy activation
            strategy_registry: Registry to sync strategy_instances.desired_state
            execution_control: In-memory execution control state
            bus: Event bus for emitting ControlCommandEvent
            poll_interval_s: Polling interval in seconds (default: 1.0)
        """
        self._command_repo = command_repo
        self._execution_repo = execution_repo
        self._live_repo = live_repo
        self._strategy_registry = strategy_registry
        self._execution_control = execution_control
        self._bus = bus
        self._poll_interval_s = poll_interval_s

        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the control plane service (begin polling for commands)."""
        if self._running:
            logger.warning("ControlPlaneService is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("ControlPlaneService started")

    async def stop(self) -> None:
        """Stop the control plane service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ControlPlaneService stopped")

    async def _run(self) -> None:
        """Main loop: poll for pending commands and process them."""
        try:
            while self._running:
                pending = await self._command_repo.list_pending()
                for cmd in pending:
                    await self._process_command(cmd)
                await asyncio.sleep(self._poll_interval_s)
        except asyncio.CancelledError:
            logger.info("ControlPlaneService run cancelled")
            raise
        except Exception as e:
            logger.exception(
                "ControlPlaneService error: {error}",
                error=str(e),
            )
            raise

    async def _process_command(self, cmd: "ControlCommandRecord") -> None:
        """Process a single control command.

        Handles version checks (optimistic concurrency), applies command to DB,
        updates in-memory state, and emits ControlCommandEvent.

        Args:
            cmd: Control command record to process
        """
        try:
            # Check version if provided (optimistic concurrency)
            if cmd.expected_version is not None:
                current = await self._execution_repo.get_control()
                if current.version != cmd.expected_version:
                    error_msg = (
                        f"Version mismatch: expected {cmd.expected_version}, got {current.version}"
                    )
                    await self._command_repo.mark_failed(str(cmd.command_id), error_msg)
                    await self._emit_command_event(cmd, "failed", error_msg, current.version)
                    return

            # Process command based on type
            if cmd.command_type == "enable_execution":
                await self._enable_execution(cmd)
            elif cmd.command_type == "disable_execution":
                await self._disable_execution(cmd)
            elif cmd.command_type == "add_active_strategy":
                await self._add_active_strategy(cmd)
            elif cmd.command_type == "remove_active_strategy":
                await self._remove_active_strategy(cmd)
            else:
                error_msg = f"Unknown command type: {cmd.command_type}"
                await self._command_repo.mark_failed(str(cmd.command_id), error_msg)
                await self._emit_command_event(cmd, "failed", error_msg, None)
                return

            # Mark command as applied
            await self._command_repo.mark_applied(str(cmd.command_id))
            await self._emit_command_event(cmd, "applied", None, None)

        except Exception as e:
            error_msg = str(e)
            logger.exception(
                "Error processing command {command_id}: {error}",
                command_id=cmd.command_id,
                error=error_msg,
            )
            await self._command_repo.mark_failed(str(cmd.command_id), error_msg)
            await self._emit_command_event(cmd, "failed", error_msg, None)

    async def _enable_execution(self, cmd: "ControlCommandRecord") -> None:
        """Enable execution (apply enable_execution command).

        Updates execution_control table and in-memory ExecutionControl state.
        Version is incremented automatically by ExecutionControlRepository.

        Args:
            cmd: Control command record
        """
        updated = await self._execution_repo.update_control(
            execution_enabled=True,
            updated_by=cmd.issued_by,
            reason=cmd.reason,
        )

        # Update in-memory state
        self._execution_control.enable()

        logger.info(
            "Execution enabled via command {command_id}: {reason} (version: {version})",
            command_id=cmd.command_id,
            reason=cmd.reason,
            version=updated.version,
        )

    async def _disable_execution(self, cmd: "ControlCommandRecord") -> None:
        """Disable execution (apply disable_execution command).

        Updates execution_control table and in-memory ExecutionControl state.
        Version is incremented automatically by ExecutionControlRepository.

        Args:
            cmd: Control command record
        """
        updated = await self._execution_repo.update_control(
            execution_enabled=False,
            updated_by=cmd.issued_by,
            reason=cmd.reason,
        )

        # Update in-memory state
        self._execution_control.disable()

        logger.info(
            "Execution disabled via command {command_id}: {reason} (version: {version})",
            command_id=cmd.command_id,
            reason=cmd.reason,
            version=updated.version,
        )

    async def _add_active_strategy(self, cmd: "ControlCommandRecord") -> None:
        """Add strategy to active set (apply add_active_strategy command).

        Updates live_strategy_activation to active=true and strategy_instances
        desired_state/actual_state to RUNNING so the orchestrator starts the
        strategy on next load (or on platform restart).
        """
        if cmd.strategy_id is None:
            raise ValueError("add_active_strategy command requires strategy_id")

        await self._live_repo.activate(
            strategy_id=cmd.strategy_id,
            activated_by=cmd.issued_by,
            reason=cmd.reason,
        )

        strategy = await self._strategy_registry.get_strategy(cmd.strategy_id)
        if strategy is not None:
            strategy.desired_state = StrategyLifecycleState.RUNNING.value
            strategy.actual_state = StrategyLifecycleState.RUNNING.value
            await self._strategy_registry.update_strategy(strategy)

        logger.info(
            "Strategy {strategy_id} activated via command {command_id}: {reason}",
            strategy_id=cmd.strategy_id,
            command_id=cmd.command_id,
            reason=cmd.reason,
        )

    async def _remove_active_strategy(self, cmd: "ControlCommandRecord") -> None:
        """Remove strategy from active set (apply remove_active_strategy command).

        Updates live_strategy_activation to active=false and strategy_instances
        desired_state/actual_state to STOPPED so the orchestrator does not
        start the strategy on next load.
        """
        if cmd.strategy_id is None:
            raise ValueError("remove_active_strategy command requires strategy_id")

        await self._live_repo.deactivate(
            strategy_id=cmd.strategy_id,
            activated_by=cmd.issued_by,
            reason=cmd.reason,
        )

        strategy = await self._strategy_registry.get_strategy(cmd.strategy_id)
        if strategy is not None:
            strategy.desired_state = StrategyLifecycleState.STOPPED.value
            strategy.actual_state = StrategyLifecycleState.STOPPED.value
            await self._strategy_registry.update_strategy(strategy)

        logger.info(
            "Strategy {strategy_id} deactivated via command {command_id}: {reason}",
            strategy_id=cmd.strategy_id,
            command_id=cmd.command_id,
            reason=cmd.reason,
        )

    async def _emit_command_event(
        self,
        cmd: "ControlCommandRecord",
        status: Literal["applied", "failed"],
        error_message: str | None,
        actual_version: int | None,
    ) -> None:
        """Emit ControlCommandEvent for audit trail.

        Args:
            cmd: Control command record
            status: Command status (applied or failed)
            error_message: Error message if failed (None if applied)
            actual_version: Actual version after application (None if failed before version check)
        """
        # Get actual version if not provided (for applied commands)
        if actual_version is None and status == "applied":
            current = await self._execution_repo.get_control()
            actual_version = current.version

        event = ControlCommandEvent(
            command_id=str(cmd.command_id),
            command_type=cmd.command_type,
            strategy_id=cmd.strategy_id,
            reason=cmd.reason,
            issued_by=cmd.issued_by,
            client_request_id=cmd.client_request_id,
            status=status,
            error_message=error_message,
            expected_version=cmd.expected_version,
            actual_version=actual_version,
        )

        await self._bus.publish(SYSTEM_LIFECYCLE, event)
