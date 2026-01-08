"""Command-line interface for the Polymarket trading system."""

import asyncio
from pathlib import Path

import typer

from polytrader.logging_config import logger, setup_logging
from polytrader.tasks import auto_buy_task, buy_task, predict_task, watch_task

app = typer.Typer(help="Polymarket trading system")

# Create sub-apps for command groups
market_app = typer.Typer(help="Market operations")
order_app = typer.Typer(help="Order operations")
model_app = typer.Typer(help="Trading model operations")

app.add_typer(market_app, name="market")
app.add_typer(order_app, name="order")
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


@order_app.command("buy")
def order_buy(
    market: str = typer.Option(..., "--market", "-m", help="Market slug"),
    outcome: str = typer.Option(..., "--outcome", "-o", help="Outcome name (e.g., 'Up', 'Down')"),
    amount: float = typer.Option(..., "--amount", "-a", help="Order amount in USDC"),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Place a buy order."""
    _setup_logging(log_file)

    response = buy_task(market, outcome, amount)
    if isinstance(response, dict):
        order_id = response.get("order_id") or response.get("id", "N/A")
        status = response.get("status") or response.get("state", "N/A")
    else:
        order_id = "N/A"
        status = "N/A"
    logger.info(
        "✅ Order placed: {market}/{outcome} ${amount:.2f}  ID:{order_id}  Status:{status}",
        market=market,
        outcome=outcome,
        amount=amount,
        order_id=order_id,
        status=status,
    )


@model_app.command("predict")
def model_predict(
    market: str = typer.Option(
        ..., "--market", "-m", help="Market pattern (e.g., 'btc-updown-15m') or market slug"
    ),
    frequency: float = typer.Option(1.0, "--frequency", "-f", help="Polling frequency in Hz"),
    buy_threshold: float = typer.Option(0.30, "--buy-threshold", help="Buy threshold price"),
    sell_threshold: float = typer.Option(0.50, "--sell-threshold", help="Sell threshold price"),
    size: float = typer.Option(1.0, "--size", "-s", help="Trade size in USD"),
    min_history: int = typer.Option(30, "--min-history", help="Minimum history ticks required"),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Run trading model predictions (no order execution)."""
    _setup_logging(log_file)

    logger.info("Predicting trades for market pattern: {market}", market=market)
    logger.info("Outcomes: UP, DOWN (both)")
    logger.info("Frequency: {frequency} Hz", frequency=frequency)
    logger.info("Buy threshold: {threshold}", threshold=buy_threshold)
    logger.info("Sell threshold: {threshold}", threshold=sell_threshold)
    logger.info("Size: ${size}", size=size)
    logger.info("Min history: {min_history} ticks", min_history=min_history)
    logger.info("Press Ctrl+C to stop")
    asyncio.run(
        predict_task(
            market,
            frequency,
            buy_threshold,
            sell_threshold,
            size,
            min_history,
        )
    )


@model_app.command("run")
def model_run(
    market: str = typer.Option(
        ..., "--market", "-m", help="Market pattern (e.g., 'btc-updown-15m') or market slug"
    ),
    frequency: float = typer.Option(1.0, "--frequency", "-f", help="Polling frequency in Hz"),
    buy_threshold: float = typer.Option(0.30, "--buy-threshold", help="Buy threshold price"),
    sell_threshold: float = typer.Option(0.50, "--sell-threshold", help="Sell threshold price"),
    size: float = typer.Option(1.0, "--size", "-s", help="Trade size in USD"),
    min_history: int = typer.Option(30, "--min-history", help="Minimum history ticks required"),
    max_trades: int = typer.Option(1, "--max-trades", help="Maximum trades per market"),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional file path to save logs"),
) -> None:
    """Run trading model with automatic order execution."""
    _setup_logging(log_file)

    logger.info("Running model for market pattern: {market}", market=market)
    logger.info("Outcomes: UP, DOWN (both)")
    logger.info("Frequency: {frequency} Hz", frequency=frequency)
    logger.info("Buy threshold: {threshold}", threshold=buy_threshold)
    logger.info("Sell threshold: {threshold}", threshold=sell_threshold)
    logger.info("Size: ${size}", size=size)
    logger.info("Min history: {min_history} ticks", min_history=min_history)
    logger.info("Max trades per outcome: {max_trades}", max_trades=max_trades)
    logger.info("Press Ctrl+C to stop")
    asyncio.run(
        auto_buy_task(
            market,
            frequency,
            buy_threshold,
            sell_threshold,
            size,
            min_history,
            max_trades,
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
