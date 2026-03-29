# Mitwirken (Arctis)

## Git-Repository (lokal)

Falls im Projektordner noch kein Git läuft:

```bash
git init
git add -A
git status   # prüfen, dass u. a. .venv/ und .ghost/ nicht getrackt werden
git commit -m "G0: GitHub-Setup, Release-Hinweise, G4-Status, Ruff-Scope"
```

Remote auf GitHub anlegen, dann `git remote add origin …` und pushen. **GitHub Actions** laufen danach bei Push und auf Pull Requests automatisch (siehe [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Voraussetzungen

- **Python 3.11+** (siehe `pyproject.toml` → `requires-python`).
- Optional: **Node/npm** für die Pipeline-A-UI unter `ui/pipeline_a/` (siehe Root-`README.md`).

## Lokale Entwicklung (Python)

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Ghost-CLI lokal spiegeln (CI-Subset)

Die GitHub Action **CI** führt aus:

```bash
ruff check arctis_ghost tests/ghost scripts
python -m pytest tests/ghost/ -q
```

CI lintet aktuell nur `arctis_ghost/`, `tests/ghost/` und `scripts/`.  
Das Engine-Paket `arctis/` wird später in einem eigenen Schritt auf Voll-Ruff erweitert.

## Lockfile erneuern

Nach Änderungen an Abhängigkeiten in `pyproject.toml`:

- Linux/macOS: `bash scripts/generate_requirements_lock.sh`
- Windows: `powershell -File scripts/generate_requirements_lock.ps1`

Details: [`docs/security_production.md`](docs/security_production.md) (Abschnitt Supply-Chain).

## Release

Siehe [`docs/RELEASE.md`](docs/RELEASE.md) und [`CHANGELOG.md`](CHANGELOG.md).
