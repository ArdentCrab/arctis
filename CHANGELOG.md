# Changelog

Alle wichtigen Änderungen an diesem Repository werden hier dokumentiert.  
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), die Versionierung an [SemVer](https://semver.org/lang/de/).

## [Unreleased]

### Added

- **G0 (Finalisierung):** `CHANGELOG.md`, `docs/RELEASE.md`, GitHub Actions CI (Ruff + `pytest tests/ghost/`), erweitertes Root-`README` (Ghost-Quickstart), `CONTRIBUTING.md`, `docs/ghost_staging_e2e.md`, `docs/arctis_package_strategy.md`, `pyproject.toml`-Metadaten (`readme`, `urls`, Keywords/Classifier).

### Changed

- Dokumentationsverweise zwischen Security- und Ghost-Dokumenten ergänzt (`docs/security_production.md`).
- **Git/GitHub:** `.gitignore` um `.ghost/`; README/RELEASE/G4-Status-Block; Tag-Gate G4; CONTRIBUTING (Ruff-Scope, erster Commit, CI-Hinweis); CI-Workflow-Kommentar (kein Ruff auf `arctis/`).
- **G0-Dokumentations-Finalisierung:** README (exakte Hinweise GitHub Actions + Tag `v0.1.0` nach G4), `ghost_staging_e2e.md` Statusblock, Ruff-Step-Kommentar in CI.

## [0.1.0] — 2026-03-28

Erster in diesem CHANGELOG geführter Release-Schnappschuss (Paketversion in `pyproject.toml`: **0.1.0**).

### Added (Überblick)

- **API / Backend:** FastAPI-App, Kunden-Execute, Runs, Skills-Pipeline (siehe Repo und `docs/`).
- **Ghost CLI (`arctis_ghost`):** `ghost` Entry-Point; Kommandos u. a. `run`, `doctor`, `fetch`, `watch`, `pull-artifacts`, `verify`, `meta`, Heartbeat, Lifecycle-Hooks (P1–P14 abgeschlossen — siehe `docs/ghost_implementation_prompts.md`).

### Notes

- Breaking-Änderungen an API oder `ghost.yaml`-Schema künftig unter `[Unreleased]` → **Changed** / **Removed** mit Migrationshinweis dokumentieren.

<!-- Nach erstem öffentlichen Repo: Compare-URLs hier eintragen. -->
