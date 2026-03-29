"""P14: optional lifecycle hooks for ``ghost run`` (subprocess, timeout, no policy engine)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from arctis_ghost.config import GhostConfig
from arctis_ghost.paths import GhostPathError, resolve_under_cwd
from arctis_ghost.util import dumps_json

HookPhase = Literal["pre_run", "post_run", "on_error"]


class GhostHookError(RuntimeError):
    """Hook script missing, path invalid, or failed in a blocking phase."""


def _script_command(resolved: Path) -> list[str]:
    if resolved.suffix.lower() == ".py":
        return [sys.executable, str(resolved)]
    return [str(resolved)]


def _hook_script_for_phase(cfg: GhostConfig, phase: HookPhase) -> str:
    if phase == "pre_run":
        return str(cfg.hook_pre_run).strip()
    if phase == "post_run":
        return str(cfg.hook_post_run).strip()
    return str(cfg.hook_on_error).strip()


def run_ghost_hook(
    phase: HookPhase,
    cfg: GhostConfig,
    *,
    body: dict[str, Any],
    workflow_id: str,
    run_id: str | None = None,
    error_message: str | None = None,
    ghost_exit_code: int | None = None,
) -> int:
    """
    Run the configured hook for ``phase`` if set.

    Returns the subprocess exit code, or ``0`` if no hook is configured.
    On timeout or launch error, raises :exc:`GhostHookError` for ``pre_run``;
    for ``post_run`` / ``on_error`` the caller may downgrade to a warning.
    """
    raw = _hook_script_for_phase(cfg, phase)
    if not raw:
        return 0

    try:
        script_path = resolve_under_cwd(raw)
    except GhostPathError as e:
        raise GhostHookError(str(e)) from e
    if not script_path.is_file():
        raise GhostHookError(f"hook script not found or not a file: {script_path}")

    payload: dict[str, Any] = {
        "hook": phase,
        "workflow_id": workflow_id,
        "execute_body": body,
        "run_id": run_id,
        "error": error_message,
        "ghost_exit_code": ghost_exit_code,
    }
    stdin_text = dumps_json(payload) + "\n"
    cmd = _script_command(script_path)
    timeout = float(cfg.hook_timeout_seconds)
    child_env = {
        **os.environ,
        "ARCTIS_GHOST_HOOK": phase,
        "ARCTIS_GHOST_WORKFLOW_ID": workflow_id,
    }
    if run_id:
        child_env["ARCTIS_GHOST_RUN_ID"] = run_id

    cwd = Path.cwd()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=stdin_text,
            text=True,
            timeout=timeout,
            env=child_env,
            capture_output=True,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise GhostHookError(
            f"hook {phase} timed out after {timeout}s ({script_path})"
        ) from e
    except OSError as e:
        raise GhostHookError(f"hook {phase} failed to start: {e}") from e

    if proc.returncode != 0 and proc.stdout:
        sys.stderr.write(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        sys.stderr.write(proc.stderr)
    return int(proc.returncode)
