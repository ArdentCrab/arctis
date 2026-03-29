# Ghost P14 — Lifecycle Hooks (§15.9)

**Status:** Pilot — subprocess-only, **keine** parallele Policy-Engine und kein Ersatz für serverseitige Governance.

## Konfiguration

| Quelle | Felder / Variablen |
|--------|---------------------|
| Profil (`ghost.yaml`) | `hook_pre_run`, `hook_post_run`, `hook_on_error` (Pfade **relativ zur CWD**), `hook_timeout_seconds` (0.5–600) |
| Umgebung | `ARCTIS_GHOST_HOOK_PRE_RUN`, `ARCTIS_GHOST_HOOK_POST_RUN`, `ARCTIS_GHOST_HOOK_ON_ERROR`, `ARCTIS_GHOST_HOOK_TIMEOUT` |

CLI: `ghost run --no-hooks` überspringt alle Hooks für diesen Lauf.

## Semantik

| Phase | Wann | Verhalten bei Exit ≠ 0 |
|--------|------|---------------------------|
| `pre_run` | Vor `POST …/execute` (nicht bei `--dry-run`, nicht bei State-Reuse ohne POST) | **Abbruch**, kein Execute |
| `post_run` | Nach erfolgreichem Execute | Warnung auf stderr, CLI-Exit bleibt 0 |
| `on_error` | Nach fehlgeschlagenem `ghost_run` (HTTP/OS) | Warnung bei Fehler/Timeout des Hooks |

## Prozess

- Auführung als **Subprocess** mit **`subprocess.run(..., timeout=…)`** (konfigurierbar).
- **Stdin:** eine JSON-Zeile mit u. a. `hook`, `workflow_id`, `execute_body`, optional `run_id`, `error`, `ghost_exit_code`.
- **Umgebung:** zusätzlich `ARCTIS_GHOST_HOOK`, `ARCTIS_GHOST_WORKFLOW_ID`, bei Bedarf `ARCTIS_GHOST_RUN_ID`.
- **`.py`-Skripte** werden mit dem gleichen Python-Interpreter wie die CLI gestartet (`sys.executable`); andere Pfade werden als ausführbare Kommandozeile übergeben (Plattformabhängig).

## Sicherheit (Pflichtlektüre für Betrieb)

- Hooks sind **beliebiger Code** mit Rechten des Benutzers — nur vertrauenswürdige Skripte eintragen.
- Keine Secrets über stdin ausgeben; `execute_body` kann sensible Kundendaten enthalten — Logs/Weiterleitung vermeiden.
- Pfade bleiben unter der CWD (`resolve_under_cwd`); keine absoluten Hook-Pfade.
- **`--dry-run`** führt **keine** Hooks aus (keine versteckten Seiteneffekte im Sandbox-Modus).

Weitere CLI-Übersicht: [`ghost_cli_reference.md`](ghost_cli_reference.md) (Abschnitt P14).
