"""Tests for ``arctis_ghost.init_demo`` (P4)."""

from __future__ import annotations

from pathlib import Path

import yaml
from arctis_ghost.init_demo import run_init_demo


def test_init_demo_creates_files(tmp_path: Path) -> None:
    run_init_demo(tmp_path)
    assert (tmp_path / "ghost.yaml").is_file()
    assert (tmp_path / "input.json").is_file()
    assert (tmp_path / "README.md").is_file()
    raw = yaml.safe_load((tmp_path / "ghost.yaml").read_text(encoding="utf-8"))
    assert raw["active_profile"] == "default"
    assert "skills" in (tmp_path / "input.json").read_text(encoding="utf-8")


def test_init_demo_refuses_overwrite(tmp_path: Path) -> None:
    (tmp_path / "ghost.yaml").write_text("x", encoding="utf-8")
    try:
        run_init_demo(tmp_path)
        raise AssertionError("expected FileExistsError")
    except FileExistsError:
        pass


def test_init_demo_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / "ghost.yaml").write_text("old", encoding="utf-8")
    run_init_demo(tmp_path, force=True)
    assert "active_profile" in (tmp_path / "ghost.yaml").read_text(encoding="utf-8")
