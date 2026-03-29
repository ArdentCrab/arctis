"""Scaffold a minimal Ghost demo directory (P4)."""

from __future__ import annotations

from pathlib import Path

_GHOST_YAML = """# Replace workflow_id with a real UUID from your tenant (POST /workflows or UI).
active_profile: default
profiles:
  default:
    api_base_url: http://localhost:8000
    workflow_id: "00000000-0000-0000-0000-000000000000"
    # api_key: ""   # prefer: export ARCTIS_API_KEY=...
"""

_INPUT_JSON = """{
  "input": {
    "query": "What is the capital of France?"
  },
  "skills": [
    {"id": "prompt_matrix"},
    {"id": "routing_explain"},
    {"id": "cost_token_snapshot"}
  ]
}
"""

_README = """# Ghost demo (init-demo)

1. Set `workflow_id` in `ghost.yaml` (or use env `ARCTIS_GHOST_WORKFLOW_ID`).
2. `export ARCTIS_API_KEY=...`
3. `ghost run input.json`  → copy run id
4. `ghost watch <run_id>` / `ghost explain <run_id>` / `ghost evidence <run_id>`

Full walkthrough: repository `docs/demo_60.md`
Capability matrix: repository `docs/demo_matrix.md`
"""


def run_init_demo(target: Path, *, force: bool = False) -> None:
    """
    Create ``ghost.yaml``, ``input.json``, and ``README.md`` under ``target``.

    Raises :class:`FileExistsError` if any file exists and ``force`` is false.
    """
    dest = target.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    mapping = {
        "ghost.yaml": _GHOST_YAML,
        "input.json": _INPUT_JSON,
        "README.md": _README,
    }
    for name, content in mapping.items():
        path = dest / name
        if path.exists() and not force:
            raise FileExistsError(str(path))
    for name, content in mapping.items():
        (dest / name).write_text(content, encoding="utf-8")
