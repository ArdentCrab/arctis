"""Customer-facing workflow product extraction (Customer Output v1).

``result`` is defined as the step output of the **last topological sink** node
(see :func:`last_topological_sink_name`).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from arctis.compiler import IRPipeline

CUSTOMER_OUTPUT_SCHEMA_VERSION = "1"

# Dict keys removed at any depth under ``result`` / ``fields`` (Customer Output v1 § Forbidden content).
_GOVERNANCE_OBJECT_KEYS: frozenset[str] = frozenset(
    {
        "audit_events",
        "audit_report",
        "audit_timeline",
        "control_plane_run_id",
        "cost_breakdown",
        "effective_input",
        "effective_policy",
        "effects",
        "engine_run_id",
        "engine_snapshot_id",
        "execution_trace",
        "executed_by_user_id",
        "governance_meta",
        "policy_enrichment",
        "raw_input",
        "raw_output",
        "review_queue",
        "review_task",
        "reviewer_decision",
        "run_identity",
        "run_id",
        "sanitized_input",
        "sanitized_input_snapshot",
        "snapshot_id",
        "step_costs",
        "tenant_id",
        "total_cost",
        "workflow_owner_user_id",
    }
)

__all__ = [
    "CUSTOMER_OUTPUT_SCHEMA_VERSION",
    "topological_order_deterministic",
    "last_topological_sink_name",
    "final_workflow_result_from_step_outputs",
    "strip_governance_from_customer_value",
    "build_customer_output_v1",
    "dumps_customer_output_v1",
]


def topological_order_deterministic(ir: IRPipeline) -> list[str]:
    """
    Kahn topological sort with lexicographic tie-breaking (always dequeue the
    smallest ready node name). Raises ``ValueError`` if the subgraph contains a cycle.
    """
    nodes = ir.nodes
    if not nodes:
        return []

    in_degree: dict[str, int] = {n: 0 for n in nodes}
    for u in nodes:
        for v in nodes[u].next:
            if v in in_degree:
                in_degree[v] += 1

    ready = sorted(n for n in nodes if in_degree[n] == 0)
    order: list[str] = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        for v in sorted(nodes[u].next):
            if v not in in_degree:
                continue
            in_degree[v] -= 1
            if in_degree[v] == 0:
                ready.append(v)
        ready.sort()

    if len(order) != len(nodes):
        raise ValueError("IR graph has a cycle or invalid edges; cannot topologically order")
    return order


def last_topological_sink_name(ir: IRPipeline) -> str | None:
    """
    **Sink** = node in ``ir.nodes`` with an empty ``next`` list (after IR normalization).

    Among all sinks, return the one that appears **last** in
    :func:`topological_order_deterministic`. If there are no nodes, return ``None``.
    """
    nodes = ir.nodes
    if not nodes:
        return None

    sinks = {n for n in nodes if not nodes[n].next}
    if not sinks:
        return None

    order = topological_order_deterministic(ir)
    for name in reversed(order):
        if name in sinks:
            return name
    return None


def final_workflow_result_from_step_outputs(
    ir: IRPipeline,
    step_outputs: Mapping[str, Any],
) -> Any:
    """
    Map engine ``output`` (step name → value) to Customer Output ``result``:
    value at :func:`last_topological_sink_name`, or ``None`` if unknown / missing.
    """
    sink = last_topological_sink_name(ir)
    if sink is None:
        return None
    if sink not in step_outputs:
        return None
    return step_outputs[sink]


def strip_governance_from_customer_value(value: Any) -> Any:
    """
    Recursively drop governance / audit / identity keys from JSON-like structures
    (dicts and lists). Primitives are returned unchanged.
    """
    if isinstance(value, dict):
        return {
            k: strip_governance_from_customer_value(v)
            for k, v in value.items()
            if k not in _GOVERNANCE_OBJECT_KEYS
        }
    if isinstance(value, list):
        return [strip_governance_from_customer_value(x) for x in value]
    if isinstance(value, tuple):
        return [strip_governance_from_customer_value(x) for x in value]
    return value


def build_customer_output_v1(
    ir: IRPipeline,
    step_outputs: Mapping[str, Any],
    *,
    confidence: float | None = None,
    score: float | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Assemble ``customer_output_v1`` (closed key set per spec). Optional facets are omitted
    when ``None`` so the JSON shape stays minimal.
    """
    raw = final_workflow_result_from_step_outputs(ir, step_outputs)
    doc: dict[str, Any] = {
        "schema_version": CUSTOMER_OUTPUT_SCHEMA_VERSION,
        "result": strip_governance_from_customer_value(raw),
    }
    if confidence is not None:
        doc["confidence"] = confidence
    if score is not None:
        doc["score"] = score
    if fields is not None:
        cleaned = strip_governance_from_customer_value(fields)
        if isinstance(cleaned, dict) and cleaned:
            doc["fields"] = cleaned
    return doc


def dumps_customer_output_v1(doc: dict[str, Any]) -> str:
    """UTF-8 JSON with sorted keys at every object level (canonical wire form)."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
