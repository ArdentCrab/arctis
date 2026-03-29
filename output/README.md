# Arctis golden outputs

This directory holds **expected (golden) artifacts** for Arctis test tasks. They are the reference the test harness compares against engine results after running the matching `input/<NNN>_*/` bundle under a deterministic mock or recorded runtime.

## Purpose

Golden files make **regressions visible**: any change to outputs, effects, traces, costs, or violation payloads must be intentional and reviewed. They are not live snapshots from production; they are curated fixtures aligned with Engine Spec v1.5 and Test Suite v1.1.

## Determinism

For a fixed input folder and engine configuration:

- **Success-path tasks** (`expected_output.json`, `expected_snapshot.json`, `expected_effects.json`, `expected_costs.json`, traces, audit JSON) must be **bit-for-bit or canonically equal** (e.g. normalized JSON) across repeated runs on the same code version.
- **Violation tasks** (`expected_violation.json`) describe the **expected error class, code, or message shape** so `pytest.raises` and structured error payloads stay stable.

If two runs differ without input or engine changes, that is a determinism bug.

## How `expected_*` files are used

| Pattern | Typical use |
|---------|-------------|
| `expected_output.json` | Final pipeline output / result object (serialized). |
| `expected_snapshot.json` | Snapshot bundle or replay handle shape after a full run. |
| `expected_effects.json` | List of effects (e.g. writes, simulated vs real) after run or dry-run. |
| `expected_audit_report.json` | Full or partial audit document (§9.1 fields). |
| `expected_trace.json` / `expected_observability.json` | DAG / step-level observability payload (§7). |
| `expected_violation.json` | Expected compliance/security/saga error metadata. |
| `expected_manual_recovery.json` | Atomic saga terminal state when compensation fails. |
| `expected_costs.json` | Total cost and per-step or breakdown structure for pricing tests. |

Tests load the matching `output/<NNN>_*/` file and assert equality (or structured containment) against `engine.run` results, audit builders, and trace APIs.

## CRM sync golden files (`021_crm_sync`)

- **`expected_output.json`** — canonical `SyncResult` (or equivalent) after CSV → AI enrich → CRM upsert.
- **`expected_audit_report.json`** — audit report matching §9.1 for that run (steps, effects, costs, errors/compensations slots).
- **`expected_observability.json`** — explorer trace with `parse_csv`, `enrich_contacts`, `upsert_crm` (and graph/DAG) per §7.

Together with `input/021_crm_sync/*`, these define the **end-to-end contract** for the reference CRM pipeline.
