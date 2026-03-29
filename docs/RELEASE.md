# Release-Prozess (Arctis)

## Tag `v0.1.0` und G4

- **Tag-Schema:** `v` + Version aus `pyproject.toml`, z. B. **`v0.1.0`**.
- **`v0.1.0` erst setzen**, wenn der **Staging-E2E-Lauf (G4)** mindestens einmal **erfolgreich** durchgelaufen ist — siehe [`ghost_staging_e2e.md`](ghost_staging_e2e.md). Vorher keinen Release-Tag für diese Version auf `main`/`master` pushen, wenn ihr G4 als Gate nutzt.

## Versionierung

- **Schema:** [Semantic Versioning](https://semver.org/) — `MAJOR.MINOR.PATCH`.
- **Quelle der Wahrheit:** `[project] version` in [`pyproject.toml`](../pyproject.toml).
- **Vorab-Builds:** optional `0.2.0-dev1` / `.devN` nach Team-Konvention — im CHANGELOG im Abschnitt **[Unreleased]** sammeln, bis ein Release-Tag gesetzt wird.

## Git-Tag

- Empfehlung: Tag-Name **`v` + Version**, z. B. `v0.1.0` (entspricht der Version in `pyproject.toml`).
- Tag auf dem Commit, der exakt die veröffentlichte `pyproject.toml`-Version enthält.

## Ablauf (kurz)

1. Einträge aus **[Unreleased]** in [`CHANGELOG.md`](../CHANGELOG.md) unter eine neue Versionsüberschrift verschieben (Datum + Version).
2. `pyproject.toml`-Version anheben (falls noch nicht geschehen).
3. PR reviewen und mergen.
4. Nach erfolgreichem **G4** (falls als Gate vereinbart): Tag setzen — `git tag -a vX.Y.Z -m "Release X.Y.Z"` und pushen.
5. Release-Notes (GitHub/GitLab): Breaking Changes, API vs. Ghost-CLI, Sicherheitshinweise; optional Links zu [`arctis_ghost_demo_60.md`](arctis_ghost_demo_60.md) / Demo-Matrix.

## Ghost-CLI

- Neue Flags oder `ghost.yaml`-Felder: im CHANGELOG unter **Added**/**Changed** erwähnen; Verweis auf [`ghost_cli_reference.md`](ghost_cli_reference.md).
