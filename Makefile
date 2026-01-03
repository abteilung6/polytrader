.PHONY: help install install-dev lint format type-check

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
