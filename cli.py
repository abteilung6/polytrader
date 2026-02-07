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
        None,
        "--config",
        help="Path to platform config YAML file (uses safe defaults if omitted)",
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Start the platform with orchestrator, control plane, and API server.

    All platform settings (API host/port, risk limits, execution params, etc.)
    are controlled via the YAML config file. If --config is omitted, safe
    hardcoded defaults from PlatformConfig are used.

    Example:
        python -m cli platform start --config config/platform.paper.yaml

    Press Ctrl+C to stop.
    """
    _setup_logging(log_file)

    config_path = Path(config) if config else None

    logger.info("🚀 PLATFORM MODE")
    logger.info("Starting platform orchestrator")
    if config_path:
        logger.info("Config file: {config}", config=config_path)
    else:
        logger.info("No config file — using safe defaults")
    logger.info("Press Ctrl+C to stop")

    asyncio.run(platform_start_task(config_path=config_path))


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
