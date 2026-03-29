# Arctis

Python-Paket für **Pipeline A** (IR, Engine-Runtime, Control-Plane) sowie die **FastAPI-Arctis-API** und die **Ghost-CLI** — ein HTTP-only Client für Customer-Execute, Runs und lokale Artefakte (**kein** direkter Engine-Import aus Ghost).

- **Version:** siehe [`pyproject.toml`](pyproject.toml) — aktuell **0.1.0** ([`CHANGELOG.md`](CHANGELOG.md)).
- **Paketinhalt:** ein Wheel umfasst API-, Engine- und Ghost-Code; Strategie für Publish/Split siehe [`docs/arctis_package_strategy.md`](docs/arctis_package_strategy.md).
- **CI:** GitHub Actions laufen automatisch, sobald das Repository auf GitHub gepusht wird. (Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — u. a. Pull Requests und Push auf `main`/`master`.)
- **Release-Tag:** Der Tag `v0.1.0` wird erst gesetzt, nachdem der Staging-E2E-Lauf (G4) erfolgreich abgeschlossen wurde — Checkliste [`docs/ghost_staging_e2e.md`](docs/ghost_staging_e2e.md), Details [`docs/RELEASE.md`](docs/RELEASE.md).

---

## Ghost CLI (Quickstart)

**Python 3.11+**, im Repo-Root:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Konsole: `ghost` (Entry-Point aus `pyproject.toml`).

### In fünf Schritten

1. **Demo-Ordner anlegen:** `ghost init-demo` (optional Zielpfad; siehe `ghost init-demo --help`).
2. **Konfiguration:** `ghost.yaml` im Arbeitsverzeichnis oder Umgebungsvariablen — siehe [`docs/ghost_cli_reference.md`](docs/ghost_cli_reference.md). **API-Key** bevorzugt als `ARCTIS_API_KEY`, nicht im Klartext in YAML committen.
3. **Smoke-Test:** `ghost doctor` — Erreichbarkeit der API (`/health`), optional authentifizierter Check.
4. **Run:** `ghost run body.json` oder mit `--recipe recipe.yaml` und `--input` — siehe Referenz.
5. **Artefakte & Prüfung:** `ghost pull-artifacts <run_id>` → `outgoing/<run_id>/`; danach `ghost verify <run_id>`.

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

## Dokumentation

- Pipeline A (Entwickler): [`docs/pipeline_a/README.md`](docs/pipeline_a/README.md)
- Normative Pipeline-A-Spezifikation: `docs/pipeline-a-v1.3.md`
- Ghost-CLI-Referenz: [`docs/ghost_cli_reference.md`](docs/ghost_cli_reference.md)
- Mitwirkung & CI lokal: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Release & Tags: [`docs/RELEASE.md`](docs/RELEASE.md)

## Control Plane API (optional Launch-Umgebung)

Beim Betrieb der FastAPI-App (`uvicorn arctis.app:create_app --factory`) u. a.:

- **LLM (Dashboard):** `ARCTIS_ENCRYPTION_KEY` — Fernet-Key; nötig für `POST /llm-config` und Tenant-LLM-Key-Speicher.
- **Stripe:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, … — Billing unter `/billing/*`.
- **Sentry:** `SENTRY_DSN`
- **Prometheus:** `PROMETHEUS_ENABLED=true` → `GET /metrics`

**Produktion:** migrierte Datenbank (`alembic upgrade head` mit `DATABASE_URL`) — siehe [`docs/Deployment.md`](docs/Deployment.md). Kein `create_all()` für das Hauptschema in Produktion.

## Optional: pre-commit

```bash
pip install pre-commit
pre-commit install
```

Nutzt `.pre-commit-config.yaml` im Repo-Root (Ruff + UI ESLint).
