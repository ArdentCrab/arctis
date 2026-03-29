"""Sanity checks for ``docs/demo_60.md`` (C6 / P6)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = _REPO_ROOT / "docs"
DEMO_60 = DOCS / "demo_60.md"


def test_demo_60_file_exists() -> None:
    assert DEMO_60.is_file(), f"expected {DEMO_60}"


def test_demo_60_contains_core_ghost_commands() -> None:
    text = DEMO_60.read_text(encoding="utf-8")
    assert "ghost run" in text
    assert "ghost watch" in text
    assert "ghost explain" in text
    assert "ghost evidence" in text


def test_demo_60_execute_body_json_is_valid() -> None:
    text = DEMO_60.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert blocks, "expected at least one ```json fenced block"
    body = json.loads(blocks[0])
    assert isinstance(body, dict)
    assert "input" in body
    assert isinstance(body["input"], dict)
    assert "skills" in body
    assert isinstance(body["skills"], list)
    assert body["skills"], "skills list should be non-empty for demo"
    for item in body["skills"]:
        assert isinstance(item, dict) and "id" in item


def test_demo_60_markdown_links_resolve() -> None:
    text = DEMO_60.read_text(encoding="utf-8")
    for raw in re.findall(r"\]\(([^)]+\.md)\)", text):
        path = (DOCS / raw.split("#", 1)[0]).resolve()
        assert path.is_file(), f"broken link target {raw!r} (resolved {path})"
