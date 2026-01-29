# Polytrader Console

Web UI for the Polytrader trading platform. React + TypeScript + Vite, with HMR, ESLint, Prettier, and Vitest.

## API client (generated from OpenAPI)

- **Spec:** Backend dumps OpenAPI to `../openapi/openapi.json`. From repo root: `make openapi-dump`.
- **Generate client:** `make generate-api` (or `npm run generate-api`) — generates TypeScript Axios client into `src/lib/api` (models + services). Requires `../openapi/openapi.json` to exist.

## Lint, format, type-check (aligned with backend)

From this directory:

| Command             | Description                           |
| ------------------- | ------------------------------------- |
| `make install`      | `npm install`                         |
| `make generate-api` | Generate API client from OpenAPI spec |
| `make test`         | Vitest run                            |
| `make lint`         | ESLint (no fix)                       |
| `make lint-fix`     | ESLint with `--fix`                   |
| `make format`       | Prettier write                        |
| `make format-check` | Prettier check (CI)                   |
| `make type-check`   | TypeScript `tsc -b --noEmit`          |
| `make build`        | Production build                      |

From repo root: `make openapi-dump`, `make frontend-generate-api`, `make frontend-test`, `make frontend-lint`, etc.
