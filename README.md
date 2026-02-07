# Polytrader

A trading system for Polymarket that automatically executes trades based on configurable trading models.

## Getting Started

### Platform Mode (Recommended)

Start the platform with multi-strategy support and control API:

```bash
# Start platform with safe defaults (paper trading)
python -m cli platform start

# Start with a config file
python -m cli platform start --config config/platform.paper.yaml
```

This will:
- Load strategies from the database
- Start paper trading (simulated execution)
- Provide a control API at `http://localhost:8000/docs`
- Share market supervisors across strategies for efficiency

**Control API:** Visit `http://localhost:8000/docs` to:
- Create and manage strategies
- Enable/disable execution
- Monitor platform state

Press `Ctrl+C` to stop the platform.

### Configuration

All platform settings (API host/port, risk limits, execution parameters, etc.)
are controlled via a YAML config file. If `--config` is omitted, safe hardcoded
defaults are used.

```bash
# See all available options in the example config
cat config/platform.yaml.example

# Use paper trading config
python -m cli platform start --config config/platform.paper.yaml
```

Secrets (private keys, database password) remain in `.env` and are never
placed in config files.

#### Paper Trading (Default)

Paper trading does not require API credentials. It uses simulated execution and tracks performance metrics.

#### Live Trading

For live trading, set environment variables in `.env`:
- `PRIVATE_KEY`: Your Polymarket private key
- `FUNDER`: Your funder address
- `SIGNATURE_TYPE`: Signature type (typically `1`)

**Warning:** Live trading executes real orders with real money. Always test with paper trading first.

### Available Commands

- `platform start`: Start the platform with multi-strategy support
  - `--config PATH`: Path to platform config YAML file (optional)
  - `--log-file PATH`: Optional file path to save logs
