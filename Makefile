.PHONY: help install install-dev lint format type-check test test-unit test-integration test-replay clean-test-cache
.PHONY: db-up db-down db-migrate db-logs db-psql
.PHONY: test-db-up test-db-down test-db-migrate

PYTHON ?= python3

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

clean-test-cache:
	@find tests -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find tests -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache 2>/dev/null || true
	@echo "Test cache cleared"

test: clean-test-cache
	pytest tests/ -v -n auto --import-mode=importlib

test-unit: clean-test-cache
	pytest tests/unit/ -v -n auto --import-mode=importlib

test-integration: clean-test-cache
	pytest tests/integration/ -v -n auto --import-mode=importlib

test-replay: clean-test-cache
	pytest tests/replay/ -v -n auto --import-mode=importlib

# Development Database
db-up:
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL to be ready..."
	@timeout 30 bash -c 'until docker exec polytrader-postgres pg_isready -U $${DB_USER:-polytrader}; do sleep 1; done' || echo "PostgreSQL may not be ready yet"

db-down:
	docker compose down

db-migrate:
	$(PYTHON) -m alembic upgrade head

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
	ALEMBIC_SQLALCHEMY_URL=postgresql+psycopg://test_user:test_password@localhost:5433/polytrader_test $(PYTHON) -m alembic upgrade head
