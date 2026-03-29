"""Pre-execution input validation (E1) — pure logic, no DB or Engine."""

from __future__ import annotations

from typing import Any, Mapping

# Keys that must not appear in workflow / customer payloads (governance).
_GOVERNANCE_FORBIDDEN_KEYS = frozenset(
    {
        "policy",
        "governance",
        "enforcement_prefix_snapshot",
        "review_db",
        "strict_policy_db",
        "allow_injected_policy",
        "routing_model",
        "routing",
        "sanitizer_policy",
        "sanitizerPolicy",
    }
)

_REPLAY_ALLOWED_TOP_LEVEL = frozenset({"engine_snapshot_id", "engine_snapshot", "input"})


class ValidationError(Exception):
    """Invalid client input before engine execution."""


def _ensure_object(input_data: Any, *, message: str = "input must be an object") -> dict[str, Any]:
    if input_data is None:
        raise ValidationError(message)
    if not isinstance(input_data, dict):
        raise ValidationError(message)
    return input_data


def _collect_governance_violations(value: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{path}.{k}" if path else str(k)
            if str(k) in _GOVERNANCE_FORBIDDEN_KEYS:
                out.append(p)
            out.extend(_collect_governance_violations(v, p))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out.extend(_collect_governance_violations(item, f"{path}[{i}]"))
    return out


def _definition_dict(pipeline_version: Any) -> dict[str, Any] | None:
    if pipeline_version is None:
        return None
    if isinstance(pipeline_version, Mapping):
        d = pipeline_version.get("definition")
        return dict(d) if isinstance(d, dict) else None
    d = getattr(pipeline_version, "definition", None)
    return dict(d) if isinstance(d, dict) else None


def _extract_schema_from_definition(definition: dict[str, Any] | None) -> dict[str, Any] | None:
    if not definition:
        return None
    schema = definition.get("input_schema")
    return dict(schema) if isinstance(schema, dict) else None


def validate_input_against_template(input_data: Any, template: Any) -> None:
    if template is None:
        return
    if not isinstance(template, dict):
        return
    data = _ensure_object(input_data)
    required = template.get("required")
    if isinstance(required, list):
        for key in required:
            if key not in data:
                raise ValidationError(f"missing required field: {key!r}")
    props = template.get("properties")
    if isinstance(props, dict) and props:
        allowed = set(props.keys())
        for key in data:
            if key not in allowed:
                raise ValidationError(f"unknown field: {key!r}")


def validate_input_against_policy(input_data: Any, policy: Any) -> None:
    if policy is None:
        return
    if not isinstance(policy, dict):
        return
    data = _ensure_object(input_data)
    forbidden = policy.get("forbidden_fields")
    if not isinstance(forbidden, list):
        return
    bad = [f for f in forbidden if f in data]
    if bad:
        raise ValidationError(f"policy violation: forbidden fields present: {sorted(bad)!r}")


def validate_input_against_pipeline_schema(input_data: Any, pipeline_version: Any) -> None:
    if pipeline_version is None:
        return
    definition = _definition_dict(pipeline_version)
    schema = _extract_schema_from_definition(definition)
    if schema:
        validate_input_against_template(input_data, schema)


def validate_input_against_workflow_schema(input_data: Any, pipeline_version: Any) -> None:
    """Validate workflow input_template (or similar dict) against target pipeline ``input_schema``."""
    if pipeline_version is None:
        return
    data = _ensure_object(input_data, message="input_template must be an object")
    bad = _collect_governance_violations(data)
    if bad:
        raise ValidationError(
            "invalid workflow input_template: governance fields not allowed: " + ", ".join(sorted(bad))
        )
    definition = _definition_dict(pipeline_version)
    schema = _extract_schema_from_definition(definition)
    if schema:
        validate_input_against_template(data, schema)


def validate_input_for_replay(snapshot: Any) -> None:
    if snapshot is None:
        raise ValidationError("invalid snapshot for replay")
    if not isinstance(snapshot, dict):
        raise ValidationError("invalid snapshot for replay")
    extra = set(snapshot.keys()) - _REPLAY_ALLOWED_TOP_LEVEL
    if extra:
        raise ValidationError(f"invalid snapshot for replay: disallowed keys: {sorted(extra)!r}")
    sid = snapshot.get("engine_snapshot_id")
    if not isinstance(sid, str) or not sid.strip():
        raise ValidationError("invalid snapshot for replay")
    es = snapshot.get("engine_snapshot")
    if not isinstance(es, dict):
        raise ValidationError("invalid snapshot for replay")
    if "input" in snapshot and not isinstance(snapshot["input"], dict):
        raise ValidationError("invalid snapshot for replay")


def validate_customer_execute_input(input_data: Any, workflow_version: Any) -> None:
    """
    Validates merged customer execute payload (governance + optional pipeline ``input_schema``).

    ``workflow_version`` may be a mapping or simple namespace with optional
    ``pipeline_input_schema`` (from ``PipelineVersion.definition["input_schema"]``) and optional
    ``merged_template_schema``: a JSON-schema-like dict (``required`` / ``properties``) derived
    from workflow + version templates when callers need stricter field rules.
    """
    data = _ensure_object(input_data, message="invalid customer input")
    bad = _collect_governance_violations(data)
    if bad:
        raise ValidationError(
            "invalid customer input: governance fields not allowed: " + ", ".join(sorted(bad))
        )

    if workflow_version is None:
        return

    tmpl_schema: dict[str, Any] | None = None
    schema: dict[str, Any] | None = None

    if isinstance(workflow_version, Mapping):
        raw_t = workflow_version.get("merged_template_schema")
        tmpl_schema = dict(raw_t) if isinstance(raw_t, dict) else None
        raw_schema = workflow_version.get("pipeline_input_schema")
        schema = dict(raw_schema) if isinstance(raw_schema, dict) else None
    else:
        raw_t = getattr(workflow_version, "merged_template_schema", None)
        tmpl_schema = dict(raw_t) if isinstance(raw_t, dict) else None
        raw_schema = getattr(workflow_version, "pipeline_input_schema", None)
        schema = dict(raw_schema) if isinstance(raw_schema, dict) else None

    if tmpl_schema:
        validate_input_against_template(data, tmpl_schema)
    if schema:
        validate_input_against_template(data, schema)
