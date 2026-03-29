# Arctis + Ghost — Produktions-Security (Referenz)

Diese Seite bündelt **Flags, Verhalten und Betrieb** für die öffentliche API (`arctis.app:create_app`) und die Ghost-CLI. Sie ergänzt `arctis_engine_and_security_spec_v1.5.md`.

## Ghost — Schnelleinstieg (Sicherheit)

| Thema | Dokument |
|--------|----------|
| CLI-Verhalten, Pfade, Limits, `--dry-run` | [ghost_cli_reference.md](ghost_cli_reference.md) |
| **Lifecycle-Hooks** (P14): Subprocess, Timeout, stdin-JSON, `--no-hooks` | [ghost_hooks_p14.md](ghost_hooks_p14.md) |
| Staging-E2E-Checkliste (ohne Secrets im Repo) | [ghost_staging_e2e.md](ghost_staging_e2e.md) |
| Publish-/Paket-Strategie (Monorepo vs. Split) | [arctis_package_strategy.md](arctis_package_strategy.md) |

## Offizieller API-Einstieg

```bash
uvicorn arctis.app:create_app --factory --host 0.0.0.0 --port 8000
```

Das Modul `main.py` ist **Legacy**; mit `ENV=prod` wird sein Import **hart abgelehnt**. Nicht als Produktions-Entry-Point verwenden.

## Umgebungsvariablen (Kurzüberblick)

| Variable | Kontext | Bedeutung |
|----------|---------|-----------|
| `ENV` | API | `dev` \| `prod` — steuert u. a. OpenAPI-Default, synthetische Rate-Limits. |
| `ALLOWED_ORIGINS` | API | Komma-separierte CORS-Origins (Prod: nur explizite Einträge). |
| `ARCTIS_CORS_WILDCARD_DEV` | API | Nur mit `ENV=dev`: CORS `*` (ohne Credentials). **Nie in Prod.** |
| `ARCTIS_EXPOSE_OPENAPI` | API | `true`/`false`: `/docs`, `/redoc`, `/openapi.json`. Default: in Prod aus, in Dev an. |
| `ARCTIS_UNSAFE_ALLOW_DBLESS_DEV_AUTH` | API | Nur `ENV=dev`: beliebiger `X-API-Key` ohne DB → Dev-Tenant. **Nie in Prod.** |
| `ARCTIS_DBLESS_DEV_TENANT_ID` | API | UUID für den unsicheren DB-less-Modus (nur mit Flag). |
| `ARCTIS_DEFAULT_RATE_LIMIT_PER_MINUTE` | API | Synthetisches Limit/Minute, wenn **kein** DB-Rate-Limit-Eintrag existiert; `0` = aus. Unset: Prod **120**, Dev kein synthetisches Cap. |
| `ARCTIS_GOVERNANCE_CROSS_TENANT` | API | Erlaubt Cross-Tenant-Reads in **Metrics** und **Audit-Export** nur zusammen mit **`system_admin`-Scope** auf dem API-Key (siehe unten). |
| `DATABASE_URL` | API | Pflicht für echte Auth; ohne Session → `X-API-Key` führt zu **503** (außer Dev+Unsafe-Flag). |
| `SENTRY_DSN` | API | Optional; sensible Header werden im `before_send`-Hook redigiert. |

## OpenAPI / Docs

- **Prod (Default):** Doc-Routen sind deaktiviert; direkte Requests auf `/docs`, `/redoc`, `/openapi.json` liefern **404** (kein 401-Hinweis).
- **Hinweis:** Eine exponierte OpenAPI-Datei ist eine **vollständige Angriffsflächen-Karte** — nur hinter VPN/Auth oder mit bewusstem `ARCTIS_EXPOSE_OPENAPI=true` freigeben.

## Rate-Limits und Missbrauch

- DB-gestützte Limits: `tenant_rate_limits`, `api_key_rate_limits` (siehe Modelle).
- **Fallback:** siehe `ARCTIS_DEFAULT_RATE_LIMIT_PER_MINUTE` und `Settings.synthetic_rate_limit_per_minute()`.
- **Alerts (operativ):** In Prometheus/Alertmanager auf erhöhte 429-Rate und Anomalien an der Execute-Route achten (Konkrete Regeln: eure Infra).

## Budget (LLM-Kosten)

- API-seitige Budget-Felder (Tenant/Key/Pipeline/Workflow) — siehe Costs/Budget-Routen und Engine-Integration.
- **Alert-Idee:** Budget-Überschreitung / „budget exhausted“ über Metriken oder Anwendungslogs (kein Roh-PII).

## Scopes (API-Keys)

| Scope | Typische Nutzung |
|-------|------------------|
| `tenant_user` | Standard-Kunden-API (Execute, Runs lesen, …). |
| `reviewer` | Review-Workflows, Reviewer-Dashboard. |
| `tenant_admin` | Tenant-Metriken, Audit-Export, Admin-Reads innerhalb des Tenants. |
| `system_admin` | Plattform-Operationen; **erforderlich** für Cross-Tenant-Zugriff wenn `ARCTIS_GOVERNANCE_CROSS_TENANT=true`. |

**Default bei leerem/`NULL` `scopes` in der DB:** nur `tenant_user` — `reviewer` ist **explizit** zu setzen.

**Scope-Änderungen / Audit:** Die Admin-Routen unter ``arctis.api.routes.api_keys`` sind derzeit **Stubs**. Ein **Audit-Log für Scope-Änderungen** ist erst sinnvoll, wenn echtes Key-CRUD existiert; dann Einträge in den Audit-Store (oder dediziertes Admin-Audit) schreiben — siehe Kommentar in ``api_keys.py``.

## Cross-Tenant

- Flag allein reicht **nicht**: Aufrufe mit fremder `tenant_id` erfordern **`system_admin`** + `ARCTIS_GOVERNANCE_CROSS_TENANT=true`.
- Es wird ein **Warning-Log** `cross_tenant_governance_query` geschrieben.

## Ghost-CLI (lokal)

- Pfade für `--input`, `--recipe`, `--merge-json`: **relativ zum Arbeitsverzeichnis**, **keine absoluten Pfade** (Default).
- Größenlimits: JSON-Dateien **1 MiB**, andere CLI-Dateien (Rezept, Text-Input) **5 MiB** — siehe `arctis_ghost.input_limits`.
- `ghost.yaml` mit `api_key`: **Warnung** beim Laden; Secrets liegen **unverschlüsselt** auf der Platte — besser `ARCTIS_API_KEY`.
- State unter `.ghost/state`: auf POSIX **0600** nach Schreiben (best effort).
- `ghost pull-artifacts`: bestehendes `outgoing/<run_id>/` nur mit **`--force`** überschreiben.
- **`ghost run --dry-run`:** kein Netzwerk; nur Sandbox-Validierung und Ausgabe des Execute-Bodies (P10).
- **Lifecycle-Hooks** (`hook_pre_run` / `hook_post_run` / `hook_on_error`): beliebige Prozesse mit Nutzerrechten; nur vertrauenswürdige Skripte; stdin kann sensible `execute_body`-Daten enthalten — Details und Betriebswarnungen: [ghost_hooks_p14.md](ghost_hooks_p14.md).

## Supply-Chain (Lockfile & Vulnerabilities)

- **`requirements-lock.txt`:** Vollständiger, **hash-gepinnter** Freeze für ``pyproject.toml`` mit Extra **`ci`** (``pip-tools`` / ``pip-compile``). Erneuern nach Dependency-Änderungen:
  - Linux/macOS: ``bash scripts/generate_requirements_lock.sh``
  - Windows: ``powershell -File scripts/generate_requirements_lock.ps1``
- CI **``lockfile``-Job:** Führt ``pip-compile`` aus und bricht, wenn sich die Datei vom Repo unterscheidet (Drift-Schutz).
- CI **``pip-audit``:** Läuft gegen **`requirements-lock.txt`** (transitive Pakete).

## SBOM (Enterprise, optional)

- Für Due-Diligence: nach Image-Build z. B. **Syft** auf das gebaute Image anwenden und CycloneDX/SPDX als Artefakt ablegen.
- Beispiel (lokal, nach ``docker build``): ``syft packages <image:tag> -o cyclonedx-json > sbom.json`` — genaue Flags je nach Syft-Version.
- Kein Blocker für Ghost P10–P14; rein release-/compliance-seitig.

## Container & signierte Images (optional)

- Dockerfile: schlankes Base-Image (z. B. ``python:3.11-slim``), Non-Root-User, Multi-Stage wo sinnvoll.
- **Signierung:** Mit **Cosign** / Sigstore das Release-Image signieren und die Signatur in eurer Registry oder im Release-Asset ablegen — Prozess- und Key-Management liegen bei eurer DevOps-Organisation.

## Observability: Grafana / Alerts (reine Ops)

- **Nicht** Teil des Ghost-Clients: Metriken kommen von API/Prometheus (z. B. ``/metrics/prometheus``), Infra und Ingress.
- **Alert-Ideen (Grafana/Alertmanager):** erhöhte 5xx-Rate, Latenz-p95, 429-Rate (Rate-Limit), Budget-Flags aus eurer Cost-Schicht, „DB unhealthy“, optional Sentry-Issue-Spikes.
- Dashboards und Schwellenwerte in eurer Umgebung definieren; keine feste Konfiguration im Repo nötig.

## Log-Rotation & PII (reine Ops)

- Container: Logs nach **stdout/stderr**; Rotation und Retention über Orchestrator (Kubernetes log driver, Docker log opts, Cloud Logging).
- Keine **Roh-Requests**, keine **API-Keys**, keine personenbezogenen Eingaben in App-Logs; strukturierte Felder ohne PII bevorzugen.

## Incident-Runbooks (Kurzfassung)

### API-Key geleakt

1. Key in der DB **deaktivieren** / rotieren; alle Clients informieren.
2. Logs auf Missbrauch (fremde Tenants, ungewöhnliche Routen) prüfen.
3. Root-Cause (Commit, Screenshot, geteiltes Terminal) dokumentieren.

### Tenant falsch konfiguriert

1. `tenant_id`, Workflows, Policies in der Control-Plane prüfen.
2. Test-Execute mit minimalem Body; Budget/Rate-Limits prüfen.

### Budget erschöpft

1. Tenant-/Key-Budgets und tagesbezogene Zähler prüfen.
2. Notfall-Erhöhung nur mit Freigabe; Kostenstelle informieren.

### Cross-Tenant aktiv

1. `ARCTIS_GOVERNANCE_CROSS_TENANT` nur bei Bedarf `true`; Zugriffe auf `system_admin`-Keys beschränken.
2. Logs `cross_tenant_governance_query` auswerten.

### DB ausgefallen / DB-less im Cluster

1. API sollte **503** liefern (kein Dev-Tenant-Fallback in Prod).
2. Alarm, wenn in Prod `SessionLocal`-Fehler oder Health/DB-Checks rot.

### OpenAPI exponiert

1. `ARCTIS_EXPOSE_OPENAPI` prüfen; auf `false` setzen oder Zugriff per Netzwerk einschränken.
2. Pen-Test-Scope anpassen (öffentliche Oberfläche verkleinern).

### Ghost-Artefakte mit sensiblen Daten

1. `outgoing/` und Repos nicht committen; `.gitignore` prüfen.
2. `envelope.json` / `__STATUS.txt`: keine personenbezogenen Freitexte in Branding/Notizen.

## Deployment — Kurz-Checkliste

- [ ] `ENV=prod`, kein `ARCTIS_UNSAFE_*` in Prod.
- [ ] `ALLOWED_ORIGINS` explizit; kein `ARCTIS_CORS_WILDCARD_DEV`.
- [ ] OpenAPI nur bei Bedarf.
- [ ] Postgres/DB URL und Migrationen (`alembic upgrade head`).
- [ ] TLS am Ingress; keine Klartext-Keys in Logs.
- [ ] Sentry DSN ohne PII-Tuning in `before_send` (bereits Basis-Redaction).
