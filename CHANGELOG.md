# Changelog

Alle wichtigen Änderungen an diesem Repository werden hier dokumentiert.  
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), die Versionierung an [SemVer](https://semver.org/lang/de/).

## [Unreleased]

## [0.1.1] — 2026-03-29

Paketversion in [`pyproject.toml`](pyproject.toml): **0.1.1**.

### Added

- **Docker publish:** `workflow_dispatch` — Image kann in **Actions → Docker publish → Run workflow** gebaut und nach GHCR gepusht werden, ohne neuen Git-Tag (Tags aus `pyproject.toml`-Version).

### Fixed

- Erster GHCR-Build: Workflows laufen zuverlässig nach **neuem Tag** `v0.1.1` (oder manuell wie oben).

## [0.1.0] — 2026-03-29

Paketversion in [`pyproject.toml`](pyproject.toml): **0.1.0**.

### Added

- **CI/CD:** GitHub Actions [`.github/workflows/release.yml`](.github/workflows/release.yml) (Wheel, sdist, `SHA256SUMS`, GitHub Release) und [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) (Push nach **GHCR**, Multi-Arch `linux/amd64` + `linux/arm64`, SBOM + Provenance).
- **G0 (Finalisierung):** `CHANGELOG.md`, `docs/RELEASE.md`, GitHub Actions CI (Ruff + `pytest tests/ghost/`), erweitertes Root-`README` (Ghost-Quickstart), `CONTRIBUTING.md`, `docs/ghost_staging_e2e.md`, `docs/arctis_package_strategy.md`, `pyproject.toml`-Metadaten (`readme`, Keywords/Classifier, `project.urls`).
- **API / Backend:** FastAPI-App, Kunden-Execute, Runs, Skills-Pipeline (siehe Repo und `docs/`).
- **Ghost CLI (`arctis_ghost`):** `ghost` Entry-Point; Kommandos u. a. `run`, `doctor`, `fetch`, `watch`, `pull-artifacts`, `verify`, `meta`, Heartbeat, Lifecycle-Hooks (P1–P14 abgeschlossen — siehe `docs/ghost_implementation_prompts.md`).

### Changed

- **Dockerfile:** Build-Kontext um `arctis_ghost` und `README.md` ergänzt, damit das Image dem Wheel entspricht.
- Dokumentationsverweise zwischen Security- und Ghost-Dokumenten ergänzt (`docs/security_production.md`).
- **Git/GitHub:** `.gitignore` um `.ghost/`; README/RELEASE/G4-Status-Block; Tag-Gate G4; CONTRIBUTING (Ruff-Scope, erster Commit, CI-Hinweis); CI-Workflow-Kommentar (kein Ruff auf `arctis/`).
- **G0-Dokumentations-Finalisierung:** README (GitHub Actions + Tag `v0.1.0` nach G4), `ghost_staging_e2e.md` Statusblock, Ruff-Step-Kommentar in CI.

### Notes

- Breaking-Änderungen an API oder `ghost.yaml`-Schema künftig unter `[Unreleased]` → **Changed** / **Removed** mit Migrationshinweis dokumentieren.

<!-- Releases: https://github.com/arctis-engine/arctis/releases -->
