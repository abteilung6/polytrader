"""Minimal HTTP API for runtime control commands.

Provides a simple JSON API to:
- register/list strategies
- view platform state
- enqueue control commands (enable/disable/select strategy)

This is intentionally minimal and uses stdlib http.server.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from polytrader.db.repository import (
    ControlCommandRepository,
    PlatformStateRepository,
    StrategyRepository,
)
from polytrader.db.session import DatabaseSessionManager
from polytrader.logging_config import logger, setup_logging

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
CONTROL_TOKEN_ENV = "POLYTRADER_CONTROL_TOKEN"


class ControlApiService:
    """Async DB service for control API operations."""

    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self._session_manager = session_manager
        self._session_factory = session_manager.session_factory()

    async def list_strategies(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            repo = StrategyRepository(session)
            rows = await repo.list_strategies()
            return [
                {
                    "strategy_id": row.strategy_id,
                    "name": row.name,
                    "description": row.description,
                    "config": row.config,
                    "enabled": row.enabled,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in rows
            ]

    async def upsert_strategy(self, payload: dict[str, Any]) -> None:
        strategy_id = payload.get("strategy_id")
        name = payload.get("name")
        if not strategy_id or not name:
            raise ValueError("strategy_id and name are required")
        description = payload.get("description")
        config = payload.get("config") or {}
        enabled = bool(payload.get("enabled", True))
        async with self._session_factory() as session:
            repo = StrategyRepository(session)
            await repo.upsert_strategy(
                strategy_id=strategy_id,
                name=name,
                description=description,
                config=config,
                enabled=enabled,
            )

    async def get_platform_state(self) -> dict[str, Any]:
        async with self._session_factory() as session:
            repo = PlatformStateRepository(session)
            state = await repo.get_state()
            return {
                "active_strategy_id": state.active_strategy_id,
                "execution_enabled": state.execution_enabled,
                "updated_at": state.updated_at.isoformat(),
                "updated_by": state.updated_by,
                "reason": state.reason,
            }

    async def enqueue_command(
        self,
        command_type: str,
        strategy_id: str | None,
        reason: str | None,
        issued_by: str,
    ) -> str:
        async with self._session_factory() as session:
            repo = ControlCommandRepository(session)
            command_id = uuid.uuid4()
            await repo.create_command(
                command_id=command_id,
                command_type=command_type,
                strategy_id=strategy_id,
                reason=reason,
                issued_by=issued_by,
            )
            return str(command_id)


def run_control_api_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    setup_logging_level: str = "INFO",
) -> None:
    """Run the control API server (blocking)."""
    setup_logging(level=setup_logging_level)
    session_manager = DatabaseSessionManager()
    service = ControlApiService(session_manager)

    handler_cls = _make_handler(service)
    server = ThreadingHTTPServer((host, port), handler_cls)
    logger.info("Control API server starting", host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            asyncio.run(session_manager.dispose())
        except Exception:
            logger.exception("Error disposing DB session manager")


def _make_handler(service: ControlApiService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _check_auth(self) -> bool:
            token = os.environ.get(CONTROL_TOKEN_ENV)
            if not token:
                return True
            return self.headers.get("X-Control-Token") == token

        def do_GET(self) -> None:
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if self.path == "/strategies":
                result = asyncio.run(service.list_strategies())
                self._send_json(200, {"strategies": result})
                return
            if self.path == "/platform/state":
                state = asyncio.run(service.get_platform_state())
                self._send_json(200, state)
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            try:
                payload = self._read_json()
            except Exception:
                self._send_json(400, {"error": "invalid json"})
                return

            if self.path == "/strategies":
                try:
                    asyncio.run(service.upsert_strategy(payload))
                except Exception as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                self._send_json(200, {"status": "ok"})
                return

            if self.path == "/control/enable":
                command_id = asyncio.run(
                    service.enqueue_command(
                        command_type="enable_execution",
                        strategy_id=None,
                        reason=payload.get("reason"),
                        issued_by=payload.get("issued_by", "operator"),
                    )
                )
                self._send_json(200, {"status": "queued", "command_id": command_id})
                return

            if self.path == "/control/disable":
                command_id = asyncio.run(
                    service.enqueue_command(
                        command_type="disable_execution",
                        strategy_id=None,
                        reason=payload.get("reason"),
                        issued_by=payload.get("issued_by", "operator"),
                    )
                )
                self._send_json(200, {"status": "queued", "command_id": command_id})
                return

            if self.path == "/control/select":
                strategy_id = payload.get("strategy_id")
                if not strategy_id:
                    self._send_json(400, {"error": "strategy_id required"})
                    return
                command_id = asyncio.run(
                    service.enqueue_command(
                        command_type="select_live_strategy",
                        strategy_id=strategy_id,
                        reason=payload.get("reason"),
                        issued_by=payload.get("issued_by", "operator"),
                    )
                )
                self._send_json(200, {"status": "queued", "command_id": command_id})
                return

            self._send_json(404, {"error": "not found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            # Route HTTP logs through structured logger
            logger.info("control_api", message=fmt % args)

    return Handler


def main() -> None:
    run_control_api_server()


if __name__ == "__main__":
    main()
