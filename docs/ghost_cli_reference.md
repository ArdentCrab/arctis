# Ghost CLI — Referenz (Sicherheit & Verhalten)

Programm: `python -m arctis_ghost.cli` bzw. installiertes `ghost`-Konsolen-Skript (Projektsetup abhängig).

## P10 — Client-Sandbox (Pilot)

- **Pfad- und Größenregeln** (siehe unten) gelten vor jedem `run`.
- **`ghost run --dry-run`:** baut den Execute-Body wie bei einem echten Lauf (Rezept/JSON, Merge), prüft Limits und Pfade, gibt **keinen** POST ab. Auf **stderr:** Hinweis, `effective_workflow_id`, würde-POST-URL; auf **stdout:** formatiertes JSON des Bodies (wie `print_json`). Kein State-Write, kein `ghost_run`.

## P11 — Heartbeat / Remote (opt-in)

- **`ghost heartbeat`** — kein Dauerprozess: führt **1–100000** Iterationen mit Pause **`--interval`** (Sekunden; Default aus Profil, sonst 30) aus.
- **`--url URL`:** `GET` pro Tick (nur `http`/`https`).
- **`--use-api-health`:** `GET {api_base_url}/health` (wie `doctor`).
- **`--metrics-file PATH`:** jede Iteration eine **NDJSON**-Zeile unter CWD (Pfadregeln wie bei `run`).
- Kombinationen: URL und/oder Health und/oder Metrikdatei; ohne mindestens eine Quelle bricht die CLI mit Fehler ab.
- **Profil / Env:** `heartbeat_url`, `heartbeat_metrics_file`, `heartbeat_interval_seconds` im YAML; `ARCTIS_GHOST_HEARTBEAT_URL`, `ARCTIS_GHOST_HEARTBEAT_METRICS_FILE`, `ARCTIS_GHOST_HEARTBEAT_INTERVAL`.
- **Tests / Matrix:** [`ghost_p11_test_matrix.md`](ghost_p11_test_matrix.md).

## P12 — Profil-Recipe, Auto-Recipe, lokales Verify

- **`profiles.<name>.default_recipe`** (YAML) und **`ARCTIS_GHOST_DEFAULT_RECIPE`** (Env): wenn `ghost run` **ohne** `--recipe` aufgerufen wird, gilt dieser Pfad wie `--recipe <Pfad>` (Eingabedatei weiterhin Positional oder `--input`).
- **`ghost run --raw-json`:** die JSON-Datei ist der **vollständige** Execute-Body; Profil-`default_recipe` und Auto-Recipe werden ignoriert.
- **Auto-Recipe (opt-in):** `--auto-recipe` oder **`ARCTIS_GHOST_AUTO_RECIPE=1`** (bzw. `true`/`yes`/`on`): fehlen `--recipe` und Profil-Default, wird nacheinander geprüft: `recipe.yaml` im CWD, sonst `recipes/<cwd-basename>.yaml`. Nur dokumentierte Heuristik, kein Policy-Engine.
- **`ghost verify RUN_ID`:** lädt `GET /runs/{id}`, vergleicht die gleichen Felder wie `pull-artifacts` → `envelope.json` (ohne `generated_at`): `schema_version`, `run_id`, `skill_report_keys`, `status`, optional `branding` (aktueller `GhostConfig`). Standardpfad: `outgoing_root/<run_id>/envelope.json`; Override: **`--envelope PATH`** (relativ zur CWD).
- **Tests / Matrix:** [`ghost_p12_test_matrix.md`](ghost_p12_test_matrix.md).

## P13 — Meta / Roadmap (Epic K light, §15.12–15.15)

- **`ghost meta`** — read-only: schreibt **JSON** auf stdout (`schema_version`, `kind: ghost_meta`, aufgelöste **nicht-geheime** Config, Python/Plattform, optional **Distribution-Version**). **Kein** API-Key und kein zusätzlicher HTTP-Call.
- **Predict / Replay:** in der Ausgabe unter `capabilities` mit Label **Roadmap** — nicht in der Ghost-CLI implementiert.
- **Multi-Region:** Label **Pilot** — nur ein `api_base_url`; kein Client-Failover zwischen Regionen ohne Backend.
- **Roadmap-Tabelle:** [`ghost_p13_roadmap.md`](ghost_p13_roadmap.md) · **Tests / Matrix:** [`ghost_p13_test_matrix.md`](ghost_p13_test_matrix.md).

## P14 — Lifecycle Hooks (§15.9, Pilot)

- Optional **`hook_pre_run`**, **`hook_post_run`**, **`hook_on_error`** (Profil oder `ARCTIS_GHOST_HOOK_*`); **`hook_timeout_seconds`** / **`ARCTIS_GHOST_HOOK_TIMEOUT`** (0.5–600 s).
- Subprocess mit Timeout; **stdin:** JSON (`hook`, `workflow_id`, `execute_body`, …). **Kein** Ersatz für Server-Policy.
- **`pre_run`** blockiert bei Exit ≠ 0; **`post_run`** / **`on_error`** nur Warnung bei Hook-Fehler.
- **`ghost run --dry-run`** und State-Reuse (Cache-Treffer ohne POST) führen **keine** Hooks aus bzw. keinen neuen Lauf.
- Sicherheit und Details: [`ghost_hooks_p14.md`](ghost_hooks_p14.md) · **Tests / Matrix:** [`ghost_p14_test_matrix.md`](ghost_p14_test_matrix.md).

## Sicherheitsrelevante Flags

| Befehl | Flag | Bedeutung |
|--------|------|-----------|
| `heartbeat` | `--url` / `--use-api-health` / `--metrics-file` | P11: Ping und/oder lokale Metrik-Zeilen (siehe Abschnitt P11). |
| `heartbeat` | `--count`, `--interval` | Anzahl Ticks und Abstand in Sekunden. |
| `run` | `--dry-run` | Nur validieren und Body ausgeben; kein HTTP (P10). |
| `run` | `--raw-json` | Voller Execute-Body aus der Datei; ignoriert Profil-Recipe und Auto-Recipe (P12). |
| `run` | `--auto-recipe` | P12: Rezept-Heuristik aus CWD (siehe Abschnitt P12). |
| `run` | `--no-hooks` | P14: keine Lifecycle-Hooks für diesen Lauf. |
| `verify` | `--envelope` | P12: Pfad zu `envelope.json` (default: `outgoing_root/<run_id>/envelope.json`). |
| `meta` | — | P13: JSON-Introspection (keine Secrets, kein Netz). |
| `run` | `--force` | Ignoriert lokalen State-Cache und sendet erneut einen Execute-POST. |
| `pull-artifacts` | `--force` | Überschreibt ein vorhandenes Verzeichnis `outgoing/<run_id>/`. |
| `init-demo` | `--force` | Überschreibt Demo-Dateien im Zielordner. |

## Pfad-Regeln

- Argumente **`--recipe`**, **`--input`**, **`--merge-json`** und die JSON-Datei bei `run` ohne Rezept: Pfade müssen **relativ zum aktuellen Arbeitsverzeichnis** sein.
- **Absolute Pfade** werden abgelehnt (`GhostPathError`).
- Auflösung mit `Path.resolve()`; Verzeichniswechsel außerhalb der CWD-Basis (z. B. `..`) → **Fehler**.

## Eingabe-Limits

| Art | Limit | Fehler |
|-----|-------|--------|
| JSON-Dateien (`run` body, `merge-json`, Rezept-Input `mode=json`) | 1 MiB | `GhostInputError` / `GhostRecipeError` |
| Rezept-YAML, Text-Input (`mode=text`) | 5 MiB | `GhostRecipeError` |

Konstanten: `arctis_ghost.input_limits`.

## Konfiguration (`ghost.yaml` + Env)

- **`api_key` in YAML:** beim Laden erscheint eine **`UserWarning`** — Klartext auf der Platte; bevorzugt **`ARCTIS_API_KEY`** setzen.
- Profile: `active_profile`, `profiles.<name>.…` — siehe `arctis_ghost.config`.

## State-Dateien (`.ghost/state`)

- Gespeicherte Mappings (Fingerprint → `run_id`) sind **nicht verschlüsselt**.
- Nach Schreiben: auf POSIX **chmod 0600** (best effort).

## Artefakte (`outgoing/`)

- `write_run_artifacts`: legt `envelope.json`, `skill_reports/*.json`, optional `routing.json`, `cost.json` an.
- **Kein Überschreiben** ohne `pull-artifacts --force`.
- **`branding`** in `envelope.json`: nur dokumentarische Felder (`envelope_audited_by`, `envelope_branding_version`); **keine sensiblen Daten** eintragen.

## Status-Datei (`__STATUS.txt`)

- Enthält u. a. `last_artifact_run_id` und optionale **user note** — **keine PII** in `plg_status_note` / Umgebungs-Override.

## HTTP-Client

- Basis-URL, Retries, Idempotency-Key: siehe `GhostConfig` und Client-Modul.
- API-Keys und Antworten nicht in zusätzliche Logdateien schreiben.

## Tests

- Pfad- und Größen-Tests: `tests/ghost/test_paths_security.py`, Rezept-/CLI-Tests unter `tests/ghost/`.
