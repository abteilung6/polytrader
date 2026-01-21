"""Runtime control plane for manual trading commands.

This module provides a file-based control channel that allows operators
to issue live trading commands while the system is running.
Commands are ingested, validated, emitted as ControlCommandEvent, and
applied via ExecutionControl with health gate checks.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Callable

from polytrader.events import SYSTEM_LIFECYCLE, EventBus
from polytrader.events.types import ControlCommandEvent
from polytrader.logging_config import logger
from polytrader.obs.logging import bind_correlation_context
from polytrader.ops.control import ExecutionControl
from polytrader.ops.health import HealthGateThresholds, HealthService, HealthStatus
from polytrader.store import IMarketDataStore

DEFAULT_CONTROL_COMMAND_PATH_ENV = "POLYTRADER_CONTROL_PATH"
DEFAULT_CONTROL_COMMAND_PATH = "var/control/commands.jsonl"


def get_default_control_command_path() -> Path:
    """Get default control command path (env override supported)."""
    env_value = os.environ.get(DEFAULT_CONTROL_COMMAND_PATH_ENV)
    if env_value:
        return Path(env_value)
    return Path(DEFAULT_CONTROL_COMMAND_PATH)


def append_control_command(path: Path, command: ControlCommandEvent) -> None:
    """Append a control command to the command file (JSONL).

    Args:
        path: Command file path
        command: ControlCommandEvent to append
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = command.model_dump(mode="json")
    line = json.dumps(payload, ensure_ascii=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class FileControlCommandReader:
    """Reads ControlCommandEvent records from a JSONL file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._offset = 0

    def read_new(self) -> list[ControlCommandEvent]:
        """Read new commands since the last offset."""
        if not self._path.exists():
            return []

        try:
            size = self._path.stat().st_size
        except FileNotFoundError:
            return []

        if size < self._offset:
            # File truncated or rotated
            self._offset = 0

        with self._path.open("r", encoding="utf-8") as f:
            f.seek(self._offset)
            lines = f.readlines()
            self._offset = f.tell()

        commands: list[ControlCommandEvent] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "Invalid control command JSON line",
                    line_preview=line[:200],
                )
                continue
            try:
                commands.append(ControlCommandEvent.model_validate(payload))
            except Exception as exc:
                logger.warning(
                    "Invalid control command payload",
                    error=str(exc),
                )
                continue
        return commands


class ControlPlaneService:
    """Control plane service that applies runtime commands.

    This service polls a command source (file-based in Phase 1),
    emits ControlCommandEvent for audit, and applies commands to
    ExecutionControl with health gate checks.
    """

    def __init__(
        self,
        bus: EventBus,
        command_reader: FileControlCommandReader,
        execution_control: ExecutionControl | None,
        store: IMarketDataStore,
        health_gate_thresholds: HealthGateThresholds | None = None,
        poll_interval_s: float = 1.0,
        get_user_stream_adapter: Callable[[], object | None] | None = None,
        get_circuit_breaker: Callable[[], object | None] | None = None,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be > 0")
        self._bus = bus
        self._command_reader = command_reader
        self._execution_control = execution_control
        self._store = store
        self._health_gate_thresholds = health_gate_thresholds or HealthGateThresholds()
        self._poll_interval_s = poll_interval_s
        self._get_user_stream_adapter = get_user_stream_adapter
        self._get_circuit_breaker = get_circuit_breaker
        self._running = False

    async def run(self) -> None:
        """Run control plane polling loop."""
        self._running = True
        logger.info("ControlPlaneService started")
        try:
            while self._running:
                commands = self._command_reader.read_new()
                for command in commands:
                    await self._handle_command(command)
                await asyncio.sleep(self._poll_interval_s)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("ControlPlaneService error")
            raise
        finally:
            self._running = False
            logger.info("ControlPlaneService stopped")

    def stop(self) -> None:
        """Stop the control plane loop."""
        self._running = False

    async def _handle_command(self, command: ControlCommandEvent) -> None:
        """Handle a single control command."""
        log_context = bind_correlation_context(
            logger,
            correlation_id=command.correlation_id,
            event_type="ControlCommand",
            command_type=command.command_type,
            strategy_id=command.strategy_id,
            issued_by=command.issued_by,
        )
        log_context.info("Processing control command")

        # Emit for audit trail
        await self._bus.publish(SYSTEM_LIFECYCLE, command)

        if self._execution_control is None:
            log_context.warning("ExecutionControl unavailable; command ignored")
            return

        if command.command_type == "enable_execution":
            await self._enable_execution(command, log_context)
        elif command.command_type == "disable_execution":
            self._execution_control.disable()
            log_context.warning("Execution disabled by operator command")
        elif command.command_type == "select_live_strategy":
            self._execution_control.set_active_strategy(command.strategy_id)
            log_context.info(
                "Active live strategy set",
                active_strategy_id=command.strategy_id,
            )
        else:
            log_context.warning("Unknown control command type")

    async def _enable_execution(self, command: ControlCommandEvent, log_context) -> None:
        """Enable execution after health gate checks."""
        all_passed, health_status, failed_gates = await self._evaluate_health()
        if not all_passed:
            log_context.error(
                "Execution enable denied: health gates failed",
                failed_gates=",".join(failed_gates),
            )
            return

        health_status_dict = self._health_status_to_dict(health_status)
        await self._execution_control.enable_with_permit(
            permit_type="manual",
            reason=command.reason or "Manual enable",
            health_status=health_status_dict,
            issued_by=command.issued_by,
        )
        log_context.info("Execution enabled by operator command")

    async def _evaluate_health(self) -> tuple[bool, HealthStatus, list[str]]:
        """Evaluate health gates using current system state."""
        user_stream_adapter = (
            self._get_user_stream_adapter() if self._get_user_stream_adapter else None
        )
        circuit_breaker = self._get_circuit_breaker() if self._get_circuit_breaker else None
        kill_switch_active = (
            self._execution_control.kill_switch_active if self._execution_control else False
        )

        health_service = HealthService(
            store=self._store,
            thresholds=self._health_gate_thresholds,
            user_stream_adapter=user_stream_adapter,
            circuit_breaker=circuit_breaker,
            execution_control=self._execution_control,
            kill_switch_active=kill_switch_active,
            error_rate=None,
            recent_reconcile_events=[],
        )
        health_status = await health_service.evaluate()
        all_passed, failed_gates = health_service.check_gates(health_status)
        return all_passed, health_status, failed_gates

    @staticmethod
    def _health_status_to_dict(health_status: HealthStatus) -> dict[str, object]:
        """Convert health status to dict for permit event."""
        return {
            "market_data_fresh": health_status.market_data_fresh,
            "market_data_staleness_seconds": health_status.market_data_staleness_seconds,
            "user_stream_connected": health_status.user_stream_connected,
            "reconciliation_healthy": health_status.reconciliation_healthy,
            "reconciliation_divergence_count": health_status.reconciliation_divergence_count,
            "error_rate_ok": health_status.error_rate_ok,
            "error_rate": health_status.error_rate,
            "circuit_breaker_triggered": health_status.circuit_breaker_triggered,
            "kill_switch_active": health_status.kill_switch_active,
        }
