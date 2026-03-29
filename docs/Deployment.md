# Deployment notes

## Infrastructure (staging / production) — A1.1

Production- und **staging**-ähnliche Umgebungen nutzen dieselben **Variablennamen**; Werte (URL, Origins, Secrets) werden pro Umgebung gesetzt. Die **reale** Staging-Laufzeit (Cluster, VM, PaaS) liegt außerhalb dieses Repos — hier die verbindliche Checkliste für Betrieb und Review.

### Erforderliche Konfiguration

| Variable | Rolle |
|----------|--------|
| `ENV` | `prod` für produktionsnahes Verhalten (u. a. OpenAPI-Defaults, synthetisches Rate-Limit ohne DB-Eintrag). Staging nutzt typischerweise ebenfalls `prod`, sofern ihr kein separates `staging`-Label im Code führt. |
| `DATABASE_URL` | SQLAlchemy-URL (empfohlen: Postgres, z. B. `postgresql+psycopg://…`). Ohne erreichbare DB schlagen echte Auth-Pfade fehl ([`security_production.md`](security_production.md)). |
| `ALLOWED_ORIGINS` | Komma-separierte CORS-Origins der **echten** Frontends (HTTPS); in Prod **kein** Wildcard über `ARCTIS_CORS_WILDCARD_DEV`. |
| `ARCTIS_AUDIT_STORE` | `jsonl` \| `db` \| `none` — Backend für Audit-Abfragen/Export ([`DR.md`](DR.md)). |
| `ARCTIS_AUDIT_JSONL_DIR` | Pflicht, wenn `ARCTIS_AUDIT_STORE=jsonl`: beschreibbarer Verzeichnispfad für JSONL-Dateien (Container: Volume mount). Bei `db` bzw. `none` nicht nötig. |

### Migrationen (vor Traffic)

```bash
export DATABASE_URL="postgresql+psycopg://..."
alembic upgrade head
```

Immer **vor** dem ersten Request mit Kundendaten ausführen; bei Deploys idempotent wiederholen. Kein Verlass auf `create_all()` in Prod ([`security_production.md`](security_production.md)).

### Kurzablauf

1. Datenbank bereitstellen, `DATABASE_URL` setzen.  
2. `alembic upgrade head`.  
3. `ENV=prod`, `ALLOWED_ORIGINS`, Audit-Variablen und übrige Secrets setzen ([`DEPLOYMENT_CHECKLIST.md`](../DEPLOYMENT_CHECKLIST.md)).  
4. API starten (`uvicorn` / Container).  

Details zu weiteren Prod-Flags: [`security_production.md`](security_production.md). Recovery: [`DR.md`](DR.md).

---

## Secrets (A1.2)

**Policy:** Im Repository, in Issues und in Doku nur **Namen** von Umgebungsvariablen verwenden. **Werte** liegen im **Secret Store** der Laufzeit (z. B. Kubernetes Secrets, AWS Secrets Manager, Vault, verschlüsselte CI-Environments) und werden zur Startzeit injiziert. Keine Klartext-Credentials in Git — siehe [`.gitleaks.toml`](../.gitleaks.toml) und [`docs/security_production.md`](security_production.md).

### Kernvariablen (Namen)

| Name | Zweck |
|------|--------|
| `ARCTIS_ENCRYPTION_KEY` | Fernet-Key für tenantgebundene Verschlüsselung (u. a. gespeicherte LLM-Keys); muss ein gültiger Fernet-String sein. |
| `CONTROL_PLANE_API_KEY` | API-Key für Smoke-/Launch-Szenarien und Lasttests (u. a. [`launch_check`](../arctis/scripts/launch_check.py)). |
| `CONTROL_PLANE_URL` | Öffentliche oder interne **Basis-URL** der Arctis-API (kein Secret; gehört zur gleichen Konfigurationssession wie der Key). |
| `SENTRY_DSN` | Error-Tracking; der DSN ist **sensibel** — wie ein Secret behandeln. |
| `STRIPE_SECRET_KEY` | Billing API (Stripe). |
| `STRIPE_WEBHOOK_SECRET` | Signaturprüfung für Stripe-Webhooks. |

### LLM-Provider (optional / betriebsspezifisch)

| Name | Hinweis |
|------|--------|
| `OPENAI_API_KEY` | Default-LLM über [`Settings`](../arctis/config.py); viele Deployments speichern Modell-Keys **pro Tenant** in der Datenbank statt global. |

Weitere Provider-Umgebungen (z. B. `OPENAI_BASE_URL`, `OLLAMA_*`) sind Konfiguration, meist ohne gleiches Geheimnisniveau wie Stripe — trotzdem nicht unkontrolliert leaken.

### Identity (Vorbereitung A1.3)

`python -m arctis.scripts.launch_check` verlangt **entweder** das **Auth0**-Set (`AUTH0_SECRET`, `AUTH0_BASE_URL`, `AUTH0_ISSUER_BASE_URL`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`) **oder** **Supabase** (`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) — exakt wie in [`launch_check.py`](../arctis/scripts/launch_check.py) (`AUTH0_REQUIRED` / `SUPABASE_REQUIRED`).

### Launch-Readiness

Vollständige Liste der von `launch_check` geprüften Variablen: Docstring in [`arctis/scripts/launch_check.py`](../arctis/scripts/launch_check.py).

---

## Authentication & identity (A1.3)

API-Keys, Auth0/Supabase, Callbacks, Tenant-Modell und Abgrenzung JWT: **[Authentication.md](Authentication.md)**.

---

## Observability (A1.4)

Sentry, Prometheus-Scrape (`/metrics/prometheus`), Grafana außerhalb des Repos, Alerts: **[Observability.md](Observability.md)**.

---

## Disaster recovery & backup (A1.5)

Backup-Jobs, Restore-Ablauf, DR-Drill, RPO/RTO: **[DR.md](DR.md)** — ergänzt durch [`DEPLOYMENT_CHECKLIST.md`](../DEPLOYMENT_CHECKLIST.md) (Abschnitt DR & Backup).

---

## Launch gates (A1.6)

`launch_check`, Playwright, Locust, Statuspage/Support: **[Launch_readiness.md](Launch_readiness.md)**.

---

## API base URL (OpenAPI servers)

- **Local:** `http://127.0.0.1:8000` (typical `uvicorn` default).
- **Production:** set your public HTTPS base URL (e.g. `https://api.yourcompany.com`). The checked-in `openapi.json` uses `https://api.example.com` as a placeholder—replace it when publishing client SDKs or external docs.

Interactive schema: `GET /openapi.json` on a running instance must match the repository `openapi.json` after `python scripts/generate_openapi.py`.

## Container image

Build and run (defaults: non-root user, `ENV=prod`, SQLite under `/home/arctis/data`; override `DATABASE_URL` for Postgres):

```bash
docker build -t arctis:latest .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+psycopg://user:pass@host:5432/arctis" \
  -e ENV=prod \
  arctis:latest
```

Apply migrations against that database before traffic: `alembic upgrade head` (see Alembic in this repo). Do not use `create_all()` in production.

## Disaster recovery

See **[DR.md](DR.md)** (backups, restore order, DR test checklist, RPO/RTO).

## Database schema (production)

Production and staging databases **must** be migrated with Alembic:

```bash
export DATABASE_URL="postgresql+psycopg://..."
alembic upgrade head
```

Do **not** rely on `Base.metadata.create_all()` to provision the main application schema in production. That path is reserved for tests and small in-memory helpers (for example policy seeding in development scripts).

After deploy, the schema should match the SQLAlchemy models under `arctis/db/models.py` and related `Base` metadata (policy, routing, audit tables), as enforced by the migration chain ending at the current `head` revision.
