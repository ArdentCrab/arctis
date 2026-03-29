"""Sanity checks for ``docs/Launch_readiness.md``."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = _REPO_ROOT / "docs"
LR_DOC = DOCS / "Launch_readiness.md"


def test_launch_readiness_md_exists() -> None:
    assert LR_DOC.is_file(), f"expected {LR_DOC}"


def test_launch_readiness_md_internal_md_links_resolve() -> None:
    text = LR_DOC.read_text(encoding="utf-8")
    for raw in re.findall(r"\]\(([^)]+\.md)\)", text):
        path = (DOCS / raw.split("#", 1)[0]).resolve()
        assert path.is_file(), f"broken link target {raw!r} (resolved {path})"


def test_launch_readiness_md_mentions_launch_check() -> None:
    text = LR_DOC.read_text(encoding="utf-8")
    assert "launch_check" in text
    assert "TEST_PIPELINE_ID" in text
