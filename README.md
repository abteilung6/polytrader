Printer: 

python cli.py watch --asset eth --time-period 15m --strategy gabagool  --trade --frequency 1
python cli.py watch --asset bitcoin --time-period 15m --strategy gabagool  --trade --frequency 1
python cli.py watch --asset sol --time-period 15m --strategy gabagool  --trade --frequency 1


# Polytrader

A Python trading system for Polymarket that enables real-time market monitoring and order placement on prediction markets.

## Features

- 🔍 **Real-time Price Monitoring**: Watch market prices with configurable polling frequency
- 📊 **Side-by-Side Price Display**: View both Up and Down outcomes simultaneously in a table format
- 🎯 **Auto Market Discovery**: Automatically find the latest market slug from asset and time period
- 💰 **Order Placement**: Place market buy orders on Polymarket
- 🏗️ **Event-Driven Architecture**: Extensible pub/sub system for building trading strategies
- 📈 **Tick Storage**: In-memory storage of historical price data

## Installation

### Prerequisites

- Python 3.12+
- A Polymarket account with a wallet (Magic wallet or EOA/MetaMask)

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd polytrader
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   For development:
   ```bash
   pip install -r requirements.dev.txt
   ```

3. **Configure environment variables**:
   
   Copy the example environment file:
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` and add your credentials:
   ```env
   PRIVATE_KEY=your_private_key_here
   FUNDER=your_magic_wallet_address_here  # Required for Magic wallets
   SIGNATURE_TYPE=1  # 0=EOA/MetaMask, 1=Magic wallet, 2=Browser wallet proxy
   ```

## Commands

### `watch` - Watch Market Prices

Monitor real-time prices for a specific market. By default, watches both Up and Down outcomes.

```bash
python cli.py watch [--market <market-slug> | --asset <asset> --time-period <period>] [options]
```

**Market Selection** (one required):
- `--market <market-slug>`: Market slug (e.g., `btc-updown-15m-1767709800`)
- `--asset <asset>`: Asset name - `bitcoin`, `btc`, `ethereum`, or `eth` (requires `--time-period`)
- `--time-period <period>`: Time period - `15m` (15-minute) or `1h` (hourly) (required with `--asset`)

**Options**:
- `--frequency <hz>`: Polling frequency in Hz (default: 1.0)
- `--limit <n>`: Number of ticks to display before stopping (optional)
- `--trade`: Enable automated trading with portfolio manager
- `--initial-balance <amount>`: Initial USDC balance for trading (default: 1000.0)
- `--strategy <strategy>`: Trading strategy - `random` or `arbitrage` (default: `random`)

**Examples**:
```bash
# Watch latest Bitcoin 15-minute market
python cli.py watch --asset bitcoin --time-period 15m --limit 2

# Watch with automated trading using arbitrage strategy
python cli.py watch --asset btc --time-period 15m --trade --strategy arbitrage --initial-balance 500.0

# Watch explicit market slug
python cli.py watch --market btc-updown-15m-1767710700 --frequency 2.0
```

### `buy` - Place Buy Order

Place a market buy order on Polymarket.

```bash
python cli.py buy [--market <market-slug> | --asset <asset> --time-period <period>] --amount <usdc>
```

**Market Selection** (one required):
- `--market <market-slug>`: Market slug (e.g., `btc-updown-15m-1767709800`)
- `--asset <asset>`: Asset name - `bitcoin`, `btc`, `ethereum`, or `eth` (requires `--time-period`)
- `--time-period <period>`: Time period - `15m` (15-minute) or `1h` (hourly) (required with `--asset`)

**Options**:
- `--amount <usdc>`: Order amount in USDC (required)

**Note**: Buy orders default to the "Up" outcome.

**Examples**:
```bash
# Buy latest Bitcoin 15-minute market (Up outcome)
python cli.py buy --asset bitcoin --time-period 15m --amount 10.0

# Buy using explicit market slug
python cli.py buy --market btc-updown-15m-1767710700 --amount 10.0
```

### `scrape` - Scrape Market Prices to CSV

Scrape market prices to CSV file for backtesting.

```bash
python cli.py scrape [--market <market-slug> | --asset <asset> --time-period <period>] [options]
```

**Market Selection** (one required):
- `--market <market-slug>`: Market slug (e.g., `btc-updown-15m-1767709800`)
- `--asset <asset>`: Asset name - `bitcoin`, `btc`, `ethereum`, or `eth` (requires `--time-period`)
- `--time-period <period>`: Time period - `15m` (15-minute) or `1h` (hourly) (required with `--asset`)

**Options**:
- `--frequency <hz>`: Polling frequency in Hz (default: 1.0)
- `--limit <n>`: Number of ticks to scrape (optional)

**Examples**:
```bash
# Scrape latest Bitcoin 15-minute market
python cli.py scrape --asset bitcoin --time-period 15m --limit 100

# Scrape explicit market slug
python cli.py scrape --market btc-updown-15m-1767710700 --frequency 0.5
```

## Project Structure

```
polytrader/
├── cli.py                 # Command-line interface
├── polytrader/
│   ├── adapters/          # Market data adapters
│   │   ├── polymarket.py  # Polymarket API adapter
│   │   └── prices.py      # Price data models
│   ├── clob.py            # Order placement functions
│   ├── config.py          # Configuration and secrets
│   ├── events.py          # Event bus (pub/sub)
│   ├── gamma.py           # Gamma API client
│   ├── market_discovery.py # Market slug generation from asset/time period
│   ├── observer.py        # Market data observer
│   ├── store.py           # Tick storage
│   └── types.py           # Data types
└── tests/                 # Unit tests
```

## Architecture

The system uses an event-driven architecture:

1. **Adapter**: Fetches market data from Polymarket API
2. **Observer**: Streams ticks and publishes to event bus
3. **Event Bus**: Pub/sub system for distributing market data
4. **Store**: Maintains historical tick data in memory

This design allows you to easily extend the system with:
- Custom trading strategies
- Multiple market monitoring
- Order execution logic
- Data analysis tools

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Linting

```bash
ruff check .
```

### Formatting

```bash
ruff format .
```

### Type Checking

```bash
mypy .
```

Or use the Makefile:

```bash
make test
make lint
make format
make type-check
```

## Market Slug Discovery

The system can automatically discover the latest market slug based on asset and time period, eliminating the need to manually find and enter slugs.

**Supported Formats**:
- **15-minute markets**: `{asset}-updown-15m-{timestamp}` (e.g., `btc-updown-15m-1767709800`)
- **Hourly markets**: `{asset}-up-or-down-{month}-{day}-{hour}am-et` (e.g., `bitcoin-up-or-down-january-6-9am-et`)

**Supported Assets**:
- `bitcoin` or `btc` for Bitcoin markets
- `ethereum` or `eth` for Ethereum markets

**Supported Time Periods**:
- `15m` for 15-minute markets
- `1h` for hourly markets

The system calculates the latest market slug based on the current UTC time, automatically aligning to the appropriate time interval. For hourly markets, it uses Eastern Time (ET) with automatic DST handling.

You can still use explicit market slugs if needed - just use the `--market` option instead of `--asset` and `--time-period`.

## Troubleshooting

### "Insufficient balance" error
- Ensure you have enough USDC in your wallet
- Deposit USDC to your Polymarket wallet

### "Market not found" error
- Verify the market slug is correct
- Check that the market is active on Polymarket

### "No orderbook exists" warning
- The market may be inactive or closed
- Try a different market or wait for the market to become active

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

