"""P12: bounded auto-recipe path suggestion."""

from __future__ import annotations

from pathlib import Path

from arctis_ghost.auto_recipe import suggest_recipe_path


def test_suggest_recipe_prefers_recipe_yaml_in_cwd(tmp_path: Path) -> None:
    (tmp_path / "recipe.yaml").write_text("workflow_id: x\n", encoding="utf-8")
    assert suggest_recipe_path(tmp_path) == "recipe.yaml"


def test_suggest_recipe_uses_recipes_dir_named_like_cwd(tmp_path: Path) -> None:
    proj = tmp_path / "myapp"
    proj.mkdir()
    recipes = proj / "recipes"
    recipes.mkdir()
    (recipes / "myapp.yaml").write_text("workflow_id: x\n", encoding="utf-8")
    assert suggest_recipe_path(proj) == str(Path("recipes") / "myapp.yaml")


def test_suggest_recipe_returns_none_when_nothing_matches(tmp_path: Path) -> None:
    assert suggest_recipe_path(tmp_path) is None
