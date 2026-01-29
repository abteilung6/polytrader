# Polytrader Console

Web UI for the Polytrader trading platform. React + TypeScript + Vite, with HMR, ESLint, Prettier, and Vitest.

## API client (generated from OpenAPI)

- **Spec:** Backend dumps OpenAPI to `../openapi/openapi.json`. From repo root: `make openapi-dump`.
- **Generate client:** `make generate-api` (or `npm run generate-api`) — generates TypeScript Axios client into `src/lib/api` (models + services). Requires `../openapi/openapi.json` to exist.
- **Using the client:** `src/lib/api-client.ts` exports `controlApi` and `marketApi` (base URL from `VITE_API_URL`, default `http://localhost:8000`). Import e.g. `import { marketApi } from '@/lib/api-client'`.

## Environment

- **Location:** `.env` in **polytrader-console/** (Vite loads env from the app root). Do not use the repo-root `.env` for frontend.
- **Variable:** `VITE_API_URL` — API base URL (default in code: `http://localhost:8000`). Optional; set only if the backend runs elsewhere.
- **Example:** Copy `env.example` to `.env` and uncomment/edit `VITE_API_URL` if needed. `.env` is gitignored.

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
