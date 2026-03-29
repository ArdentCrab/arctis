"""Recipe YAML loading and execute body merge (P5)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from arctis_ghost.config import GhostConfig
from arctis_ghost.recipes import (
    GhostRecipeError,
    GhostRecipeFile,
    build_execute_body,
    effective_workflow_id,
    load_recipe,
)


def test_load_recipe_golden(ghost_cwd) -> None:
    Path("r.yaml").write_text(
        """
workflow_id: wf-recipe
defaults:
  input:
    a: 1
skills:
  - id: cost_token_snapshot
    params: {}
input_mapping:
  mode: json
""".strip(),
        encoding="utf-8",
    )
    r = load_recipe("r.yaml")
    assert r.workflow_id == "wf-recipe"
    assert r.skills is not None and len(r.skills) == 1
    assert r.skills[0].id == "cost_token_snapshot"


def test_load_recipe_invalid_yaml(ghost_cwd) -> None:
    Path("bad.yaml").write_text("{ not: yaml", encoding="utf-8")
    with pytest.raises(GhostRecipeError, match="invalid YAML"):
        load_recipe("bad.yaml")


def test_load_recipe_validation(ghost_cwd) -> None:
    Path("bad2.yaml").write_text("skills: [{}]", encoding="utf-8")
    with pytest.raises(GhostRecipeError):
        load_recipe("bad2.yaml")


def test_build_body_merge_order(ghost_cwd) -> None:
    recipe = load_recipe_from_dict(
        {
            "defaults": {"input": {"x": 0, "y": 1}},
            "skills": [{"id": "routing_explain"}],
            "input_mapping": {"mode": "json"},
        },
    )
    Path("d.json").write_text('{"input": {"x": 2}}', encoding="utf-8")
    Path("p.json").write_text('{"input": {"z": 3}}', encoding="utf-8")
    body = build_execute_body(recipe, input_path=Path("d.json"), merge_json_path=Path("p.json"))
    assert body["input"] == {"x": 2, "y": 1, "z": 3}
    assert body["skills"] == [{"id": "routing_explain"}]


def test_build_body_text_mode(ghost_cwd) -> None:
    recipe = load_recipe_from_dict(
        {
            "defaults": {"input": {"title": "t"}},
            "input_mapping": {"mode": "text", "text_field": "body"},
        },
    )
    Path("note.txt").write_text("hello\n", encoding="utf-8")
    body = build_execute_body(recipe, input_path=Path("note.txt"))
    assert body["input"] == {"title": "t", "body": "hello\n"}


def test_effective_workflow_id_order() -> None:
    cfg = GhostConfig(
        api_base_url="http://x",
        workflow_id="from-config",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="o",
        state_enabled=False,
        state_dir=".ghost/state",
    )
    r = GhostRecipeFile(workflow_id="from-recipe")
    assert effective_workflow_id(cfg=cfg, recipe=r, cli_workflow_id=None) == "from-recipe"
    assert effective_workflow_id(cfg=cfg, recipe=r, cli_workflow_id="cli-wf") == "cli-wf"


def load_recipe_from_dict(d: dict) -> GhostRecipeFile:
    Path("gen.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    return load_recipe("gen.yaml")
