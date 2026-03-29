"""Small JSON helpers for the Ghost CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from arctis_ghost.errors import GhostInputError
from arctis_ghost.input_limits import MAX_JSON_BYTES
from arctis_ghost.paths import GhostPathError, resolve_under_cwd


def load_json(path: str | Path, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    """Load and parse JSON from ``path`` (UTF-8), under CWD only; size-capped."""
    try:
        p = resolve_under_cwd(path)
    except GhostPathError as e:
        raise GhostInputError(str(e)) from e
    if p.stat().st_size > max_bytes:
        raise GhostInputError(f"JSON file exceeds max size ({max_bytes} bytes)")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def dumps_json(obj: Any) -> str:
    """Serialize ``obj`` as sorted-key, indented JSON (deterministic, UTF-8)."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)


def print_json(obj: Any) -> None:
    """Print ``obj`` as sorted-key, indented JSON (deterministic, UTF-8)."""
    print(dumps_json(obj))
