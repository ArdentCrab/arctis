# Arctis test task inputs

This directory holds **deterministic, versioned inputs** for Arctis test tasks. Each task folder is a self-contained bundle the harness loads to configure tenant context, pipelines, modules, and simulated failures—without depending on random network calls or mutable external systems.

## Numbering (001–021)

Folders use a **fixed three-digit prefix** so tasks sort lexically and map cleanly to the suite:

| ID | Folder | Maps to |
|----|--------|---------|
| 001 | `001_deterministic_pipeline` | Determinism — repeated full runs |
| 002 | `002_flaky_pipeline` | Determinism — retry / transient failures |
| 003 | `003_parallel_pipeline` | Determinism — parallel DAG, stable ordering |
| 004 | `004_snapshot_replay` | Determinism — snapshot replay id |
| 005 | `005_ai_deterministic` | Determinism — `ai.transform` with temperature 0 |
| 006 | `006_security_ai_boundaries` | Security — AI data boundary, secrets, forbidden fields |
| 007 | `007_tenant_isolation` | Security — cross-tenant snapshot/effect access |
| 008 | `008_effect_whitelist` | Security — versioned / whitelisted effects |
| 009 | `009_idempotency` | Security — idempotent writes under retry |
| 010 | `010_module_tampering` | Security — signed module bytes (original vs tampered) |
| 011 | `011_audit` | Compliance — audit report generation |
| 012 | `012_dry_run` | Compliance — dry-run, no real effects |
| 013 | `013_marketplace` | Compliance — signed vs unsigned module artifacts |
| 014 | `014_data_residency` | Compliance — EU/US region constraints |
| 015 | `015_observability` | Compliance — Pipeline Explorer trace shape |
| 016 | `016_saga_atomic` | Saga — atomic compensation / manual recovery |
| 017 | `017_saga_best_effort` | Saga — best-effort compensation, warnings |
| 018 | `018_budget_limit` | Performance — `budget_limit` enforcement |
| 019 | `019_resource_limits` | Performance — CPU / memory / time caps |
| 020 | `020_cost_determinism` | Performance — reproducible cost breakdown |
| 021 | `021_crm_sync` | E2E — canonical CRM sync pipeline |

## CRM sync task (`021_crm_sync`)

- **`contacts.csv`** — deterministic CSV attachment fed as pipeline input (parse → enrich → upsert path).
- **`enrichment_prompt.txt`** — fixed natural-language or template text associated with the enrich step (for audits and prompt redaction checks); must stay stable across runs.
- **`forbidden_secrets.json`** — literal strings or patterns that must **never** appear in AI prompts or model-visible payloads (boundary tests compare engine output against this list).

Fill each placeholder file with concrete JSON/CSV/text/binary content when you lock the golden harness; until then these paths only reserve the contract.
