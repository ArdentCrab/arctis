# Arctis: Rollout-Anleitung (jetzt → Produktion)

Diese Anleitung ist **1:1 an das Repository gebunden**: App-Factory (`arctis/app.py`), vorhandene Tests unter `tests/`, `openapi.json` und `arctis/config.py`. Sie beschreibt **Reihenfolge**, **Abnahmekriterien** und **Betrieb** — keine parallele „Mini-App“ neben `create_app()`.

**Navigation:** Ausgang & API-Schicht (§2–3) · App-Factory & Konfiguration (§4–7) · Tests (§8) · Produktion (§9) · Spec v1.5 (§10) · **Engine P0/P1 (§12)** · **Arctis Ghost (§13)** · **Gesamtcheckliste (§14)** · **Ghost/Skill-Projektplan ([arctis_ghost_project_plan.md](arctis_ghost_project_plan.md))** · **Ghost-Demo-Matrix ([arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md))**.

*Hinweis zur Nummerierung:* Nach §10 folgen direkt **§12** und **§13** (Produkt-Erweiterungen); **§14** ist die komprimierte End-Checkliste. Es gibt kein separates §11-Kapitel.

---

## 1. Ziele und Prinzipien

| Prinzip | Umsetzung |
|--------|-----------|
| **Ein ASGI-Einstieg** | Produktion startet die App über **`arctis.app:create_app`** (Factory), nicht über ein separates FastAPI-Skript ohne diese Factory. |
| **Ein Auth-/Tenant-Pfad** | `APIKeyMiddleware` setzt Kontext auf `request.state`; Routen nutzen `Depends` und/oder `arctis.auth.scopes` — **keine** zweite, hartcodierte API-Key-Logik in Einzelrouten. |
| **Kontrakt** | Öffentliche HTTP-Pfade und Schemas: **`openapi.json`** (Titel „Arctis“, Version `0.1.0`) als Referenz; bei Änderungen OpenAPI und Tests anpassen. |
| **Abnahme** | Nach jeder größeren Schicht: gezielte **`pytest`**-Läufe (siehe Abschnitt 8). |
| **Engine & Governance (Produkt)** | API allein reicht für „HTTP läuft“; **finale Produktreife** inkl. Budget/Mock/Evidence/Rate-Limit: **§12**; dateibasiertes Nutzer-Interface ohne zweite Runtime: **§13**. |

**Hinweis:** Das Architektur- und Sicherheitszielbild steht zusätzlich in `docs/arctis_engine_and_security_spec_v1.5.md`. Wo die Spezifikation weitergeht als der Code, gilt: **erst Repo-Tests grün, dann schrittweise Spec schließen** — nicht alles auf einmal. **§12/§13** konkretisieren die Lücken zwischen Rollout-Anleitung und Spec (Budget, Ghost, Evidence).

---

## 2. Ausgangsprüfung (P0)

### 2.1 Paket `arctis.api` muss importierbar sein

`create_app()` importiert ausschließlich aus `arctis.api.*`. Fehlt das Paket, schlagen **alle** API-Tests und der Start fehl.

**Erwartete Struktur (Pflichtdateien laut `arctis/app.py`):**

```
arctis/api/
  __init__.py
  main.py              # Meta-Router (u. a. /health)
  middleware.py        # APIKeyMiddleware, hash_api_key_sha256
  deps.py              # DB, Singleton-Reset, ggf. Audit-Helfer
  routes/
    __init__.py
    api_keys.py
    llm_config.py
    runs.py
    review.py
    reviewer_dashboard.py
    pipelines.py
    llm_keys.py
    workflows.py
    customer.py
    prompt_matrix.py
    admin_policies.py
    admin_flags.py
    admin_routing.py
    metrics.py
    audit_export.py
    dashboard.py
    costs.py
```

**Erster Smoke-Test:**

```bash
pytest tests/api/test_health.py -q
```

Erwartung: `GET /health` → `200`, Body `{"status":"ok"}`.

### 2.2 Root-`main.py`

Die Datei `main.py` im Repository-Root kann für lokale Demos oder Legacy-Flüsse existieren — **Produktions-Deployment** sollte sich am **`create_app()`**-Pfad orientieren, damit Middleware, Router, Sentry und DB-Init identisch zu den Tests sind.

---

## 3. Bau-Reihenfolge: API-Schicht (Datei für Datei)

Die Reihenfolge unten minimiert Zyklen: zuerst Middleware und Dependencies, dann Meta-Router, dann fachliche Router **in der gleichen Reihenfolge wie in `create_app()`**.

### Phase A — Fundament

| Schritt | Datei | Aufgabe (kurz) |
|--------|--------|----------------|
| A1 | `arctis/api/__init__.py` | Paket-Marker. |
| A2 | `arctis/api/middleware.py` | `APIKeyMiddleware` nach Starlette/FastAPI-Konvention **nach außen** (in `app.py` direkt nach CORS). Funktion **`hash_api_key_sha256`** (von Tests und `scripts/bootstrap_initial_api_key.py` importiert). Auf `request.state` u. a.: Tenant-Kontext, **`scopes`** (siehe `arctis/auth/scopes.py`: `resolve_scope` liest `request.state.scopes`). Öffentliche Pfade (z. B. `/health`, `/docs`) von der API-Key-Pflicht ausnehmen, falls so gewünscht — konsistent mit Tests. |
| A3 | `arctis/api/deps.py` | Gemeinsame Dependencies: DB-Session, ggf. aktueller Tenant aus `request.state`. **Muss exportieren:** `reset_engine_singleton` (Tests rufen das in Fixtures auf, zusammen mit `arctis.db.reset_engine`). Optional/ je nach Implementierung: `get_audit_export_store`, `get_optional_audit_query_store` (siehe `tests/api/test_audit_export_*.py`, `test_dashboard_routing.py`). |
| A4 | `arctis/api/main.py` | `APIRouter` mit **`GET /health`**. Weitere Meta-Endpunkte nur, wenn Tests oder OpenAPI sie verlangen. |
| A5 | `arctis/api/routes/__init__.py` | Paket-Marker. |

**Gate nach Phase A:** `pytest tests/api/test_health.py tests/api/test_auth_scopes_enforcement.py -q` (Scopes setzen voraus, dass Middleware + Admin-/Dashboard-Routen teilweise existieren — ggf. Router-Stubs mit 501 nur für sehr frühe Iteration; Ziel ist vollständige Implementierung).

### Phase B — Router in Registrierungs-Reihenfolge (`arctis/app.py`)

Jede Zeile: eine Datei unter `arctis/api/routes/`, jeweils ein `router = APIRouter(...)`, in `create_app()` per `include_router` eingebunden.

| # | Modul | Prefix in `create_app` | OpenAPI-Pfade (Auszug aus `openapi.json`) |
|---|--------|-------------------------|---------------------------------------------|
| 1 | `api_keys.py` | *(kein Prefix)* | `/api-keys`, `/api-keys/{key_id}` |
| 2 | `llm_config.py` | — | `/llm-config`, `/llm-config/test` |
| 3 | `runs.py` | — | `/runs`, `/runs/search`, `/runs/{run_id}`, `/snapshots`, `/snapshots/{snapshot_id}`, `/snapshots/{snapshot_id}/replay`, `/pipelines/{pipeline_id}/run` |
| 4 | `review.py` | **`/review`** | `/review/{task_id}/approve`, `/review/{task_id}/reject` — *Hinweis: OpenAPI-Pfade enthalten oft das Präfix bereits als Teil des Pfads; beim `include_router(..., prefix="/review")` auf doppelte Segmente achten.* |
| 5 | `reviewer_dashboard.py` | **`/reviewer`** | `/reviewer/queue`, `/reviewer/sla_badges`, `/reviewer/task/{task_id}` |
| 6 | *(bereits in A4)* `main.py` | — | `/health` |
| 7 | `pipelines.py` | — | `/pipelines/`, `/pipelines/{pipeline_id}`, `/pipelines/{pipeline_id}/versions` |
| 8 | `llm_keys.py` | — | `/keys/llm/`, `/keys/llm/{key_id}`, `/keys/llm/{key_id}/rotate` |
| 9 | `workflows.py` | — | `/workflows/`, `/workflows/{workflow_id}`, `/workflows/{workflow_id}/upgrade` |
| 10 | `customer.py` | — | `/customer/workflows/{workflow_id}/execute` |
| 11 | `prompt_matrix.py` | — | `/prompt-matrix/compare`, `/prompt-matrix/{matrix_id}`, `/prompt-matrix/{matrix_id}/version` |
| 12 | `admin_policies.py` | **`/admin`** | `/admin/tenants/{tenant_id}/policy`, `/admin/pipelines/{pipeline_name}/policy` |
| 13 | `admin_flags.py` | **`/admin`** | `/admin/tenants/{tenant_id}/flags` |
| 14 | `admin_routing.py` | **`/admin`** | `/admin/tenants/{tenant_id}/routing_models`, … (siehe `openapi.json`) |
| 15 | `metrics.py` | **`/metrics`** | `/metrics/review_sla`, `/metrics/reviewer_load`, `/metrics/prometheus` |
| 16 | `audit_export.py` | **`/audit`** | `/audit/export` |
| 17 | `dashboard.py` | **`/dashboard`** | `/dashboard/review_sla`, `/dashboard/routing` |
| 18 | `costs.py` | **`/costs`** | `/costs/report` |

**Wichtig:** Die tatsächlichen URL-Pfade müssen mit **`openapi.json`** und den Tests übereinstimmen. Wenn sich Präfixe und Pfadstrings überlagern, in einer lokalen OpenAPI-Ausgabe (`/openapi.json` der laufenden App) gegenprüfen.

### Phase C — Autorisierung pro Route

- **`arctis/auth/scopes.py`:** `Scope`-Enum, `RequireScopes`, `enforce_any_scope`. Admin-Endpunkte: mindestens `tenant_admin` oder `system_admin` wo die Tests es erwarten (z. B. `tests/api/test_auth_scopes_enforcement.py`: `tenant_user` → **403** auf `/admin/.../flags`).
- **Legacy-Schlüssel ohne `scopes` in der DB:** `default_legacy_scopes()` → `tenant_user` + `reviewer` (kein implizites `tenant_admin`).

**Nach API-Stabilisierung:** Budget-Valve, Rate-Limit, Mock-Header, Evidence-Aggregation und Idempotenz (§12) **in derselben Auth-/Tenant-Linie** implementieren — keine parallele „Bypass“-Logik neben `APIKeyMiddleware`.

---

## 4. App-Factory und Middleware-Reihenfolge

Relevante Zeilen in `arctis/app.py`:

1. `init_engine()` und optional `ensure_default_pipeline_policy` mit `SessionLocal`.
2. Sentry bei gesetztem `SENTRY_DSN`.
3. Logging: **DEBUG** nur wenn `ENV=dev`, sonst **INFO**.
4. `FastAPI(title="Arctis", version="0.1.0")`.
5. **CORSMiddleware** zuerst (äußerste Schicht nach Starlette-Konvention: zuerst hinzugefügt = außen).
6. **APIKeyMiddleware** danach (innerhalb von CORS).
7. Alle `include_router`-Aufrufe wie in der Datei geordnet.

**Produktion:** `ENV=prod`, `ALLOWED_ORIGINS` auf echte Frontend-Origins setzen (kein `*` in sensiblen Setups).

---

## 5. Konfiguration und Geheimnisse (`arctis/config.py`)

| Variable | Rolle |
|----------|--------|
| `DATABASE_URL` | SQLAlchemy-URL (Prod: Postgres o. Ä., nicht SQLite-Datei auf ephemeral Disk). |
| `ENV` | `dev` \| `prod` (Log-Level, ggf. weitere Härtung). |
| `ALLOWED_ORIGINS` | Komma-separierte CORS-Origins. |
| `SENTRY_DSN` | Optional; aktiviert Sentry in `create_app()`. |
| `OPENAI_*` / `OLLAMA_*` / `ARCTIS_USE_OLLAMA` | LLM-Fallback, wenn kein Tenant-Key. |
| `ARCTIS_GOVERNANCE_CROSS_TENANT` | Cross-Tenant-Abfragen für Metriken/Audit (standardmäßig `false`; bewusst aktivieren). |
| `ARCTIS_AUDIT_JSONL_DIR` / `ARCTIS_AUDIT_STORE` | Audit-Export-Backend (`jsonl`, `db`, `none`). |

Weitere Keys (z. B. Verschlüsselung für gespeicherte LLM-Keys): in Tests als `ARCTIS_ENCRYPTION_KEY` gesetzt — in Prod aus Secret-Store.

**Regel:** Keine Secrets im Git; `.env` nur lokal / in Secret-Management.

---

## 6. Datenbank und Migrationen

- **Engine-Init:** `arctis.db` (von `create_app()` via `init_engine()`).
- **Schema:** SQLAlchemy-Modelle unter `arctis/db/`; Migrationen unter `alembic/versions/`.
- **Produktion:** Vor Deploy **`alembic upgrade head`**. Kein ausschließliches Vertrauen auf `Base.metadata.create_all` für Prod, sofern nicht explizit für eine kontrollierte Umgebung vorgesehen.
- **Seed:** `arctis.policy.seed.ensure_default_pipeline_policy` läuft beim App-Start mit Session — sicherstellen, dass Prod-DB diesen Schritt ohne Fehler durchläuft.

---

## 7. Skripte und Bootstrap

| Skript | Zweck |
|--------|--------|
| `scripts/bootstrap_initial_api_key.py` | Legt Dev-Tenant und Hash für bekannten Plain-Key an; nutzt **`hash_api_key_sha256`** aus `arctis.api.middleware`. |

Nach DB-Migrationen und vor ersten API-Calls lokal: Skript ausführen (siehe Kopfkommentar im Skript, `PYTHONPATH` = Repo-Root).

---

## 8. Test-Matrix (Abnahme pro Schicht)

`pytest.ini` definiert u. a. Marker: `integration`, `e2e`, `engine`, `security`, `compliance`, `performance`.

### 8.1 API (Pflichtpfad Richtung Produktion)

| Testdatei | Thema |
|-----------|--------|
| `tests/api/test_health.py` | Health |
| `tests/api/test_auth_scopes_enforcement.py` | Scopes / 403 |
| `tests/api/test_api_keys.py` | API-Keys |
| `tests/api/test_llm_keys.py` | LLM-Keys |
| `tests/api/test_pipelines.py` | Pipelines |
| `tests/api/test_runs.py` | Runs / Snapshots |
| `tests/api/test_runs_requires_policy_db.py` | Policy-DB |
| `tests/api/test_runs_policy_metadata.py` | Policy-Metadaten |
| `tests/api/test_workflows.py` | Workflows |
| `tests/api/test_customer_execute.py` | Customer Execute |
| `tests/api/test_spec_master_prompts.py` | Spec/Master-Prompts |
| `tests/api/test_reviewer_dashboard.py` | Reviewer-Dashboard |
| `tests/api/test_audit_export_basic.py` | Audit Export |
| `tests/api/test_audit_export_strict_mode.py` | Audit Strict |
| `tests/api/test_audit_export_db_backend.py` | Audit DB |
| `tests/api/test_metrics_review_sla.py` | Metriken SLA |
| `tests/api/test_metrics_reviewer_load.py` | Reviewer Load |
| `tests/api/test_dashboard_review_sla.py` | Dashboard SLA |
| `tests/api/test_dashboard_routing.py` | Dashboard Routing |
| `tests/api/test_sla_report.py` | SLA Report |
| `tests/api/test_cost_report.py` | Kosten |

### 8.2 Admin-API

| Testdatei | Thema |
|-----------|--------|
| `tests/api_admin/test_admin_policies.py` | Admin-Policies |
| `tests/api_admin/test_feature_flags.py` | Feature Flags |
| `tests/api_admin/test_policy_immutability.py` | Policy-Immutability |

### 8.3 Empfohlene erweiterte Gates vor Produktion

```bash
pytest tests/api tests/api_admin -q
pytest tests/integration -m integration -q
```

Weitere Ordner (`tests/engine`, `tests/security_invariants`, `tests/compliance`, …) je nach Release-Scope und Spec-Priorität.

---

## 9. Produktion: Betrieb und Deployment

### 9.1 Prozess-Start

Beispiel (uvicorn):

```bash
uvicorn arctis.app:create_app --factory --host 0.0.0.0 --port 8000
```

`--factory` ist nötig, weil `create_app` eine Factory-Funktion ist.

### 9.2 Checkliste vor Go-Live

- [ ] `ENV=prod`, passende `DATABASE_URL`, Migration angewendet.
- [ ] `ALLOWED_ORIGINS` auf Produktions-Frontends.
- [ ] `SENTRY_DSN` gesetzt (optional aber empfohlen).
- [ ] Secrets (OpenAI, Encryption, Stripe falls genutzt) im Secret-Store.
- [ ] `ARCTIS_AUDIT_STORE` und ggf. `ARCTIS_AUDIT_JSONL_DIR` für Compliance-Konzept geklärt.
- [ ] TLS terminieren (Reverse Proxy / Load Balancer).
- [ ] Rate-Limits / WAF nach Bedarf **vor** der App (oder als Middleware — nicht doppelt widersprüchlich).
- [ ] Backups für DB; Restore getestet.

### 9.3 Artefakte, die oft noch ergänzt werden

Im Repository nicht zwingend vorhanden — für Produktion typischerweise anlegen:

- **Dockerfile** (Multi-Stage, Non-Root, `uvicorn` mit `--factory`).
- **docker-compose** oder Helm/Manifeste für App + DB.
- **CI** (z. B. GitHub Actions): Install, Lint optional, `alembic upgrade` gegen Test-DB, `pytest`.

---

## 10. Abgleich mit Spec v1.5

`docs/arctis_engine_and_security_spec_v1.5.md` beschreibt u. a. Budget-Limits, Dry-Run, Marketplace, Edge — **nicht alles muss im aktuellen Code vollständig sein**.

Empfohlenes Vorgehen:

1. **Kern:** API + Engine-Pfad, der von `tests/integration` und `tests/engine` abgedeckt ist, stabilisieren.
2. **Sicherheit:** Scopes, Tenant-Isolation, Audit wie in den Security-/Compliance-Tests.
3. **Spec-Lücken** als Tickets mit Verweis auf Spec-Abschnitt; pro Ticket Tests vor Merge.
4. **Produkt-Lücken** gezielt über **§12** (Engine/API-Härtung) und **§13** (Ghost als Endnutzer-Kanal) schließen, statt Spekulationen außerhalb des Repos.

---

## 12. Engine- und API-Erweiterungen (P0 / P1)

Ziel: **dieselbe** Control-Plane (`create_app`, Middleware, Scopes) bleibt die einzige Governance-Schicht. Validierung, Budget, Limits und Nachweise passieren **vor** oder **neben** `arctis.engine` — nicht als zweiter paralleler Einstieg.

### 12.1 P0 — Pflicht für „harte“ Produktion

| ID | Thema | Technische Zielsetzung | Typische Verdrahtung im Repo |
|----|--------|-------------------------|-------------------------------|
| **E1** | **422 vor Engine** | Request-Bodies für auslösende Endpunkte (z. B. `POST /pipelines/{pipeline_id}/run`) strikt per **Pydantic** validieren; ungültige Eingaben erreichen `arctis.engine.runtime` nicht. | `arctis/api/routes/pipelines.py` / `runs.py` + gemeinsame Schemas (z. B. unter `arctis/` oder `arctis/api/schemas/` sobald angelegt). |
| **E2** | **Budget-Valve** | Vor `Engine.run` (oder zentral in der Route): Policy-/Tenant-Budget prüfen; bei Überschreitung **HTTP 402** (oder vereinbartes Budget-Signal) + **Audit-Flag** / strukturiertes `detail`. Kein stilles Absenken ohne Antwortcode. | `arctis/config.py` (Limits), Policy-DB (`arctis/policy/`), Route oder Middleware — **eine** Implementierung, keine doppelte Logik. |
| **E3** | **Rate-Limit** | Pro **Tenant** und/oder **API-Key** (z. B. Sliding Window / Token Bucket). Antwort **429** mit `Retry-After` wo sinnvoll. | Bevorzugt Erweiterung von `arctis/api/middleware.py` oder dediziertes Middleware-Modul, registriert direkt neben `APIKeyMiddleware` (Reihenfolge testen). |
| **E4** | **Mock-Modus** | Header z. B. **`X-Arctis-Mock: true`** → deterministischer Pfad durch Engine/Stub (keine externen LLM-Calls); nur mit passendem Scope oder nur `ENV=dev`, je nach Threat Model. | Middleware setzt `request.state.mock = True` oder Route liest Header und übergibt an Runtime. |
| **E5** | **Evidence** | Ein nachvollziehbares **Evidence-Envelope** oder aggregierter Endpoint: `run_id`, `snapshot_id`, Policy-Hash, ggf. Signatur — konsistent mit Audit/Compliance. Kann `GET /runs/{run_id}` erweitern oder dedizierten Pfad spezifizieren (OpenAPI + Tests). | `arctis/api/routes/runs.py`, `arctis/engine/`, `arctis/audit/` je nach bestehender Datenlage. |

**Reihenfolge-Empfehlung:** **E1** zuerst (verhindert nutzlose Engine-Zyklen), dann **E2/E3** (Kosten & Missbrauch), dann **E4** (Testbarkeit), **E5** (Nachweis).

### 12.2 P1 — Mid-Market / Skalierung

| ID | Thema | Technische Zielsetzung | Hinweis |
|----|--------|-------------------------|---------|
| **E6** | **Idempotency-Key** | Header `Idempotency-Key` (oder Projektstandard) für wiederholbare `POST`-Runs: gleicher Key → gleiche semantische Antwort, keine doppelte Wirkung. | Persistenz für Key → `run_id`/`status` nötig; Tenant-scoped. |
| **E7** | **Metrics** | Prometheus-kompatibler Endpoint ist in **`openapi.json`** unter `/metrics/prometheus` referenziert — Implementierung mit echten Metriken (Latenz, Fehlerquote, Budget-Events) abstimmen. | Bereits Router `arctis/api/routes/metrics.py`; Inhalt mit Observability-Stack (`arctis/observability/`) verzahnen. |
| **E8** | **DR-Nachweis** | Backup/Restore der Prod-DB (und ggf. Audit-Speicher) **dokumentiert und mindestens einmal pro Major** geübt. | Operativer Nachweis, kein Python-Modul-Zwang; in §9 Go-Live aufnehmen. |

### 12.3 Abnahme

- Pro P0-Item: **mindestens ein** automatisierter Test (API oder Engine), der das erwartete Statuscode-Verhalten und kein Leaken über Tenant-Grenzen prüft.
- OpenAPI und ggf. `openapi.json` im Repo bei neuen Headern/Pfaden aktualisieren.

---

## 13. Arctis Ghost (Zero-Interface Governance)

**Ghost** ist **kein** zweites Backend und **kein** direkter Import der Engine. Es ist ein **dateibasierter Klient** (Watch/Worker), der **ausschließlich über HTTP** mit der bestehenden Arctis-API spricht — geeignet für Nutzer ohne UI (z. B. getaktete Finance-/Consulting-Workflows).

**Detaillierter Fahrplan (Skill-Envelope, `skill_reports`, Ghost-Paket, PLG, Innovations-Horizonte):** [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) — dort ist der **kanonische Projektplan** für Umsetzung in Issues/Cursor gebündelt; §13 hier bleibt die kompakte Rollout-Einbettung. **24-Prompt-Serie** (Reihenfolge inkl. `init-demo` vor `watch`): [arctis_ghost_prompt_series.md](arctis_ghost_prompt_series.md). **Demos:** Story-Arc & Module für Landingpage [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md) · 60-Sekunden-Skript [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md).

### 13.1 Zielbild

| Aspekt | Regel |
|--------|--------|
| Transport | **Nur HTTP(S)** zu derselben Basis-URL wie die Produkt-API. |
| Governance | **Keine** lokale „Governance-Engine“ — alle Ablehnungen kommen als **422 / 403 / 402 / 429** von der API. |
| Runtime | **Keine** `from arctis.engine ...` in Ghost; sonst entstehen zwei Wahrheiten. |

### 13.2 Ordnerstruktur (Referenz)

Repository-Pfad ist Projektentscheidung (z. B. top-level `ARCTIS_GHOST/` oder `tools/ghost/`). Logische Struktur:

```
ARCTIS_GHOST/
  incoming/
    text/
    json/
    excel/              # später (Phase C+)
    review_actions/
    batch/
  outgoing/
    approved/
    rejected/
    review/
    skipped/
    errors/
  config/
    config.yaml         # Basis-URL, API-Key-Quelle (Env), Tenant-Kontext
  state/                # Hashes / Cursor gegen Doppel-Läufe
```

### 13.3 Betriebsregeln

- **Ein Parser pro Eingabeart** (TXT, JSON; später Excel): klare Zuordnung Ordner → Parser → JSON-Payload für die API.
- **State:** Content-Hash (oder stabiler Datei-ID + mtime-Policy) gegen **Doppel-Runs**; unveränderte Eingaben → Ausgabe nach **`skipped/`** (Smart Re-Run).
- **Commit-Gate:** nur Dateien mit Marker **`.commit`** verarbeiten; **`.pending`** ignorieren (oder umgekehrt nach Team-Konvention — festhalten und testen).
- **Review-Loop:** wenn die API einen Review-Zustand meldet, steuert Ghost **`POST /review/...`** (siehe `openapi.json`) — keine lokale Genehmigungslogik.
- **Evidence-Envelope:** geschriebene Ergebnisdateien enthalten mindestens **`run_id`**, **`snapshot_id`** (falls vorhanden), **Hash** der Eingabe — kompatibel mit §12 **E5**.

### 13.4 Lifecycle (ein Durchlauf)

1. Watch auf `incoming/**` (oder Poll).
2. Datei parsen → **JSON-Body** für die jeweilige Route bauen.
3. **`POST /pipelines/{pipeline_id}/run`** (oder projektgewählter Einstieg laut API).
4. **`GET /runs/{run_id}`** (und ggf. Snapshots / Evidence gemäß §12 **E5**).
5. Ergebnis + Envelope nach **`outgoing/...`** schreiben; State aktualisieren.
6. Eingabedatei archivieren oder löschen nach Policy.

### 13.5 Phasen

| Phase | Umfang |
|--------|--------|
| **Ghost MVP (B)** | Parser **TXT + JSON**; Ausgabe **JSON + kurze `summary.txt`**; kein Excel/PDF; kein Cloud-Adapter. |
| **Ghost Vollausbau (C)** | Excel-Parser, Batch-Manifest, vollständiger Review-Loop, Evidence wie in API; **höchstens ein** Cloud-Zieladapter (nicht fünf parallel), damit Betrieb überschaubar bleibt. |

### 13.6 Abnahme Ghost

- Integrationstest: **trockener** Lauf gegen `TestClient(create_app())` oder gegen lokale API mit Fixture-Datei in `incoming/`.
- Sicherstellen: Ghost-Prozess startet **ohne** `PYTHONPATH`-Import von `arctis.engine`.

---

## 14. Kurz-Checkliste „von jetzt bis Produkt“

Zusammenfassung nach §2–10 und den Erweiterungen §12–§13.

### 14.1 API & Plattform (Pflicht)

1. **`arctis/api/`** vollständig und importierbar; Middleware + `deps` wie von Tests gefordert.
2. **Alle Router** aus `arctis/app.py` implementiert; Pfade konsistent mit **`openapi.json`**.
3. **Scopes** auf allen sensiblen Routen; Verhalten wie `tests/api/test_auth_scopes_enforcement.py`.
4. **`pytest tests/api tests/api_admin`** grün.
5. **DB:** Alembic auf Prod-Schema; Policy-Seed läuft.
6. **Konfiguration:** `ENV=prod`, CORS, Secrets, Sentry.
7. **Deploy:** Factory-Start, TLS, Monitoring, Backups.

### 14.2 Engine & Governance (finale Produktreife — §12)

8. **P0 aus §12** abgearbeitet oder bewusst zurückgestellt (Ticket + Risiko): Validation vor Engine, Budget-Valve, Rate-Limit, Mock-Header, Evidence.
9. **P1 aus §12** nach Priorität (Idempotenz, DR-Nachweis, …).

### 14.3 Ghost (optionaler Rollout-Pfad — §13)

10. **Ghost MVP** (§13.4–§13.6): Ordnerstruktur, TXT/JSON, nur HTTP, keine Engine-Imports im Ghost-Prozess.
11. **Ghost Vollausbau** (§13.5): erst nach stabiler API + gewünschter Evidence-/Review-Kette.
12. **Skill Engine am Customer-Execute** (optional, Produktpfad): Request `skills`, `execution_summary.skill_reports`, Run-Zugriff für Clients — siehe [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) §3 und §10.

---

*Dokument-Revision: `arctis/app.py`, `openapi.json`, `pytest.ini`, `arctis/config.py`, Testpfade; §12–§13: Engine-P0/P1 und Ghost (Zero-Interface Governance) als Ergänzung zur reinen API-Rollout-Anleitung.*
