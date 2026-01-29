.PHONY: help install generate-api test lint lint-fix format format-check type-check build dev preview

help:
	@echo "polytrader-console targets:"
	@echo "  install       - npm install"
	@echo "  generate-api  - generate TypeScript API client from ../openapi/openapi.json"
	@echo "  test          - vitest run"
	@echo "  lint          - eslint ."
	@echo "  lint-fix      - eslint . --fix"
	@echo "  format        - prettier --write ."
	@echo "  format-check  - prettier --check . (CI)"
	@echo "  type-check    - tsc -b --noEmit"
	@echo "  build         - tsc -b && vite build"
	@echo "  dev           - vite dev server"
	@echo "  preview       - vite preview (after build)"

install:
	npm install

generate-api:
	npm run generate-api

test:
	npm run test

lint:
	npm run lint

lint-fix:
	npm run lint:fix

format:
	npm run format

format-check:
	npm run format:check

type-check:
	npm run type-check

build:
	npm run build

dev:
	npm run dev

preview:
	npm run preview
