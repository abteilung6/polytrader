"""Centralized logging configuration using loguru."""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    json_output: bool = False,
) -> None:
    """Configure loguru logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logging
        json_output: If True, output JSON format (for production)
    """
    # Remove default handler
    logger.remove()

    # Console handler
    if json_output:
        # JSON format for production/log aggregation
        logger.add(
            sys.stderr,
            level=level,
            format="{time} | {level} | {name}:{function}:{line} | {message}",
            serialize=True,  # JSON output
        )
    else:
        # Rich colored output for development
        logger.add(
            sys.stderr,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    # File handler (if specified)
    if log_file:
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_file),  # Convert Path to string for loguru
            level=level,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
            ),
            rotation="10 MB",  # Rotate at 10MB
            retention="7 days",  # Keep logs for 7 days
            compression="zip",  # Compress old logs
        )

    # Suppress noisy third-party loggers
    logger.add(
        lambda msg: None,
        filter=lambda record: record["name"] is not None and record["name"].startswith("httpx"),
        level="WARNING",
    )
    logger.add(
        lambda msg: None,
        filter=lambda record: record["name"] is not None and record["name"].startswith("urllib3"),
        level="WARNING",
    )


# Export logger for easy import
__all__ = ["logger", "setup_logging"]
