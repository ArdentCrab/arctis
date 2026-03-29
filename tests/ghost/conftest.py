"""Shared fixtures for Ghost CLI tests (CWD-bound path safety)."""

from __future__ import annotations

import pytest


@pytest.fixture
def ghost_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Run CLI path resolution relative to ``tmp_path``."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
