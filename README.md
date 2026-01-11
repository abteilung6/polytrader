# Polytrader

A trading system for Polymarket that automatically executes trades based on configurable trading models.

## Getting Started

### Paper Trading (Recommended for Testing)

Run paper trading with simulated execution and performance metrics:

```bash
python -m cli model paper \
  --market btc-updown-15m \
  --buy-threshold 0.30 \
  --sell-threshold 0.50 \
  --size 1.0 \
  --max-trades 1 \
  --starting-equity 1000.0 \
  --fill-model mid_price \
  --metrics-interval 60.0 \
  --log-file paper.log
```

This command will:
- Monitor the `btc-updown-15m` market pattern (automatically finds the current active market)
- Buy when price drops below 0.30 (30 cents)
- Sell when price reaches 0.50 (50 cents) or target price
- Trade with $1.0 per position
- Limit to 1 trade per market/outcome
- Use simulated execution (no real orders placed)
- Display performance metrics every 60 seconds
- Automatically handle market transitions (markets change every 15 minutes)
- Close positions when markets expire

Press `Ctrl+C` to stop the trading system.

### Live Trading

For real order execution, use the `live` command:

```bash
python -m cli model live \
  --market btc-updown-15m \
  --buy-threshold 0.30 \
  --sell-threshold 0.50 \
  --size 1.0 \
  --max-trades 1 \
  --sync-interval 60.0
```

**⚠️ Warning:** Live trading executes real orders with real money. Always test with paper trading first.

### Configuration

#### Paper Trading

Paper trading does not require API credentials. It uses simulated execution and tracks performance metrics.

#### Live Trading

For live trading, set the following environment variables:

- `POLYMARKET_PRIVATE_KEY`: Your Polymarket private key
- `POLYMARKET_FUNDER`: Your funder address
- `POLYMARKET_SIGNATURE_TYPE`: Signature type (e.g., "EIP712")

### Available Commands

- `model paper`: Run paper trading with simulated execution and performance metrics
- `model live`: Run live trading with real order execution (requires API credentials)
- `market watch`: Watch market prices/ticks without trading
