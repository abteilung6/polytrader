# Getting Started with Polytrader

This guide will help you set up the development environment for Polytrader.

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Git

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd polytrader
```

### 2. Install Python Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
make install-dev
```

### 3. Install Docker

**macOS:**
```bash
# Install Docker Desktop
brew install --cask docker
```

**Linux:**
```bash
# Install Docker and Docker Compose
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo chown $USER:$USER /var/run/docker.sock
```

**Windows:**
- Download and install Docker Desktop from https://www.docker.com/products/docker-desktop

### 4. Set Up Environment Variables

```bash
# Copy example environment file
cp env.example .env

# Edit .env and set your values
# Required:
# - DB_PASSWORD: PostgreSQL password
# - PRIVATE_KEY: Polymarket private key (for live trading)
# - FUNDER: Funder address (for live trading)
```

### 5. Start PostgreSQL Database

```bash
# Start development database
make db-up

# Verify it's running
docker ps | grep polytrader-postgres
```

### 6. Run Database Migrations

```bash
# Run migrations to create events table
make db-migrate
```

**Note:** Migrations will be available after Commit 3 is implemented.

### 7. Verify Setup

```bash
# Run tests to verify everything works
make test

# Or run a quick paper trading test
python -m cli model paper --market btc-updown-15m --max-trades 1
```

## Development Workflow

### Starting the Database

```bash
make db-up        # Start PostgreSQL
make db-down      # Stop PostgreSQL
make db-logs      # View database logs
make db-psql      # Connect to database with psql
```

### Running Migrations

```bash
make db-migrate   # Run all pending migrations
```

### Running Tests

```bash
make test                    # Run all tests
make test-integration       # Run integration tests (requires test DB)
make test-db-up            # Start test PostgreSQL
make test-db-down          # Stop test PostgreSQL
```

### Paper Trading

```bash
python -m cli model paper \
  --market btc-updown-15m \
  --buy-threshold 0.30 \
  --sell-threshold 0.50 \
  --size 1.0
```

## Troubleshooting

### PostgreSQL Connection Errors

- Verify database is running: `docker ps | grep postgres`
- Check connection URL in `.env`: `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USER`, `DB_PASSWORD`
- Test connection: `make db-psql`

### Migration Errors

- Ensure database is running: `make db-up`
- Check migration files exist: `ls polytrader/events/migrations/versions/`
- View database schema: `make db-psql` then `\d events`

### Test Database Issues

- Start test database: `make test-db-up`
- Run test migrations: `make test-db-migrate`
- Check test database logs: `docker logs polytrader-postgres-test`
