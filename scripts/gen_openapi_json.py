from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from backend.app.main import create_app  # type: ignore
    except Exception as e:
        print(f"ERROR: failed to import backend.app.main.create_app: {e}", file=sys.stderr)
        return 2

    app = create_app()
    # openapi-typescript currently expects OpenAPI 3.0.x.
    # FastAPI defaults to 3.1.0 in newer versions; downgrade for type generation.
    try:
        app.openapi_version = "3.0.2"
    except Exception:
        pass
    schema = app.openapi()
    json.dump(schema, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
