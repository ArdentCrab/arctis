"""Path safety for CLI file arguments (no traversal outside the working directory)."""

from __future__ import annotations

import os
from pathlib import Path


class GhostPathError(ValueError):
    """Rejected path (traversal, missing base)."""


def resolve_under_cwd(
    path: str | Path,
    *,
    cwd: Path | None = None,
    allow_absolute: bool = False,
) -> Path:
    """
    Resolve ``path`` to an absolute path that stays under ``cwd`` (default: process CWD).

    Rejects paths that escape the base after resolution (including via symlinks).
    By default, absolute paths are rejected so all CLI inputs are CWD-relative.
    """
    base = (cwd or Path.cwd()).resolve()
    p = Path(path)
    if p.is_absolute() and not allow_absolute:
        raise GhostPathError(
            "absolute paths are not allowed; use a path relative to the working directory"
        )
    if not p.is_absolute():
        candidate = (base / p).resolve()
    else:
        candidate = p.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise GhostPathError(f"path must stay under {base}: {path!r}") from e
    return candidate


def chmod_private_file(path: Path, *, mode: int = 0o600) -> None:
    """Best-effort restrictive permissions (POSIX only)."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass
