# Customer Output — Specification v1

**Status:** normative for `customer_output_v1`  
**Audience:** product, API consumers, implementers of the transformation layer

## Purpose

Customer Output is the **only** JSON payload returned to end-users who must not see governance, audit, billing, or operational internals. It is derived from engine execution **after** persistence of full run data on the server.

## Design principles

1. **Minimal** — smallest surface that still conveys the workflow product.
2. **Stable** — additive changes ship as new schema versions (`v2`, …); `v1` fields remain backward compatible where possible.
3. **Non-leaking** — no identifiers or metadata that tie the response to internal control-plane state, people, or enforcement mechanics.
4. **Canonical serialization** — one deterministic JSON encoding (see § Serialization).

## Root object

Top-level JSON object with **exactly** the keys defined in § Allowed keys. No other keys are permitted in `customer_output_v1`.

### Required

| Field             | Type   | Description |
|-------------------|--------|-------------|
| `schema_version`  | string | Literal `"1"` for this specification. |

### Workflow product

| Field    | Type | Description |
|----------|------|-------------|
| `result` | any JSON value | The **final workflow result** — the end-user-visible outcome of the workflow. May be `null` if the workflow defines no product or the sink step did not produce a value. Shape is workflow-specific (object, array, string, number, boolean). Must not embed governance or audit payloads (see § Forbidden content). |

#### Mapping from engine step outputs

`result` is derived **deterministically** from the engine’s per-step output map (node name → JSON value):

1. Consider only the **structural** `IRPipeline` used for the run (normalized graph: edges point only to nodes that exist).
2. A **sink** is any node whose `next` list is empty.
3. Compute a **topological order** of all nodes with **Kahn’s algorithm**, breaking ties by choosing the **lexicographically smallest** node name among nodes with indegree zero at each step.
4. Let **last topological sink** be the sink that appears **last** in that topological order (scan the order from end to start; first hit that is a sink).
5. Set `result` to that node’s value in the step output map. If there is no such node, or the map has no entry for it, `result` is JSON `null`.

This rule is implemented in `arctis.customer_output.final_workflow_result_from_step_outputs`.

### Optional

| Field         | Type   | Description |
|---------------|--------|-------------|
| `confidence`  | number | Optional scalar in **\[0, 1\]** expressing model or system confidence in `result`, if the workflow supplies one. Omit if unknown. |
| `score`       | number | Optional scalar score (workflow-defined scale). Omit if unknown. |
| `fields`      | object | Optional bag of **structured result fields** (string keys, JSON values). Use for labeled facets (e.g. extracted attributes) without overloading `result`. Values must obey § Forbidden content recursively. |

**Note:** `confidence` and `score` may both be omitted, or one or both present, depending on the workflow. They must not duplicate secret or internal metrics (token counts, raw logits, etc.).

## Allowed keys (closed set)

Implementations **must** emit only:

- `schema_version` (required)
- `result` (required; value may be `null`)
- `confidence` (optional)
- `score` (optional)
- `fields` (optional)

## Forbidden content

The entire Customer Output document (including nested values under `result` and `fields`) **must not** contain, at any depth:

- Audit timelines, audit events, or audit reports
- Reviewer tasks, decisions, queues, or human-review state
- Cost, usage, billing, token counts, or pricing breakdowns
- Run identity (run id, engine run id, snapshot id, trace ids)
- Workflow owner, executor, user ids, API key ids, tenant ids
- `sanitized_input`, `effective_input`, `raw_input`, `raw_output`, or equivalent input/output capture fields
- Model internals: prompts, system messages, tool call transcripts, hidden chain-of-thought, raw provider responses not already reduced to the workflow product
- Policy objects, enforcement matrices, routing rules, or sanitizer diagnostics

If the engine would otherwise place such data in the workflow product, the **transformation layer** (Phase 2) must strip or replace it with workflow-safe content before emitting Customer Output.

## Serialization (canonical JSON)

For equality and replay checks, the **on-the-wire** JSON for `customer_output_v1` must be produced as:

- UTF-8 encoding
- Object keys sorted lexicographically at **every** object nesting level
- No insignificant whitespace between tokens (single canonical form)
- Numbers formatted as JSON numbers (no locale-specific formatting)
- No `undefined`; omit optional keys rather than emitting `null` for “not provided” (except `result` itself, which may be JSON `null`)

(Exact implementation helpers belong in Phase 2.)

## Versioning

- This document defines **Customer Output v1**.
- The `schema_version` field is the **protocol version** carried in every payload.
- Future breaking or large shape changes require a new spec (`customer-output-v2.md`) and a new `schema_version` literal.

## JSON Schema

Machine-readable schema: [`schemas/customer_output_v1.schema.json`](schemas/customer_output_v1.schema.json).
