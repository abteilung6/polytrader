.PHONY: help install install-dev lint format type-check test test-integration
.PHONY: db-up db-down db-migrate db-logs db-psql
.PHONY: test-db-up test-db-down test-db-migrate

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.dev.txt

lint:
	ruff check .

format:
	ruff format .

type-check:
	mypy .

test:
	pytest tests/ -v -n auto

test-integration:
	pytest tests/integration/ -v -n auto

# Development Database
db-up:
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL to be ready..."
	@timeout 30 bash -c 'until docker exec polytrader-postgres pg_isready -U $${DB_USER:-polytrader}; do sleep 1; done' || echo "PostgreSQL may not be ready yet"

db-down:
	docker compose down

db-migrate:
	@echo "Migrations will be implemented in Commit 3"

db-logs:
	docker compose logs -f postgres

db-psql:
	docker exec -it polytrader-postgres psql -U $${DB_USER:-polytrader} -d $${DB_DATABASE:-polytrader}

# Test Database
test-db-up:
	docker compose -f docker-compose.test.yml up -d
	@echo "Waiting for test PostgreSQL to be ready..."
	@timeout 30 bash -c 'until docker exec polytrader-postgres-test pg_isready -U test_user; do sleep 1; done' || echo "Test PostgreSQL may not be ready yet"

test-db-down:
	docker compose -f docker-compose.test.yml down

test-db-migrate:
	@echo "Migrations will be implemented in Commit 3"
