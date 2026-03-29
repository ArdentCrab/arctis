"""Generate basic Python/TypeScript SDKs from OpenAPI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_openapi() -> dict:
    return json.loads(Path("openapi.json").read_text(encoding="utf-8"))


def _gen_python(spec: dict) -> str:
    title = spec.get("info", {}).get("title", "Arctis")
    return (
        '"""Auto-generated SDK stub."""\n\n'
        "import requests\n\n"
        f"SDK_TITLE = {title!r}\n"
        "def get_health(base_url: str, api_key: str) -> dict:\n"
        "    r = requests.get(f\"{base_url}/health\", headers={\"X-API-Key\": api_key})\n"
        "    r.raise_for_status()\n"
        "    return r.json()\n"
    )


def _gen_typescript(spec: dict) -> str:
    title = spec.get("info", {}).get("title", "Arctis")
    return (
        "// Auto-generated SDK stub.\n"
        f"export const SDK_TITLE = {title!r};\n"
        "export async function getHealth(baseUrl: string, apiKey: string) {\n"
        "  const res = await fetch(`${baseUrl}/health`, { headers: { 'X-API-Key': apiKey } });\n"
        "  if (!res.ok) throw new Error(`HTTP ${res.status}`);\n"
        "  return res.json();\n"
        "}\n"
    )


def main() -> int:
    spec = _load_openapi()
    out = Path("sdk")
    out.mkdir(exist_ok=True)
    (out / "python_sdk.py").write_text(_gen_python(spec), encoding="utf-8")
    (out / "typescript_sdk.ts").write_text(_gen_typescript(spec), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

