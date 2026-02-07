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
    config: str | None = typer.Option(
        None, "--config", help="Path to platform config YAML file (optional)"
    ),
    api_host: str | None = typer.Option(
        None, "--api-host", help="API server host (overrides config file)"
    ),
    api_port: int | None = typer.Option(
        None, "--api-port", help="API server port (overrides config file)"
    ),
    frequency: float | None = typer.Option(
        None, "--frequency", "-f", help="Polling frequency in Hz (overrides config file)"
    ),
    starting_equity: float | None = typer.Option(
        None, "--starting-equity", help="Starting equity for paper trading (overrides config file)"
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Start the platform with orchestrator, control plane, and API server.

    Starts the multi-strategy platform that:
    - Loads all strategies from database
    - Runs all strategies in paper mode
    - Starts control plane service (processes control commands)
    - Starts FastAPI control API server

    If --config is provided, loads platform configuration from a YAML file.
    CLI flags (--api-host, --api-port, etc.) override config file values.
    If no --config is provided, safe hardcoded defaults are used.

    Press Ctrl+C to stop.
    """
    _setup_logging(log_file)

    config_path = Path(config) if config else None

    logger.info("🚀 PLATFORM MODE")
    logger.info("Starting platform orchestrator")
    if config_path:
        logger.info("Config file: {config}", config=config_path)
    logger.info("Press Ctrl+C to stop")

    asyncio.run(
        platform_start_task(
            config_path=config_path,
            api_host_override=api_host,
            api_port_override=api_port,
            frequency_override=frequency,
            starting_equity_override=starting_equity,
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
