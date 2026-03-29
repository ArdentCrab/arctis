"""Sanity checks for ``docs/ghost_plg.md`` (P8)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = _REPO_ROOT / "docs"
GHOST_PLG = DOCS / "ghost_plg.md"


def test_ghost_plg_exists() -> None:
    assert GHOST_PLG.is_file()


def test_ghost_plg_markdown_links_resolve() -> None:
    text = GHOST_PLG.read_text(encoding="utf-8")
    for raw in re.findall(r"\]\(([^)]+\.md)\)", text):
        path = (DOCS / raw.split("#", 1)[0]).resolve()
        assert path.is_file(), f"broken link {raw!r} → {path}"
