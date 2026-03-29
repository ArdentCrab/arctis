"""Bind Pipeline A AI-node placeholders to a concrete input payload."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arctis.compiler import IRPipeline
from arctis.engine.modules.forbidden_fields import (
    _merged_forbidden_substrings,
    assert_no_forbidden_keys,
)
from arctis.engine.modules.sanitizer import sanitize_payload
from arctis.engine.modules.schema_validator import (
    _merged_required_fields,
    validate_required_fields,
)
from arctis.policy.resolver import resolve_effective_policy

from . import PIPELINE_A_PLACEHOLDER_PROMPT, PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT

_ENFORCEMENT_PATH = Path(__file__).resolve().parent.parent / "pipelines" / "enforcement.json"

# Fixed execution guardrails (enforcement contract). Not end-user content.
PIPELINE_A_BASE_INSTRUCTION = (
    "[Arctis Pipeline A — execution rules]\n"
    "- Use only information implied by the structured input JSON; do not invent tenant data.\n"
    "- Prefer concise, task-focused answers; avoid filler and hedging.\n"
    "- Never echo or request secrets, API keys, tokens, or raw credentials.\n"
    "- If output should be structured, use stable lowercase keys and valid JSON when asked.\n\n"
)


@dataclass(frozen=True)
class PipelinePromptBindResult:
    """Result of :func:`bind_pipeline_a_prompt` (IR + enforcement-only prefix for audits)."""

    ir: IRPipeline
    enforcement_prefix_snapshot: str


def _optional_enforcement_suffix() -> str:
    """Optional extra prefix lines from ``enforcement.json`` (product extension)."""
    try:
        if not _ENFORCEMENT_PATH.is_file():
            return ""
        raw = json.loads(_ENFORCEMENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    extra = raw.get("additional_prefix")
    return str(extra) if extra else ""


def enforcement_prefix_snapshot_text() -> str:
    """Enforcement block only (no policy mid-line, no user prompt) — for governance_meta / audits."""
    return f"{PIPELINE_A_BASE_INSTRUCTION}{_optional_enforcement_suffix()}"


def _enforcement_prefix() -> str:
    """Full enforcement block: base rules + optional JSON extension (still not user prompt)."""
    return enforcement_prefix_snapshot_text()


def _spec_v13_policy_mid() -> str:
    """Inserted between enforcement prefix and user prompt after policy checks (Spec v1.3)."""
    return "[Spec v1.3] input policy checks passed.\n"


def bind_pipeline_a_prompt(
    ir: IRPipeline,
    input_payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    effective_policy: Any = None,
    policy_db: Any = None,
) -> PipelinePromptBindResult:
    """
    Replace AI placeholders with payload-derived strings.

    Returns bound IR plus ``enforcement_prefix_snapshot`` (rules only; **excludes** user prompt).
    """
    ir2 = copy.deepcopy(ir)
    pn = str(getattr(ir, "name", None) or "pipeline_a")
    if effective_policy is not None:
        pol = effective_policy
    elif policy_db is not None:
        pol = resolve_effective_policy(policy_db, tenant_id, pn)
    else:
        raise ValueError("bind_pipeline_a_prompt requires effective_policy or policy_db")

    schema_node = ir.nodes.get("schema_validator")
    schema_cfg = (
        schema_node.config
        if schema_node is not None and isinstance(getattr(schema_node, "config", None), dict)
        else {}
    )
    forbid_node = ir.nodes.get("forbidden_fields")
    forbid_cfg = (
        forbid_node.config
        if forbid_node is not None and isinstance(getattr(forbid_node, "config", None), dict)
        else {}
    )

    pl = sanitize_payload(dict(input_payload))
    validate_required_fields(pl, _merged_required_fields(pol, schema_cfg))
    assert_no_forbidden_keys(pl, _merged_forbidden_substrings(pol, forbid_cfg))
    sanitized_input_json = json.dumps(pl, sort_keys=True)
    user_prompt = str(pl.get("prompt", ""))
    snap = enforcement_prefix_snapshot_text()
    composed_prompt_for_ir = f"{snap}{_spec_v13_policy_mid()}{user_prompt}"

    for node in ir2.nodes.values():
        if node.type == "ai":
            cfg = node.config
            if isinstance(cfg, dict):
                if isinstance(cfg.get("input"), str):
                    cfg["input"] = cfg["input"].replace(
                        PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT, sanitized_input_json
                    )
                if isinstance(cfg.get("prompt"), str):
                    cfg["prompt"] = cfg["prompt"].replace(
                        PIPELINE_A_PLACEHOLDER_PROMPT, composed_prompt_for_ir
                    )

    return PipelinePromptBindResult(ir=ir2, enforcement_prefix_snapshot=snap)
