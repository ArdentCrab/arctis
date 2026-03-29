# Deployment checklist

## Infrastructure (A1.1)

- [ ] `ENV=prod` (oder gleichwertiges produktionsnahes Verhalten für Staging, siehe [`docs/Deployment.md`](docs/Deployment.md))
- [ ] `DATABASE_URL` gesetzt (Postgres o. Ä.; nicht SQLite auf ephemeral Disk in Prod)
- [ ] `alembic upgrade head` gegen diese Datenbank ausgeführt (vor Live-Traffic)
- [ ] `ALLOWED_ORIGINS` auf echte Frontend-Origins (komma-separiert)
- [ ] `ARCTIS_AUDIT_STORE` gewählt (`jsonl` \| `db` \| `none`); bei `jsonl`: `ARCTIS_AUDIT_JSONL_DIR` beschreibbar und gemountet

## Secrets (A1.2)

Werte nur im **Secret Store** der Umgebung, nicht im Repo ([`docs/Deployment.md`](docs/Deployment.md) Abschnitt Secrets).

- [ ] `ARCTIS_ENCRYPTION_KEY` (Fernet-kompatibel)
- [ ] `CONTROL_PLANE_API_KEY` und `CONTROL_PLANE_URL` für Betrieb/Checks
- [ ] `SENTRY_DSN`
- [ ] `STRIPE_SECRET_KEY` und `STRIPE_WEBHOOK_SECRET` (oder **N/A** mit Begründung, wenn kein Billing; `launch_check` erwartet sie für ein volles Gate — siehe Deployment-Doku)
- [ ] `OPENAI_API_KEY` o. Ä. nur falls ihr globale Provider-Keys setzt (sonst Tenant-Keys in der DB)

## Auth & Identity (A1.3)

Siehe [`docs/Authentication.md`](docs/Authentication.md).

- [ ] **Auth0** *oder* **Supabase** festgelegt; alle erforderlichen Umgebungsvariablen gesetzt (siehe [`docs/Authentication.md`](docs/Authentication.md), `launch_check` Schritt 7)
- [ ] Im IdP: **Callback URLs**, **Logout URLs**, **Site URL** / Web Origins zum Dashboard-Host; konsistent mit [`ALLOWED_ORIGINS`](docs/Deployment.md) für API-Aufrufe
- [ ] **Tenant-API-Keys** in der DB für Staging/Prod angelegt; Scopes geprüft (`pytest tests/api/`)

## Observability (A1.4)

Siehe [`docs/Observability.md`](docs/Observability.md).

- [ ] **`SENTRY_DSN`** gesetzt und Projekt-Alerts in Sentry konfiguriert (siehe A1.2)
- [ ] **Prometheus:** Scrape von **`GET /metrics/prometheus`** mit **`X-API-Key`** (Scope `tenant_admin` oder `system_admin`) — Key nur im Secret Store; kein öffentlicher unauthentifizierter Metrics-Endpunkt
- [ ] **Grafana** (oder vergleichbar) an eure Prometheus-Instanz angebunden; Dashboards für Latenz/Fehler/429 nach Bedarf
- [ ] **Alertmanager** / ähnliche Regeln für 5xx, Latenz, ggf. Budget-Metriken (Runbook außerhalb Repo)

## DR & Backup (A1.5)

Siehe [`docs/DR.md`](docs/DR.md) (Backup-Strategie, Restore, **Verification** / Restore-Test, RPO/RTO).

- [ ] **Backup-Job(s)** für Postgres (und bei JSONL-Audit das Audit-Verzeichnis) nach DR.md automatisiert; **Fehler-Alert** bei ausbleibendem oder fehlgeschlagenem Lauf
- [ ] **Restore-Test** (DR-Drill) nach DR.md durchgeführt oder mit Datum terminiert; Ergebnis im internen Runbook dokumentiert
- [ ] **`docs/DR.md`** mit aktuellem Betriebsmodell abgeglichen (Review bei Release oder quartalsweise)

## Launch gates (A1.6)

Siehe [`docs/Launch_readiness.md`](docs/Launch_readiness.md) und [`arctis/scripts/launch_check.py`](../arctis/scripts/launch_check.py).

- [ ] **`python -m arctis.scripts.launch_check`** in **Staging** mit gesetzten Umgebungsvariablen **grün** (Exit 0)
- [ ] **Playwright:** `npm run test:e2e` unter `dashboard/` — siehe Launch_readiness (aktuell ggf. noch einzurichten)
- [ ] **Locust:** Kurzlauf wie in `launch_check` erfolgreich; Ziel **&lt; 5 %** Fehlerquote zusätzlich in Logs/Report prüfen
- [ ] **Statuspage** (oder gleichwertig) für Nutzer sichtbar gepflegt
- [ ] **Support-Inbox** / Erstkontakt-Kanal betriebsbereit und kommuniziert

## Weitere Punkte

- [ ] Billing-Webhooks in Stripe-Dashboard zur API-URL konfiguriert (wenn Billing aktiv)
- [ ] Alembic upgrade head applied (siehe A1.1, falls noch nicht abgehakt)
