"""Ghost recipes: YAML → customer execute body (P5). No engine imports."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arctis_ghost.config import GhostConfig
from arctis_ghost.input_limits import MAX_CLI_FILE_BYTES, MAX_JSON_BYTES
from arctis_ghost.paths import GhostPathError, resolve_under_cwd


class GhostRecipeError(ValueError):
    """Invalid or unreadable recipe file."""


class SkillEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class InputMappingSpec(BaseModel):
    """How ``--input`` is merged into the execute body."""

    model_config = ConfigDict(extra="ignore")

    mode: Literal["json", "text"] = "json"
    #: For ``mode=="text"``: key under ``input`` for the file contents (UTF-8).
    text_field: str = "body"


class GhostRecipeFile(BaseModel):
    """Root object in a recipe YAML file."""

    model_config = ConfigDict(extra="ignore")

    workflow_id: str | None = None
    #: When ``None``, recipe does not override ``skills`` from defaults/file merge.
    skills: list[SkillEntry] | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)
    input_mapping: InputMappingSpec = Field(default_factory=InputMappingSpec)
    output_mapping: dict[str, Any] = Field(default_factory=dict)


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``overlay`` onto ``base`` (dict values merged recursively)."""
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_recipe(path: str | Path) -> GhostRecipeFile:
    """Load and validate a recipe YAML file (must resolve under process CWD)."""
    try:
        p = resolve_under_cwd(path)
    except GhostPathError as e:
        raise GhostRecipeError(str(e)) from e
    if p.stat().st_size > MAX_CLI_FILE_BYTES:
        raise GhostRecipeError(f"recipe file exceeds max size ({MAX_CLI_FILE_BYTES} bytes)")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise GhostRecipeError(f"cannot read recipe {p}: {e}") from e
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise GhostRecipeError(f"invalid YAML in {p}: {e}") from e
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise GhostRecipeError(f"{p}: recipe root must be a mapping")
    try:
        return GhostRecipeFile.model_validate(raw)
    except ValidationError as e:
        raise GhostRecipeError(str(e)) from e


def _skills_to_json(skills: list[SkillEntry]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in skills:
        d: dict[str, Any] = {"id": s.id}
        if s.params:
            d["params"] = s.params
        out.append(d)
    return out


def build_execute_body(
    recipe: GhostRecipeFile,
    *,
    input_path: Path | None = None,
    merge_json_path: Path | None = None,
    cli_body_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the POST body for customer execute.

    Merge order (lowest → highest): ``recipe.defaults`` < file from ``input_path``
    (per ``input_mapping``) < ``recipe.skills`` when set < JSON from ``merge_json_path``
    < ``cli_body_patch``.
    """
    body: dict[str, Any] = copy.deepcopy(recipe.defaults) if recipe.defaults else {}

    if input_path is not None:
        try:
            ip = resolve_under_cwd(input_path)
        except GhostPathError as e:
            raise GhostRecipeError(str(e)) from e
        max_in = MAX_JSON_BYTES if recipe.input_mapping.mode == "json" else MAX_CLI_FILE_BYTES
        if ip.stat().st_size > max_in:
            raise GhostRecipeError(f"input file exceeds max size ({max_in} bytes)")
        try:
            raw_file = ip.read_text(encoding="utf-8")
        except OSError as e:
            raise GhostRecipeError(f"cannot read input file {ip}: {e}") from e
        spec = recipe.input_mapping
        if spec.mode == "json":
            try:
                loaded = json.loads(raw_file)
            except json.JSONDecodeError as e:
                raise GhostRecipeError(f"{ip}: invalid JSON: {e}") from e
            if not isinstance(loaded, dict):
                raise GhostRecipeError(f"{ip}: JSON root must be an object for mode=json")
            body = deep_merge(body, loaded)
        else:
            inp = body.get("input")
            if not isinstance(inp, dict):
                inp = {}
            else:
                inp = copy.deepcopy(inp)
            if spec.text_field in inp and not isinstance(inp.get(spec.text_field), str):
                raise GhostRecipeError(
                    f"input_mapping.text_field {spec.text_field!r} would overwrite a non-string"
                )
            inp[spec.text_field] = raw_file
            body = deep_merge(body, {"input": inp})

    if recipe.skills is not None:
        body["skills"] = _skills_to_json(recipe.skills)

    if merge_json_path is not None:
        try:
            mj = resolve_under_cwd(merge_json_path)
        except GhostPathError as e:
            raise GhostRecipeError(str(e)) from e
        if mj.stat().st_size > MAX_JSON_BYTES:
            raise GhostRecipeError(f"merge-json file exceeds max size ({MAX_JSON_BYTES} bytes)")
        try:
            t = mj.read_text(encoding="utf-8")
            patch = json.loads(t)
        except OSError as e:
            raise GhostRecipeError(f"cannot read merge-json {mj}: {e}") from e
        except json.JSONDecodeError as e:
            raise GhostRecipeError(f"{mj}: invalid JSON: {e}") from e
        if not isinstance(patch, dict):
            raise GhostRecipeError(f"{mj}: JSON root must be an object")
        body = deep_merge(body, patch)

    if cli_body_patch:
        body = deep_merge(body, cli_body_patch)

    return body


def effective_workflow_id(
    *,
    cfg: GhostConfig,
    recipe: GhostRecipeFile | None = None,
    cli_workflow_id: str | None = None,
) -> str:
    """CLI override > recipe > config profile (same idea as Ghost config env overrides)."""
    if cli_workflow_id is not None and str(cli_workflow_id).strip():
        return str(cli_workflow_id).strip()
    if recipe is not None and recipe.workflow_id is not None and str(recipe.workflow_id).strip():
        return str(recipe.workflow_id).strip()
    return cfg.workflow_id
