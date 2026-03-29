# Arctis HTTP API — Security-Überblick

Zielgruppe: Backend- und Platform-Engineering. Details und Runbooks: [`security_production.md`](security_production.md).

## Tenant-Isolation

- Jede authentifizierte Anfrage erhält `tenant_id` und `scopes` aus dem validierten API-Key (Middleware).
- Ressourcen (Runs, Workflows, Pipelines, …) müssen zur **gleichen Tenant-ID** passen; Tests decken IDOR-Szenarien ab.
- **Evidence** und Routing-Daten folgen der gleichen Tenant-Kette über die Control-Plane (keine Engine-Änderung nötig für dieses Dokument).

## Authentifizierung

- Header `X-API-Key` (außer öffentliche Pfade: `/health`; Doc-Pfade nur wenn OpenAPI exponiert ist).
- Ohne funktionierende DB: **503** mit klarer Meldung — kein anonymer Dev-Tenant in Produktion.

## Autorisierung (Scopes)

| Scope | Rolle |
|-------|--------|
| `tenant_user` | Default wenn `scopes` NULL/leer; Kunden-Flows. |
| `reviewer` | Review-Endpoints; **nicht** implizit vergeben. |
| `tenant_admin` | Metriken, Audit-Export, Kosten-Reports innerhalb des eigenen Tenants. |
| `system_admin` | Plattform; **erforderlich** für Cross-Tenant-Zugriffe (siehe unten). |

Endpunkte nutzen `RequireScopes(...)` — siehe `arctis.auth.scopes`.

## Cross-Tenant (Governance)

- Nur wenn **`ARCTIS_GOVERNANCE_CROSS_TENANT=true`** **und** der API-Key **`system_admin`** enthält.
- Betrifft u. a. `GET /metrics/review_sla`, `GET /metrics/reviewer_load` mit fremder `tenant_id`, sowie `GET /audit/export` mit fremder `tenant_id`.
- Jede erfolgreiche Abfrage erzeugt ein **Warning-Log** (`cross_tenant_governance_query`).

## Rate-Limits

- Primär: Datensätze `TenantRateLimitRecord` / `ApiKeyRateLimitRecord`.
- Ohne Eintrag: synthetisches Limit pro Minute über `Settings.synthetic_rate_limit_per_minute()` (Prod-Default **120**/Minute wenn nicht überschrieben).

## Budget-Enforcement

- Konfiguration über Budget-Records und Umgebungs-Caps (`ARCTIS_BUDGET_MAX_TOKENS_PER_RUN`, …).
- Operative Alerts: siehe Monitoring-Runbooks in `security_production.md`.

## OpenAPI / Dev-Modus

- **Prod:** Docs aus; direkte Requests auf `/docs`, `/redoc`, `/openapi.json` → **404**.
- **Dev:** Standard exponiert; override mit `ARCTIS_EXPOSE_OPENAPI`.
- **Dev CORS *:** nur `ARCTIS_CORS_WILDCARD_DEV=true` (ohne Cookies/Credentials an Browser).

## CORS (Produktion)

- Nur Einträge aus `ALLOWED_ORIGINS` (komma-separiert); Credentials erlaubt für explizite Origins.

## Observability

- **Sentry:** `before_send` redigiert u. a. `X-API-Key`, `Authorization`, Cookies.
- **Prometheus:** `/metrics/prometheus` (geschützt); Dashboards für Fehlerquote, Latenz, 429, Budget — in eurer Grafana-Stack definieren.

## LLM / Prompt-Injection

- Eingaben können sensible Daten enthalten; Sanitizer und Allowlists wo implementiert — siehe Engine-/Governance-Spezifikation.
- Keine Roh-Prompts oder vollständigen Kunden-Inputs in strukturierten Logs ablegen.
