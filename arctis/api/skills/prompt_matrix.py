"""Customer skill ``prompt_matrix`` — advise-only input matrix (B1, no engine / policy)."""

from __future__ import annotations

import json
from typing import Any

from arctis.api.skills.registry import SkillContext

# Total characters in all string values (recursive) for long vs short heuristic.
_SHORT_TEXT_CHAR_THRESHOLD = 200


def _string_char_count(obj: Any) -> int:
    if isinstance(obj, str):
        return len(obj)
    if isinstance(obj, dict):
        return sum(_string_char_count(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_string_char_count(v) for v in obj)
    return 0


def _top_level_field_counts(merged: dict[str, Any]) -> tuple[int, int]:
    primitive = 0
    structured = 0
    for v in merged.values():
        if isinstance(v, (dict, list)):
            structured += 1
        else:
            primitive += 1
    return primitive, structured


def _classify(merged: dict[str, Any]) -> str:
    prim, struct = _top_level_field_counts(merged)
    text_chars = _string_char_count(merged)
    if struct > 0 and prim > 0:
        return "mixed"
    if struct > 0:
        return "structured"
    if text_chars < _SHORT_TEXT_CHAR_THRESHOLD:
        return "short_text"
    return "long_text"


def prompt_matrix_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """
    Advise-only matrix snapshot of ``ctx.merged_input``.

    ``params`` and ``run_result`` are ignored (B1); no engine, policy, or run mutation.
    """
    del params, run_result
    merged = ctx.merged_input if isinstance(ctx.merged_input, dict) else {}
    merged = dict(merged)

    key_count = len(merged)
    canonical = json.dumps(merged, sort_keys=True, default=str, ensure_ascii=False)
    primitive_fields, structured_fields = _top_level_field_counts(merged)
    classification = _classify(merged)

    return {
        "schema_version": "1.0",
        "payload": {
            "input_overview": {
                "key_count": key_count,
                "canonical_json_length": len(canonical),
                "top_level_primitive_fields": primitive_fields,
                "top_level_structured_fields": structured_fields,
            },
            "classification": classification,
            "stats": {
                "total_string_characters": _string_char_count(merged),
                "short_text_threshold": _SHORT_TEXT_CHAR_THRESHOLD,
            },
        },
        "provenance": {
            "skill_id": "prompt_matrix",
            "mode": "advise",
        },
    }
