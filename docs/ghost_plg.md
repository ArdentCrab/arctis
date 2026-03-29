# Ghost — lokales PLG / Branding (P8)

**Zweck:** Optionale, **lokale** Hinweise für Demos und Ordner-Workflows. **Kein** Ersatz für API-Quotas, Verträge oder Signatur.

## `envelope.json` (Writer / `ghost pull-artifacts`)

Wenn in `ghost.yaml` (Profil) oder per Umgebung gesetzt, schreibt der Writer einen Block **`branding`** (nur wenn mindestens ein Feld nicht leer ist):

| Feld im JSON | Quelle (YAML / Env) |
|----------------|---------------------|
| `branding.audited_by` | `envelope_audited_by` / `ARCTIS_GHOST_ENVELOPE_AUDITED_BY` |
| `branding.branding_version` | `envelope_branding_version` / `ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION` |
| `branding.schema_version` | fest `"1.0"` (Format des Branding-Blocks) |

Leere Strings → kein `branding`-Schlüssel (Defaults bleiben harmlos).

## `__STATUS.txt` (unter `outgoing_root`)

Nach jedem **`ghost pull-artifacts`** wird (sofern nicht abgeschaltet) **`outgoing_root/__STATUS.txt`** überschrieben: letzte Run-ID, Kurzdisclaimer, optional **`plg_status_note`** / `ARCTIS_GHOST_PLG_STATUS_NOTE`.

| YAML | Env |
|------|-----|
| `plg_status_note` | `ARCTIS_GHOST_PLG_STATUS_NOTE` |
| `plg_status_file_enabled: false` | `ARCTIS_GHOST_PLG_STATUS_FILE=off` |

## Code

- `arctis_ghost.limits.freemium` — Textzeilen für die Status-Datei (Stub, erweiterbar).
- `arctis_ghost.writer` — `write_run_artifacts(..., cfg=)`, `write_plg_status_file(...)`.

Weitere Einordnung: [demo_matrix.md](demo_matrix.md), [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) §8.
