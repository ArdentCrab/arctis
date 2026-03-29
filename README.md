# Arctis

**Produkt:** Plattform für **Pipeline A** — IR, Engine-Runtime und Control Plane — mit einer **FastAPI-Arctis-API** für Customer-Execute und Betrieb. **Ghost** ist die schlanke **CLI**: nur HTTP, keine Engine im Client; Runs, Evidence und lokale Artefakte unter `outgoing/`.

**Zielgruppe:** **Plattform- und Backend-Teams**, die Pipelines und Governance integrieren; **Solution- und Field-Rollen**, die Kunden einen **ordnerbasierten** Einstieg (`ghost init-demo` → `ghost run`) ohne separates Produkt-UI geben wollen.

**API und Ghost:** Die **API** ist die autoritative Ausführungs- und Evidence-Quelle; **Ghost** spricht dieselben Endpunkte (`POST …/execute`, `GET /runs/{id}`) und spiegelt Ergebnisse lokal — **eine** Policy- und Nachweis-Wahrheit auf dem Server.

- **Erster Run (≈30 s):** Abschnitt [Try Arctis in 30 seconds](#try-arctis-in-30-seconds) · ausführlicheres 60‑Sekunden-Storyboard: [`docs/arctis_ghost_demo_60.md`](docs/arctis_ghost_demo_60.md).
- **Repository:** [`github.com/arctis-lab/arctis`](https://github.com/arctis-lab/arctis) · **GHCR:** `ghcr.io/arctis-lab/arctis` (nach Release-Workflows).
- **Version:** siehe [`pyproject.toml`](pyproject.toml) — aktuell **0.1.2** ([`CHANGELOG.md`](CHANGELOG.md)).
- **Paketinhalt:** ein Wheel umfasst API-, Engine- und Ghost-Code; Strategie für Publish/Split siehe [`docs/arctis_package_strategy.md`](docs/arctis_package_strategy.md).
- **CI:** GitHub Actions laufen automatisch, sobald das Repository auf GitHub gepusht wird. ([`.github/workflows/ci.yml`](.github/workflows/ci.yml) — PRs und Push auf `main`/`master`.) **Release:** bei Tag `v*` bauen [`.github/workflows/release.yml`](.github/workflows/release.yml) (Wheel, sdist, Checksums) und [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) (Push nach **GHCR**). **Security:** [SECURITY.md](SECURITY.md) (Meldeweg), [Gitleaks](.github/workflows/gitleaks.yml) + [`.gitleaks.toml`](.gitleaks.toml).
- **Release-Tag:** Der Tag `v0.1.0` wird erst gesetzt, nachdem der Staging-E2E-Lauf (G4) erfolgreich abgeschlossen wurde — Checkliste [`docs/ghost_staging_e2e.md`](docs/ghost_staging_e2e.md), Details [`docs/RELEASE.md`](docs/RELEASE.md).

### Pilot (operativ): Gitleaks, ein E2E-Flow, Support-Scope

**A — Gitleaks (Blocker vor Pilot):** Der Workflow [`.github/workflows/gitleaks.yml`](.github/workflows/gitleaks.yml) muss **grün** sein — sonst kein Pilot (Governance / Audit / Vertrauen). Bei Rot: lokal `gitleaks detect --source . --config .gitleaks.toml` ausführen und Befund klären, bevor ihr Kunden einbindet.

**B — Ein End-to-End-Flow (Readiness-Test):** Voraussetzung: erreichbare **Arctis-API**, **`ARCTIS_API_KEY`**, gültige **`workflow_id`** in `ghost.yaml` (nach `init-demo`). Dann im **Ghost-Arbeitsverzeichnis**:

```bash
ghost init-demo
ghost doctor
ghost run input.json
ghost pull-artifacts <run_id>
ghost verify <run_id>
```

(`<run_id>` = Ausgabe von `ghost run`.) Wenn diese Kette funktioniert, ist **Ghost für diesen Pfad** produktiv nutzbar — wichtiger als jede Prozentzahl. Erweiterungen (z. B. `watch` / `explain`): [`docs/arctis_ghost_demo_60.md`](docs/arctis_ghost_demo_60.md).

**C — Support-Scope (Kurz):**

| Thema | Was wir supporten (Open-Source / Pilot) |
|--------|----------------------------------------|
| **OS** | **Windows, Linux, macOS** (best effort), wo **Python 3.11+** läuft und die API erreichbar ist; unter Windows bei Bedarf `python -m arctis_ghost …` statt `ghost`. |
| **Python** | **3.11+** wie in [`pyproject.toml`](pyproject.toml) — das ist der Referenzrahmen für Ghost. |
| **Ghost** | Nur die **dokumentierte CLI** gegen **eure** Arctis-API ([`docs/ghost_cli_reference.md`](docs/ghost_cli_reference.md)) — **keine** Engine im Client, nur HTTP und lokale Artefakte. |
| **Full-Stack** | **API + DB + Betrieb** nur im Umfang von [`docs/Deployment.md`](docs/Deployment.md) und [`docs/security_production.md`](docs/security_production.md) — kein implizites globales SaaS, es sei denn, ihr betreibt es selbst und sagt das so. |

### Verzeichnisse und Kanonik (Ghost)

**Festgelegt: Option A** — eine dokumentierte Layout-Wahrheit für Ghost-Kunden-Workflows; kein zusätzliches `sandbox/`-Verzeichnis im Repository (dafür genügt ein beliebiger Zielordner für `ghost init-demo`).

| Bereich | Inhalt |
|--------|--------|
| **Ghost-Arbeitsverzeichnis** | Beliebiger Ordner deiner Wahl (z. B. Ziel von `ghost init-demo`). Darin: `ghost.yaml`, Payload-Datei(en) — bei der Demo z. B. `input.json` im Ordnerroot (Scaffold: [`arctis_ghost/init_demo.py`](arctis_ghost/init_demo.py)) — sowie nach [`ghost pull-artifacts`](docs/ghost_cli_reference.md) die Artefakte unter **`outgoing/<run_id>/`** (Standard, konfigurierbar über `outgoing_root` / `ARCTIS_GHOST_OUTGOING_ROOT`). Optional ein lokales **`output/`**, falls ihr so arbeitet; das ist unabhängig vom Repo. |
| **Repo-Root [`input/`](input/README.md) und [`output/`](output/README.md)** | Nur **Harness- und Test-Tasks** (nummerierte Ordner `001_…`–`021_…`, Golden Outputs). **Nicht** dasselbe wie der Ghost-Demo-Ordner — dort legt ihr eigene Dateien an, ohne diese Test-Fixtures zu verwenden. |

**Hinweis zu älteren Begriffen:** In einigen Plan- und Roadmap-Dokumenten taucht **`incoming/`** als Hot-Folder-Idee auf. Die **kanonische Ghost-CLI** nutzt aktuell Payload-Dateien + `pull-artifacts` → `outgoing/…`, nicht ein Repo-verankertes `incoming/`. Details: [`docs/ghost_quickstart.md`](docs/ghost_quickstart.md).

---

## Ghost CLI (Quickstart)

**Python 3.11+**, im Repo-Root:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Konsole: `ghost` (Entry-Point aus `pyproject.toml`). Unter Windows ggf. `python -m arctis_ghost …` nutzen, wenn `ghost` nicht im `PATH` steht.

### Try Arctis in 30 seconds

Diese **sechs Schritte** sind die kanonische **Erstkontakt-Sequenz** (PLG); sie entsprechen dem technischen Walkthrough in [`docs/demo_60.md`](docs/demo_60.md) und dem **60‑Sekunden**-Storyboard in [`docs/arctis_ghost_demo_60.md`](docs/arctis_ghost_demo_60.md) (Erzählzeit ≠ reine Terminalzeit).

Voraussetzung: **Python 3.11+**, erreichbare **Arctis-API** (lokal oder Staging), **`ARCTIS_API_KEY`** und eine gültige **`workflow_id`** im Tenant (in `ghost.yaml` eintragen, Platzhalter `0000…` ersetzen).

1. `pip install -e ".[dev]"` im Repo-Root.
2. Leeren Ordner wählen, darin: `ghost init-demo` → erzeugt `ghost.yaml`, `input.json`, `README.md`.
3. `export ARCTIS_API_KEY=…` (oder Windows-Äquivalent) und `workflow_id` in `ghost.yaml` setzen.
4. `ghost doctor` — bei laufender API sollte `/health` grün sein.
5. `ghost run input.json` → **Run-ID** kopieren.
6. `ghost watch <run_id>` · `ghost explain <run_id>` · `ghost pull-artifacts <run_id>` · `ghost verify <run_id>`.

Details und Storyboard (60 s Erzählung): [`docs/arctis_ghost_demo_60.md`](docs/arctis_ghost_demo_60.md). Kommando-genau: [`docs/demo_60.md`](docs/demo_60.md). Beispiel-Terminalauszug: [`docs/assets/ghost_demo_flow_sample.txt`](docs/assets/ghost_demo_flow_sample.txt).

### Customer-Execute (Kern-Story)

**Ein Satz:** `ghost run` mit einem **Execute-Body** (JSON-Datei) → **`ghost pull-artifacts <run_id>`** → **`ghost verify <run_id>`** — ohne Engine im Client, nur HTTP und lokale Artefakte.

| Schritt | Befehl / Artefakt |
|--------|-------------------|
| 1 | `ghost.yaml` + Body-JSON im selben Arbeitsverzeichnis (frisch: `ghost init-demo` legt `input.json` an — gleiches Schema wie [`docs/examples/customer_execute_body.json`](docs/examples/customer_execute_body.json)). |
| 2 | `ghost run body.json` — stdout: **Run-ID**. |
| 3 | `ghost pull-artifacts <run_id>` — u. a. `outgoing/<run_id>/envelope.json`. |
| 4 | `ghost verify <run_id>` — muss nach `pull-artifacts` laufen. |

Nummerierte Liste und Diagramm: [`docs/ghost_quickstart.md#customer-execute-von-null-bis-verify`](docs/ghost_quickstart.md#customer-execute-von-null-bis-verify). **Alle Flags und Policy-Details:** [`docs/ghost_cli_reference.md`](docs/ghost_cli_reference.md).

### In fünf Schritten

1. **Demo-Ordner anlegen:** `ghost init-demo` (optional Zielpfad; siehe `ghost init-demo --help`).
2. **Konfiguration:** `ghost.yaml` im Arbeitsverzeichnis oder Umgebungsvariablen — siehe [`docs/ghost_cli_reference.md`](docs/ghost_cli_reference.md). **API-Key** bevorzugt als `ARCTIS_API_KEY`, nicht im Klartext in YAML committen.
3. **Smoke-Test:** `ghost doctor` — Erreichbarkeit der API (`/health`), optional authentifizierter Check.
4. **Run:** `ghost run body.json` oder mit `--recipe recipe.yaml` und `--input` — siehe Referenz.
5. **Artefakte & Prüfung:** `ghost pull-artifacts <run_id>` → `outgoing/<run_id>/`; danach `ghost verify <run_id>`.

Kurzreferenz (Kanonik + Mindest-Commands): [`docs/ghost_quickstart.md`](docs/ghost_quickstart.md).  
Demo-Storyboard (60s): [`docs/arctis_ghost_demo_60.md`](docs/arctis_ghost_demo_60.md).  
Staging-Checkliste: [`docs/ghost_staging_e2e.md`](docs/ghost_staging_e2e.md).

---

## API-Server (lokal)

```bash
pip install -e ".[dev]"
uvicorn arctis.app:create_app --factory --host 0.0.0.0 --port 8000
```

Produktions- und Security-Hinweise: [`docs/security_production.md`](docs/security_production.md), Deployment: [`docs/Deployment.md`](docs/Deployment.md).

---

## Pipeline A (IR, UI, Tests)

Python-Bibliothek und Mock-UI für **Pipeline A**: IR-Kompilierung, Engine-Runtime, Control-Plane-Stores und eine browser-lokale Demo.

### Setup

**Python** (3.11+):

```bash
python -m pip install ruff
```

Optional: Test-Extras — `pip install -e ".[dev]"`.

**UI** (`ui/pipeline_a/`):

```bash
cd ui/pipeline_a
npm install
```

### Tests

**Alle** (Python + UI):

```bash
npm test
# oder
make test
```

**Python (Pipeline A + core):**

```bash
python -m pytest tests/integration tests/unit
```

Die vollständige `tests/`-Baumstruktur kann zusätzliche Compliance- oder Platzhalterfälle enthalten; für einen CI-ähnlichen grünen Pfad siehe [`CONTRIBUTING.md`](CONTRIBUTING.md) (Ghost-Subset) bzw. die obigen Pfade.

**UI only:**

```bash
cd ui/pipeline_a && npm test
```

### Demo (sandbox reset)

```bash
npm run demo
# oder
make demo
python scripts/dev_reset_demo.py
```

### UI (Dev-Server)

```bash
npm run dev
# oder
make dev
# oder
cd ui/pipeline_a && npm run dev
```

Dann die URL öffnen, die Vite ausgibt (typisch `http://localhost:5173`).

### Linting

```bash
npm run lint
# oder
make lint
```

Python: [Ruff](https://docs.astral.sh/ruff/). UI: ESLint in `ui/pipeline_a/`.

---

## Launch-Orchestrierung (A0 → A4)

**Source of Truth** für Agent- und Team-Workflows (Phasen, Gates, Owner, Commit-/Stop-Policy, Scorecard):

→ [`docs/agent_prompt_plan_launch_a0_a4.md`](docs/agent_prompt_plan_launch_a0_a4.md)

---

## Dokumentation

- Pipeline A (Entwickler): [`docs/pipeline_a/README.md`](docs/pipeline_a/README.md)
- Normative Pipeline-A-Spezifikation: `docs/pipeline-a-v1.3.md`
- Ghost Quickstart (Kanonik): [`docs/ghost_quickstart.md`](docs/ghost_quickstart.md)
- Customer-Execute-Beispiel (`body.json`): [`docs/examples/customer_execute_body.json`](docs/examples/customer_execute_body.json)
- Ghost Demo-Terminalbeispiel: [`docs/assets/ghost_demo_flow_sample.txt`](docs/assets/ghost_demo_flow_sample.txt)
- Ghost-CLI-Referenz: [`docs/ghost_cli_reference.md`](docs/ghost_cli_reference.md)
- Mitwirkung & CI lokal: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Release & Tags: [`docs/RELEASE.md`](docs/RELEASE.md)
- Auth & Identity (A1.3): [`docs/Authentication.md`](docs/Authentication.md)
- Observability (A1.4): [`docs/Observability.md`](docs/Observability.md)
- Disaster Recovery & Backup (A1.5): [`docs/DR.md`](docs/DR.md)
- Launch gates (A1.6): [`docs/Launch_readiness.md`](docs/Launch_readiness.md)
- Packaging & Delivery (A2): [`docs/Packaging.md`](docs/Packaging.md)
- Customer Onboarding Kit (A2.4): [`docs/customer/README.md`](docs/customer/README.md)
- Commercial Readiness (A3): [`docs/commercial/README.md`](docs/commercial/README.md)
- Pilot & Post-Launch (A4): [`docs/pilot/README.md`](docs/pilot/README.md)
- Sustain & Evolve (A5): [`docs/a5/README.md`](docs/a5/README.md)

## Control Plane API (optional Launch-Umgebung)

Beim Betrieb der FastAPI-App (`uvicorn arctis.app:create_app --factory`) u. a.:

- **LLM (Dashboard):** `ARCTIS_ENCRYPTION_KEY` — Fernet-Key; nötig für `POST /llm-config` und Tenant-LLM-Key-Speicher.
- **Stripe:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, … — Billing unter `/billing/*`.
- **Sentry:** `SENTRY_DSN`
- **Prometheus:** Scrape **`GET /metrics/prometheus`** mit **`X-API-Key`** (Scope `tenant_admin` oder `system_admin`) — siehe [`docs/Observability.md`](docs/Observability.md)

**Produktion:** migrierte Datenbank (`alembic upgrade head` mit `DATABASE_URL`) — siehe [`docs/Deployment.md`](docs/Deployment.md). Kein `create_all()` für das Hauptschema in Produktion.

## Optional: pre-commit

```bash
pip install pre-commit
pre-commit install
```

Nutzt `.pre-commit-config.yaml` im Repo-Root (Ruff + UI ESLint).
