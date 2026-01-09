# Polytrader

A Python trading system for Polymarket that enables real-time market monitoring and order placement on prediction markets.

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` and add your credentials:
   ```env
   PRIVATE_KEY=your_private_key_here
   FUNDER=your_magic_wallet_address_here
   SIGNATURE_TYPE=1  # 0=EOA/MetaMask, 1=Magic wallet, 2=Browser wallet proxy
   ```

## Main Commands

### Watch

Monitor real-time prices for a market:

```bash
# Watch latest market by asset and time period
python cli.py watch --asset bitcoin --time-period 15m

# Watch with automated trading
python cli.py watch --asset eth --time-period 15m --strategy gabagool --trade --frequency 2

# Watch explicit market slug
python cli.py watch --market btc-updown-15m-1767710700 --frequency 2.0
```

**Options:**
- `--market <slug>`: Market slug (e.g., `btc-updown-15m-1767709800`)
- `--asset <asset>`: Asset name - `bitcoin`, `btc`, `ethereum`, `eth`, `solana`, `sol`, `xrp` (requires `--time-period`)
- `--time-period <period>`: `15m` or `1h` (required with `--asset`)
- `--frequency <hz>`: Polling frequency in Hz (default: 1.0)
- `--limit <n>`: Number of ticks to display (optional)
- `--trade`: Enable automated trading
- `--money`: Execute real orders on Polymarket (requires `--trade`)
- `--initial-balance <amount>`: Initial USDC balance (default: 1000.0)
- `--strategy <strategy>`: Trading strategy (default: `gabagool`)

### Buy

Place a market buy order:

```bash
# Buy latest market by asset and time period
python cli.py buy --asset bitcoin --time-period 15m --amount 10.0

# Buy using explicit market slug
python cli.py buy --market btc-updown-15m-1767710700 --amount 10.0
```

**Options:**
- `--market <slug>`: Market slug
- `--asset <asset>`: Asset name (requires `--time-period`)
- `--time-period <period>`: `15m` or `1h` (required with `--asset`)
- `--amount <usdc>`: Order amount in USDC (required)

### Scrape

Scrape market prices to CSV for backtesting:

```bash
# Scrape latest market by asset and time period
python cli.py scrape --asset bitcoin --time-period 15m --limit 100

# Scrape explicit market slug
python cli.py scrape --market btc-updown-15m-1767710700 --frequency 0.5
```

**Options:**
- `--market <slug>`: Market slug
- `--asset <asset>`: Asset name (requires `--time-period`)
- `--time-period <period>`: `15m` or `1h` (required with `--asset`)
- `--frequency <hz>`: Polling frequency in Hz (default: 1.0)
- `--limit <n>`: Number of ticks to scrape (optional)

### Backtest

Backtest trading strategies on historical market data:

```bash
# Backtest all markets in data directory
python backtest.py --strategy gabagool --initial-balance 1000.0

# Backtest specific market
python backtest.py --market btc-updown-15m-1767710700 --strategy gabagool

# Backtest with custom data directory
python backtest.py --data-dir ./user_trades/data --strategy gabagool
```

**Options:**
- `--strategy <strategy>`: Strategy to backtest (default: `arbitrage`)
- `--initial-balance <amount>`: Initial balance in USDC (default: 1000.0)
- `--data-dir <dir>`: Directory containing market data (default: `data`)
- `--timestamp-tolerance <seconds>`: Maximum timestamp difference for matching UP/DOWN ticks (default: 0.1)
- `--market <slug>`: Backtest only a specific market slug (default: all markets)

### Streamlit App

Visualize backtest results with an interactive dashboard:

```bash
# Run Streamlit app
streamlit run streamlit_app.py
```

The app provides:
- Interactive backtest visualization dashboard
- Market detail views with trade-by-trade analysis
- Strategy performance metrics and charts
- Filtering by date and asset
