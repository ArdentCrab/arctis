# Disaster recovery (Arctis)

Operational guide for restoring Arctis after data loss, region failure, or corruption. Keep runbooks and credentials outside this repository in your secure ops store.

## Components

| Component | Role | Notes |
|-----------|------|--------|
| **PostgreSQL** | Single source of truth for control-plane data (tenants, API keys, pipelines, workflows, runs, budgets, idempotency keys, audit timeline rows, etc.) | Required in production. |
| **Audit store** | Query/export path for compliance (`ARCTIS_AUDIT_STORE`: `jsonl`, `db`, or `none`) | JSONL on disk and/or `audit_records` / related DB tables. |
| **Snapshot store** | Engine snapshots linked to runs (`snapshots` table + blob JSON) | Backed up with Postgres when using the DB backend. |
| **Application** | Stateless containers (Docker image); config via env | No `create_all` in prod; schema via **Alembic** only. |

## Backup strategy

1. **PostgreSQL — logical (daily)**  
   - `pg_dump` (custom format `-Fc`) or managed-provider automated backup.  
   - Retain ≥ **7** daily copies; align retention with legal/compliance.

2. **PostgreSQL — physical (weekly)**  
   - Base backup + WAL archiving (e.g. `pg_basebackup`, cloud PITR).  
   - Enables faster restore and point-in-time recovery when configured.

3. **Audit JSONL (if used)**  
   - Replicate directory (`ARCTIS_AUDIT_JSONL_DIR`) with **rsync**, **rclone**, or object storage with **versioning**.  
   - Treat files as immutable append-only where possible.

4. **Secrets**  
   - API hash seeds, `ARCTIS_ENCRYPTION_KEY` (Fernet), DB URLs, Sentry DSN: store in a **secret manager**, not only in backups.

## Restore procedure

1. **Provision** a new Postgres instance (or empty database) and network access for Arctis.
2. **Restore data**  
   - From logical backup: `pg_restore` (or `psql` for plain SQL) into the new database.  
   - From physical/PITR: follow your provider’s restore workflow to the target time.
3. **Schema alignment**  
   - Deploy the **same application version** (image tag) you intend to run.  
   - Run **`alembic upgrade head`** against `DATABASE_URL` (idempotent if backup already matched that revision; required if restoring an older dump onto a newer empty cluster).
4. **Configure** environment variables (`DATABASE_URL`, `ENV=prod`, encryption key, audit paths, etc.) to match the restored environment.
5. **Start** Arctis (e.g. `uvicorn` via Docker `CMD` as in the project `Dockerfile`).  
6. **Restore audit JSONL** (if applicable) to the configured directory before relying on `/audit/export`.

## Verification (DR test)

Run a **DR drill at least once per release** (or quarterly minimum):

- [ ] `GET /health` returns **200**.
- [ ] API key auth: existing tenant key still works (or re-issue keys if hashes/secrets rotated).
- [ ] `GET /pipelines`, `GET /workflows` return expected tenant data.
- [ ] `GET /runs/{id}` and `GET /runs/{id}/evidence` return consistent run + evidence for a known run id.
- [ ] Optional: run one **read-only** smoke test pipeline in a non-prod clone of the restore.

Document date, scope, gaps, and follow-up tickets.

## Objectives (configurable)

| Metric | Default target | Depends on |
|--------|----------------|------------|
| **RPO** | ≤ **24 h** | Backup frequency (increase frequency to tighten RPO). |
| **RTO** | ≤ **1 h** | DB size, restore method (logical vs physical), automation maturity. |

Tighten RPO/RTO by shortening backup intervals, using PITR, and automating restore playbooks.

## Contacts

Define on-call rotation, escalation, and communication templates in your internal wiki; link from here.
