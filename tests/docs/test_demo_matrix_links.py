"""Sanity checks for ``docs/demo_matrix.md`` (P6)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = _REPO_ROOT / "docs"
DEMO_MATRIX = DOCS / "demo_matrix.md"


def test_demo_matrix_file_exists() -> None:
    assert DEMO_MATRIX.is_file(), f"expected {DEMO_MATRIX}"


def test_demo_matrix_links_core_docs() -> None:
    text = DEMO_MATRIX.read_text(encoding="utf-8")
    assert "demo_60.md" in text
    assert "arctis_ghost_demo_matrix.md" in text
    assert "arctis_ghost_project_plan.md" in text
    assert "ghost_implementation_prompts.md" in text


def test_demo_matrix_internal_md_links_resolve() -> None:
    text = DEMO_MATRIX.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+\.md)\)", text)
    assert targets, "expected at least one .md link"
    for raw in targets:
        path = (DOCS / raw.split("#", 1)[0]).resolve()
        assert path.is_file(), f"broken link target {raw!r} (resolved {path})"
