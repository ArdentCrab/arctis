"""P12: bounded heuristic to pick a recipe path from the working directory name."""

from __future__ import annotations

from pathlib import Path


def suggest_recipe_path(cwd: Path | None = None) -> str | None:
    """
    Return a **relative** recipe path if a known file exists, else ``None``.

    Rules (in order):

    1. ``recipe.yaml`` in the working directory.
    2. ``recipes/<cwd_basename>.yaml`` where ``cwd_basename`` is :func:`Path.name` of CWD.

    No recursion; no paths outside CWD. Documented for operators — not a policy engine.
    """
    base = (cwd or Path.cwd()).resolve()
    r1 = base / "recipe.yaml"
    if r1.is_file():
        return "recipe.yaml"
    name = base.name
    if not name:
        return None
    r2 = base / "recipes" / f"{name}.yaml"
    if r2.is_file():
        return str(Path("recipes") / f"{name}.yaml")
    return None
