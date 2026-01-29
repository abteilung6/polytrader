# OpenAPI spec (backend)

- **Source:** FastAPI app (`polytrader.api.app`).
- **Generate:** From repo root run `make openapi-dump` (writes `openapi.json`).
- **Consume:** Frontend runs `make generate-api` in `polytrader-console/` to generate the TypeScript client from this spec.

Commit `openapi.json` so the frontend can generate the API client without running the backend.
