"""Path boundary and absolute-path rules for Ghost CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from arctis_ghost.errors import GhostInputError
from arctis_ghost.input_limits import MAX_JSON_BYTES
from arctis_ghost.paths import GhostPathError, resolve_under_cwd
from arctis_ghost.util import load_json


def test_resolve_rejects_parent_escape(ghost_cwd) -> None:
    with pytest.raises(GhostPathError):
        resolve_under_cwd("..")


def test_resolve_rejects_absolute_path_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "f.json"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(GhostPathError, match="absolute"):
        resolve_under_cwd(p)


def test_load_json_rejects_oversize(ghost_cwd) -> None:
    p = Path("big.json")
    p.write_bytes(b"{" + b"x" * (MAX_JSON_BYTES + 1) + b"}")
    with pytest.raises(GhostInputError, match="max size"):
        load_json("big.json")
