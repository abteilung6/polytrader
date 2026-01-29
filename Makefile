.PHONY: help install install-dev lint format type-check test test-unit test-integration test-replay clean-test-cache
.PHONY: db-up db-down db-migrate db-logs db-psql
.PHONY: test-db-up test-db-down test-db-migrate
.PHONY: prometheus-up prometheus-down prometheus-logs
.PHONY: test-prometheus-up test-prometheus-down test-prometheus-logs
.PHONY: frontend-install frontend-test frontend-lint frontend-format frontend-format-check frontend-type-check frontend-build

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

# Development Prometheus
prometheus-up:
	docker compose up -d prometheus
	@echo "Waiting for Prometheus to be ready..."
	@timeout 30 bash -c 'until curl -s http://localhost:9092/-/healthy > /dev/null; do sleep 1; done' || echo "Prometheus may not be ready yet"

prometheus-down:
	docker compose stop prometheus

prometheus-logs:
	docker compose logs -f prometheus

# Test Prometheus
test-prometheus-up:
	docker compose -f docker-compose.test.yml up -d prometheus-test
	@echo "Waiting for test Prometheus to be ready..."
	@timeout 30 bash -c 'until curl -s http://localhost:9091/-/healthy > /dev/null; do sleep 1; done' || echo "Test Prometheus may not be ready yet"

test-prometheus-down:
	docker compose -f docker-compose.test.yml stop prometheus-test

test-prometheus-logs:
	docker compose -f docker-compose.test.yml logs -f prometheus-test

# Grafana
grafana-up:
	docker compose up -d grafana
	@echo "Waiting for Grafana to be ready..."
	@timeout 30 bash -c 'until curl -s http://localhost:3000/api/health > /dev/null; do sleep 1; done' || echo "Grafana may not be ready yet"
	@echo "Grafana is available at http://localhost:3000 (admin/admin)"

grafana-down:
	docker compose stop grafana

grafana-logs:
	docker compose logs -f grafana

# Frontend (polytrader-console)
CONSOLE_DIR = polytrader-console

frontend-install:
	cd $(CONSOLE_DIR) && npm install

frontend-test:
	cd $(CONSOLE_DIR) && npm run test

frontend-lint:
	cd $(CONSOLE_DIR) && npm run lint

frontend-format:
	cd $(CONSOLE_DIR) && npm run format

frontend-format-check:
	cd $(CONSOLE_DIR) && npm run format:check

frontend-type-check:
	cd $(CONSOLE_DIR) && npm run type-check

frontend-build:
	cd $(CONSOLE_DIR) && npm run build
