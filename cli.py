"""Command-line interface for the Polymarket trading system."""

import asyncio
from pathlib import Path

import typer

from polytrader.logging_config import logger, setup_logging
from polytrader.tasks import (
    live_trading_task,
    paper_trading_task,
    watch_task,
)

app = typer.Typer(help="Polymarket trading system")

# Create sub-apps for command groups
market_app = typer.Typer(help="Market operations")
model_app = typer.Typer(help="Trading model operations")

app.add_typer(market_app, name="market")
app.add_typer(model_app, name="model")


@market_app.command("watch")
def market_watch(
    pattern: str = typer.Option(
        ..., "--pattern", "-p", help="Market pattern (e.g., 'btc-updown-15m') or market slug"
    ),
    frequency: float = typer.Option(1.0, "--frequency", "-f", help="Polling frequency in Hz"),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Number of ticks to show (default: unlimited)"
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Watch market prices/ticks."""
    _setup_logging(log_file)

    logger.info("Watching market pattern: {pattern}", pattern=pattern)
    logger.info("Outcomes: UP, DOWN (both)")
    logger.info("Frequency: {frequency} Hz", frequency=frequency)
    if limit:
        logger.info("Limit: {limit} ticks", limit=limit)
    logger.info("Press Ctrl+C to stop")
    asyncio.run(watch_task(pattern, frequency, limit))


@model_app.command("live")
def model_live(
    market: str = typer.Option(
        ..., "--market", "-m", help="Market pattern (e.g., 'btc-updown-15m') or market slug"
    ),
    frequency: float = typer.Option(1.0, "--frequency", "-f", help="Polling frequency in Hz"),
    buy_threshold: float = typer.Option(0.30, "--buy-threshold", help="Buy threshold price"),
    sell_threshold: float = typer.Option(0.50, "--sell-threshold", help="Sell threshold price"),
    size: float = typer.Option(1.0, "--size", "-s", help="Trade size in USD"),
    min_history: int = typer.Option(30, "--min-history", help="Minimum history ticks required"),
    max_trades: int = typer.Option(1, "--max-trades", help="Maximum trades per market"),
    sync_interval: float = typer.Option(
        60.0, "--sync-interval", help="Position sync interval in seconds"
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Run live trading with real order execution and position tracking."""
    _setup_logging(log_file)

    logger.info("🚀 LIVE TRADING MODE")
    logger.info("Running live trading for market pattern: {market}", market=market)
    logger.info("Outcomes: UP, DOWN (both)")
    logger.info("Frequency: {frequency} Hz", frequency=frequency)
    logger.info("Buy threshold: {threshold}", threshold=buy_threshold)
    logger.info("Sell threshold: {threshold}", threshold=sell_threshold)
    logger.info("Size: ${size}", size=size)
    logger.info("Min history: {min_history} ticks", min_history=min_history)
    logger.info("Max trades per outcome: {max_trades}", max_trades=max_trades)
    logger.info("Sync interval: {interval}s", interval=sync_interval)
    logger.info("Press Ctrl+C to stop")
    asyncio.run(
        live_trading_task(
            market,
            frequency,
            buy_threshold,
            sell_threshold,
            size,
            min_history,
            max_trades,
            sync_interval=sync_interval,
        )
    )


@model_app.command("paper")
def model_paper(
    market: str = typer.Option(
        ..., "--market", "-m", help="Market pattern (e.g., 'btc-updown-15m') or market slug"
    ),
    frequency: float = typer.Option(1.0, "--frequency", "-f", help="Polling frequency in Hz"),
    buy_threshold: float = typer.Option(0.30, "--buy-threshold", help="Buy threshold price"),
    sell_threshold: float = typer.Option(0.50, "--sell-threshold", help="Sell threshold price"),
    size: float = typer.Option(1.0, "--size", "-s", help="Trade size in USD"),
    min_history: int = typer.Option(30, "--min-history", help="Minimum history ticks required"),
    max_trades: int = typer.Option(1, "--max-trades", help="Maximum trades per market"),
    fill_probability: float = typer.Option(
        1.0, "--fill-probability", help="Fill probability (0-1)"
    ),
    rejection_probability: float = typer.Option(
        0.0, "--rejection-probability", help="Rejection probability (0-1)"
    ),
    latency_ms: float = typer.Option(
        50.0, "--latency-ms", help="Simulated latency in milliseconds"
    ),
    metrics_interval: float = typer.Option(
        60.0, "--metrics-interval", help="Performance metrics display interval in seconds"
    ),
    starting_equity: float = typer.Option(
        1000.0, "--starting-equity", help="Starting equity in USD"
    ),
    fill_model: str = typer.Option(
        "mid_price", "--fill-model", help="Fill model: immediate, mid_price, slippage"
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Run paper trading with simulated execution and performance metrics."""
    _setup_logging(log_file)

    # Parameter validation
    if not 0.0 <= fill_probability <= 1.0:
        raise ValueError(f"fill_probability must be between 0 and 1, got {fill_probability}")
    if not 0.0 <= rejection_probability <= 1.0:
        raise ValueError(
            f"rejection_probability must be between 0 and 1, got {rejection_probability}"
        )
    if fill_probability + rejection_probability > 1.0:
        raise ValueError(
            f"fill_probability + rejection_probability must be <= 1.0, "
            f"got {fill_probability + rejection_probability}"
        )
    if frequency <= 0.0:
        raise ValueError(f"frequency must be > 0, got {frequency}")
    if buy_threshold < 0.0 or buy_threshold > 1.0:
        raise ValueError(f"buy_threshold must be between 0 and 1, got {buy_threshold}")
    if sell_threshold < 0.0 or sell_threshold > 1.0:
        raise ValueError(f"sell_threshold must be between 0 and 1, got {sell_threshold}")
    if buy_threshold >= sell_threshold:
        raise ValueError(
            f"buy_threshold ({buy_threshold}) must be < sell_threshold ({sell_threshold})"
        )
    if size <= 0.0:
        raise ValueError(f"size must be > 0, got {size}")
    if min_history < 0:
        raise ValueError(f"min_history must be >= 0, got {min_history}")
    if max_trades < 1:
        raise ValueError(f"max_trades must be >= 1, got {max_trades}")
    if latency_ms < 0.0:
        raise ValueError(f"latency_ms must be >= 0, got {latency_ms}")
    if metrics_interval <= 0.0:
        raise ValueError(f"metrics_interval must be > 0, got {metrics_interval}")
    if starting_equity <= 0.0:
        raise ValueError(f"starting_equity must be > 0, got {starting_equity}")

    # Validate and convert fill_model
    from polytrader.execution.fill_models import FillModel

    fill_model_lower = fill_model.lower()
    try:
        fill_model_enum = FillModel(fill_model_lower)
    except ValueError as err:
        valid_models = ", ".join([m.value for m in FillModel])
        raise ValueError(
            f"Invalid fill_model '{fill_model}'. Must be one of: {valid_models}"
        ) from err

    logger.info("📝 PAPER TRADING MODE")
    logger.info("Running paper trading for market pattern: {market}", market=market)
    logger.info("Outcomes: UP, DOWN (both)")
    logger.info("Frequency: {frequency} Hz", frequency=frequency)
    logger.info("Buy threshold: {threshold}", threshold=buy_threshold)
    logger.info("Sell threshold: {threshold}", threshold=sell_threshold)
    logger.info("Size: ${size}", size=size)
    logger.info("Min history: {min_history} ticks", min_history=min_history)
    logger.info("Max trades per outcome: {max_trades}", max_trades=max_trades)
    logger.info("Fill probability: {prob:.1%}", prob=fill_probability)
    logger.info("Rejection probability: {prob:.1%}", prob=rejection_probability)
    logger.info("Simulated latency: {latency}ms", latency=latency_ms)
    logger.info("Metrics interval: {interval}s", interval=metrics_interval)
    logger.info("Starting equity: ${equity:.2f}", equity=starting_equity)
    logger.info("Fill model: {model}", model=fill_model_enum.value)
    logger.info("Press Ctrl+C to stop")
    asyncio.run(
        paper_trading_task(
            market,
            frequency,
            buy_threshold,
            sell_threshold,
            size,
            min_history,
            max_trades,
            fill_model=fill_model_enum,
            fill_probability=fill_probability,
            rejection_probability=rejection_probability,
            latency_ms=latency_ms,
            metrics_interval=metrics_interval,
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
