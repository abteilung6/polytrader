# Polytrader Console

Web UI for the Polytrader trading platform. React + TypeScript + Vite, with HMR, ESLint, Prettier, and Vitest.

## Lint, format, type-check (aligned with backend)

From this directory:

| Command             | Description                  |
| ------------------- | ---------------------------- |
| `make install`      | `npm install`                |
| `make test`         | Vitest run                   |
| `make lint`         | ESLint (no fix)              |
| `make lint-fix`     | ESLint with `--fix`          |
| `make format`       | Prettier write               |
| `make format-check` | Prettier check (CI)          |
| `make type-check`   | TypeScript `tsc -b --noEmit` |
| `make build`        | Production build             |

From repo root: `make frontend-test`, `make frontend-lint`, `make frontend-format`, `make frontend-type-check`, `make frontend-build`.
