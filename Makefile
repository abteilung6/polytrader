.PHONY: help install install-dev lint format type-check test test-fast test-integration

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

test-fast:
	pytest tests/ -v -n auto --ignore=tests/integration/

test-integration:
	pytest tests/integration/ -v -n auto
