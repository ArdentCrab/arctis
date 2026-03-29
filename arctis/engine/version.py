"""Engine version string (Phase 1.3 — aligned with package metadata)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def read_engine_version() -> str:
    """Read ``[project].version`` from ``pyproject.toml`` next to the package root."""
    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        candidate = parent / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        in_project = False
        for line in text.splitlines():
            s = line.strip()
            if s == "[project]":
                in_project = True
                continue
            if s.startswith("[") and s.endswith("]"):
                in_project = False
            if in_project and s.startswith("version"):
                m = re.match(r'version\s*=\s*["\']([^"\']+)["\']', s)
                if m:
                    return m.group(1)
    return "unknown"
