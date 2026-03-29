# Engine-ready checklist (control plane)

Use this as a quick gate before treating a deployment as audit- and ops-complete.

- [ ] **Run identity:** Every successful control-plane run has `Run.id` aligned with `RunResult.control_plane_run_id` and `execution_summary.run_identity.control_plane_run_id` (when stamped).
- [ ] **Ownership:** `workflow_owner_user_id` and `executed_by_user_id` are set consistently on `Run` for workflow vs direct pipeline execution.
- [ ] **I/O persistence:** Live runs have `RunInput` + `RunOutput` after success; replays clone source I/O or fall back to the same persist path as live runs.
- [ ] **Sanitization:** `raw_input` / `sanitized_input` / `effective_input` follow `arctis.sanitization` (canonical JSON + structured storage for effective input after execution).
- [ ] **Determinism:** Persisted JSON uses `canonical_json_dumps`; replay output matches snapshot semantics documented in `developer-platform-extensions.md`.
- [ ] **Costs:** `cost_breakdown.schema_version == 1` with `total_cost` / `step_costs_total`; cost report aggregates new keys without double-counting legacy-only runs.
- [ ] **Audit:** Trace rows persist to `AuditEvent` when `audit_store=db` on live runs; reviewer actions emit decisions + audit entries as documented.
