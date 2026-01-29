"""Dump FastAPI OpenAPI spec to openapi/openapi.json (repo root).

Run from repo root: python scripts/dump_openapi.py
Used by frontend to generate API client (npm run generate-api).
"""

import json
import sys
from pathlib import Path

# Repo root: parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_DIR = REPO_ROOT / "openapi"
OPENAPI_JSON = OPENAPI_DIR / "openapi.json"


def main() -> None:
    if REPO_ROOT.resolve() != Path.cwd().resolve():
        print("Run from repo root: python scripts/dump_openapi.py", file=sys.stderr)
        sys.exit(1)

    from polytrader.api.app import create_app

    app = create_app()
    spec = app.openapi()
    OPENAPI_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_JSON.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Wrote {OPENAPI_JSON}")


if __name__ == "__main__":
    main()
