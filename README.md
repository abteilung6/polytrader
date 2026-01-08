# Polytrader

A trading system for Polymarket that automatically executes trades based on configurable trading models.

## Getting Started

Run the trading model with automatic order execution:

```bash
python cli.py model run \
  --market btc-updown-15m \
  --buy-threshold 0.4 \
  --sell-threshold 0.6 \
  --size 1.0 \
  --max-trades 1
  --log-file live.log
```

This command will:
- Monitor the `btc-updown-15m` market pattern (automatically finds the current active market)
- Buy when price drops below 0.4 (40 cents)
- Sell when price reaches 0.6 (60 cents) or target price
- Trade with $1.0 per position
- Limit to 1 trade per market/outcome
- Automatically handle market transitions (markets change every 15 minutes)

Press `Ctrl+C` to stop the trading system.

### Configuration

Set the following environment variables:

- `POLYMARKET_PRIVATE_KEY`: Your Polymarket private key
- `POLYMARKET_FUNDER`: Your funder address
- `POLYMARKET_SIGNATURE_TYPE`: Signature type (e.g., "EIP712")
