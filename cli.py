"""Command-line interface for the Polymarket trading system."""

import asyncio
from pathlib import Path

import typer

from polytrader.logging_config import logger, setup_logging
from polytrader.tasks import platform_start_task

app = typer.Typer(help="Polymarket trading system")

# Create sub-apps for command groups
platform_app = typer.Typer(help="Platform operations")

app.add_typer(platform_app, name="platform")


@platform_app.command("start")
def platform_start(
    api_host: str = typer.Option(
        "0.0.0.0", "--api-host", help="API server host (default: 0.0.0.0)"
    ),
    api_port: int = typer.Option(8000, "--api-port", help="API server port (default: 8000)"),
    frequency: float = typer.Option(1.0, "--frequency", "-f", help="Polling frequency in Hz"),
    starting_equity: float = typer.Option(
        1000.0, "--starting-equity", help="Starting equity for paper trading"
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Start the platform with orchestrator, control plane, and API server.

    Starts the multi-strategy platform that:
    - Loads all strategies from database
    - Runs all strategies in paper mode
    - Starts control plane service (processes control commands)
    - Starts FastAPI control API server

    Press Ctrl+C to stop.
    """
    _setup_logging(log_file)

    logger.info("🚀 PLATFORM MODE")
    logger.info("Starting platform orchestrator")
    logger.info("API server: http://{host}:{port}/docs", host=api_host, port=api_port)
    logger.info("Frequency: {frequency} Hz", frequency=frequency)
    logger.info("Starting equity: ${equity:.2f}", equity=starting_equity)
    logger.info("Press Ctrl+C to stop")

    asyncio.run(
        platform_start_task(
            api_host=api_host,
            api_port=api_port,
            frequency=frequency,
            starting_equity=starting_equity,
        )
    )


def _setup_logging(log_file: str | None) -> None:
    """Setup logging with optional file output."""
    log_path = None
    if log_file:
        log_path = Path(log_file)
    setup_logging(level="INFO", log_file=log_path)

    if log_path:
        logger.info("Logging to file: {file}", file=log_path)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
