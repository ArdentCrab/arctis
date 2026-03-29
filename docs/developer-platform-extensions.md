# Developer guide: platform extensions (ownership, I/O, audit, prompt matrix)

This document summarizes control-plane concepts added for multi-tenant ownership, persisted run text, unified audit timelines, and prompt matrices.

## Ownership model

- **Workflows** carry a required logical `owner_user_id` (UUID). There is no `users` table yet; the UUID is an application-level identifier.
- **Runs** store `workflow_owner_user_id` (defaults to `SYSTEM_USER_ID` for direct pipeline runs) and `executed_by_user_id` (defaults to the authenticated API key row id from middleware).
- **Fallback user**: `arctis.constants.SYSTEM_USER_ID` is used for legacy rows and non-interactive paths.

## Sanitization pipeline

- Module: `arctis.sanitization` — strips HTML tags, masks emails and phone-like sequences, normalizes whitespace; `canonical_json_dumps` / `sanitize_structured_for_storage` keep persisted JSON deterministic and governance-safe.
- **Engine** persistence: `RunInput.raw_input` is canonical JSON of the request payload; `sanitized_input` is `sanitize_text` of that string. After outputs exist, `RunInput.effective_input` is updated to **structured** storage redaction (`sanitize_structured_for_storage` of the in-memory workflow payload). Execution still uses the unsanitized in-process payload unless a step applies its own policy.
- **Snapshot replay (HTTP):** `Engine.replay` is called with `persist_control_plane_io=False`; `copy_run_io_for_replay` copies the source run’s `RunInput`/`RunOutput` onto the new run when present (verbatim audit parity), otherwise falls back to the same persist helpers as a live run.

## RunInputs / RunOutputs

- ORM: `RunInput`, `RunOutput` in `arctis.db.models` (one row per run, FK to `runs.id`).
- Populated from `Engine.run` when the HTTP layer pre-creates a `Run` and passes the UUID into the engine.

## ReviewerDecision

- Table `reviewer_decisions`: `run_id` (FK), `reviewer_id`, `decision`, optional `comment`, `created_at`.
- Created from `/review/{task_id}/approve` and `/reject` when the review task’s `run_id` parses as a UUID and a matching `Run` row exists.

## AuditEvent schema

- Table `audit_events`: `run_id`, `event_type`, `payload` (JSON), `timestamp`, optional `actor_user_id`.
- Written when audit trace rows are persisted with `control_plane_run_uuid` in `persist_audit_rows_from_trace`, and for reviewer decisions from the review API.
- Reviewer task detail (`/reviewer/task/{id}`) returns `audit_timeline` sorted by `timestamp`, `id`.

## PromptMatrix

- Table `prompt_matrices`: `owner_user_id`, `prompt_a`, `prompt_b`, `versions` (JSON array history).
- Routes under `/prompt-matrix`: `POST /compare`, `GET /{id}`, `POST /{id}/version`.

## Cost breakdown

- `RunResult.cost_breakdown` uses `schema_version: 1` with `total_cost` and `step_costs_total` (spine for aggregations) plus legacy `steps` and numeric `step_costs`, plus `reviewer_costs`, `routing_costs`, `prompt_costs` (attribution buckets; often zero except simulated step totals).
- `GET /costs/report` fills `cost_breakdown_totals`: legacy runs contribute to `step_costs`; `schema_version` **1** runs also mirror the same per-run amount into `total_cost` and `step_costs_total` (do not sum those three keys together — they repeat the same step total for different readers). Attribution keys `reviewer_costs`, `routing_costs`, `prompt_costs` are summed separately.

## Run identity (`execution_summary.run_identity`)

- `execution_mode`: `"live"` for normal pipeline runs, `"replay"` for `POST /snapshots/{id}/replay`.
- `control_plane_run_id`: UUID string of the persisted run when the engine stamped it on `RunResult`.
- `replay_source_run_id`: set only on replay; UUID string of the run that produced the snapshot.
