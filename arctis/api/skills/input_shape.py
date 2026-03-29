"""Customer skill ``input_shape`` — advise-only structural analysis of merged input (B3)."""

from __future__ import annotations

from typing import Any

from arctis.api.skills.registry import SkillContext


def _primitive_shape(value: Any, depth: int) -> dict[str, Any] | None:
    if value is None:
        return {"type": "null", "depth": depth}
    if isinstance(value, bool):
        return {"type": "boolean", "depth": depth}
    if isinstance(value, int):
        return {"type": "number", "depth": depth}
    if isinstance(value, float):
        return {"type": "number", "depth": depth}
    if isinstance(value, str):
        return {"type": "string", "depth": depth}
    return None


def _strip_depth(shape: dict[str, Any]) -> dict[str, Any]:
    """Shape equality for array homogeneity (ignore depth)."""
    out: dict[str, Any] = {k: v for k, v in shape.items() if k != "depth"}
    ch = out.get("children")
    if isinstance(ch, dict):
        out["children"] = {k: _strip_depth(ch[k]) for k in sorted(ch.keys(), key=str)}
    elif isinstance(ch, list):
        out["children"] = [_strip_depth(c) for c in ch]
    return out


def _array_form(children_shapes: list[dict[str, Any]]) -> str:
    if len(children_shapes) == 0:
        return "empty"
    first = _strip_depth(children_shapes[0])
    for s in children_shapes[1:]:
        if _strip_depth(s) != first:
            return "heterogeneous"
    return "homogeneous"


def _build_shape(value: Any, depth: int) -> dict[str, Any]:
    prim = _primitive_shape(value, depth)
    if prim is not None:
        return prim

    if isinstance(value, list):
        child_shapes = [_build_shape(item, depth + 1) for item in value]
        return {
            "type": "array",
            "depth": depth,
            "array_form": _array_form(child_shapes),
            "children": child_shapes,
        }

    if isinstance(value, dict):
        keys = sorted(value.keys(), key=str)
        children = {k: _build_shape(value[k], depth + 1) for k in keys}
        return {
            "type": "object",
            "depth": depth,
            "key_count": len(keys),
            "children": children,
        }

    return {"type": "string", "depth": depth, "note": type(value).__name__}


def _max_depth_in_shape(shape: dict[str, Any]) -> int:
    d = int(shape.get("depth", 0))
    ch = shape.get("children")
    if isinstance(ch, dict):
        return max([d] + [_max_depth_in_shape(ch[k]) for k in ch], default=d)
    if isinstance(ch, list):
        return max([d] + [_max_depth_in_shape(c) for c in ch], default=d)
    return d


def _count_nodes(shape: dict[str, Any]) -> int:
    t = shape.get("type")
    if t in ("null", "boolean", "number", "string"):
        return 1
    ch = shape.get("children")
    if isinstance(ch, dict):
        return 1 + sum(_count_nodes(ch[k]) for k in ch)
    if isinstance(ch, list):
        return 1 + sum(_count_nodes(c) for c in ch)
    return 1


def _count_type(shape: dict[str, Any], type_name: str) -> int:
    n = 1 if shape.get("type") == type_name else 0
    ch = shape.get("children")
    if isinstance(ch, dict):
        return n + sum(_count_type(ch[k], type_name) for k in ch)
    if isinstance(ch, list):
        return n + sum(_count_type(c, type_name) for c in ch)
    return n


def input_shape_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """
    Advise-only recursive shape tree for ``ctx.merged_input``.

    ``params`` and ``run_result`` are ignored (B3). No engine or policy.
    """
    del params, run_result
    raw = ctx.merged_input
    if not isinstance(raw, dict):
        root = {"value": raw}
    else:
        root = dict(raw)

    shape = _build_shape(root, 0)
    summary = {
        "max_depth": _max_depth_in_shape(shape),
        "total_fields": _count_nodes(shape),
        "array_count": _count_type(shape, "array"),
        "object_count": _count_type(shape, "object"),
    }

    return {
        "schema_version": "1.0",
        "payload": {
            "shape": shape,
            "summary": summary,
        },
        "provenance": {
            "skill_id": "input_shape",
            "mode": "advise",
        },
    }
