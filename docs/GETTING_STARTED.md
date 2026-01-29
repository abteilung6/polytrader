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

# Or manually using Alembic
alembic upgrade head
```

### 7. Verify Setup

```bash
# Run tests to verify everything works
make test

# Or start the platform for testing
python -m cli platform start --api-host 0.0.0.0 --api-port 8000
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
make db-migrate        # Run all pending migrations (Alembic)
alembic upgrade head   # Same as above
alembic downgrade -1   # Rollback last migration
alembic current       # Show current migration version
alembic history       # Show migration history
```

### Running Tests

```bash
make test                    # Run all tests
make test-integration       # Run integration tests (requires test DB)
make test-db-up            # Start test PostgreSQL
make test-db-down          # Stop test PostgreSQL
```

### Platform Mode (Recommended)

Start the platform with multi-strategy support:

```bash
# Start platform (paper trading by default)
python -m cli platform start --api-host 0.0.0.0 --api-port 8000 > platform.log 2>&1
```

The platform provides:
- **Control API**: `http://localhost:8000/docs` - Manage strategies via REST API
- **Multi-strategy support**: Run multiple strategies simultaneously
- **Shared market supervisors**: Efficient resource usage for strategies on the same market
- **Paper trading by default**: Safe testing without real money

**Using the Control API:**
1. Visit `http://localhost:8000/docs` in your browser
2. Create strategies via `/api/v1/strategies` endpoint
3. Enable/disable execution via `/api/v1/control/execution` endpoint
4. Monitor platform state via `/api/v1/state` endpoints

**Note:** The legacy single-strategy mode (`model paper`, `model live`) has been removed. Use `platform start` instead.

### Frontend (polytrader-console)

The operator console is a separate Vite + React app in `polytrader-console/`:

```bash
cd polytrader-console
make install
# Optional: set API URL if backend is not at http://localhost:8000
# cp env.example .env && edit VITE_API_URL
npm run dev
```

- **Env:** Use `.env` in **polytrader-console/** (not repo root). Copy `env.example` to `.env`; set `VITE_API_URL` only if the control API runs on a different host/port.
- **API client:** Generated from OpenAPI (`make generate-api`). Use `controlApi` and `marketApi` from `src/lib/api-client.ts`. See `polytrader-console/README.md`.

## Troubleshooting

### PostgreSQL Connection Errors

- Verify database is running: `docker ps | grep postgres`
- Check connection URL in `.env`: `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USER`, `DB_PASSWORD`
- Test connection: `make db-psql`

### Migration Errors

- Ensure database is running: `make db-up`
- Check migration files exist: `ls alembic/versions/`
- Check current migration version: `alembic current`
- View database schema: `make db-psql` then `\d events`

### Test Database Issues

- Start test database: `make test-db-up`
- Run test migrations: `make test-db-migrate`
- Check test database logs: `docker logs polytrader-postgres-test`
