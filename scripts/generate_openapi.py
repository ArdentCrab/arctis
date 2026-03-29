"""Generate full OpenAPI spec from FastAPI app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arctis.app import create_app


def main() -> int:
    app = create_app()
    spec = app.openapi()
    out = Path("openapi.json")
    out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

