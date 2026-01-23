# Polytrader

A trading system for Polymarket that automatically executes trades based on configurable trading models.

## Getting Started

### Platform Mode (Recommended)

Start the platform with multi-strategy support and control API:

```bash
# Start platform (paper trading by default)
python -m cli platform start --api-host 0.0.0.0 --api-port 8000 > platform.log 2>&1
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

#### Paper Trading (Default)

Paper trading does not require API credentials. It uses simulated execution and tracks performance metrics.

#### Live Trading

For live trading, set environment variables:
- `PRIVATE_KEY`: Your Polymarket private key
- `FUNDER`: Your funder address
- `SIGNATURE_TYPE`: Signature type (typically `1`)

**⚠️ Warning:** Live trading executes real orders with real money. Always test with paper trading first.

### Available Commands

- `platform start`: Start the platform with multi-strategy support
