# Ghost — kopierfertige Implementierungs‑Prompts (Agent / Cursor)

**Zweck:** Jeder Abschnitt ist ein **eigenständiger Prompt** für die nächste Session. Reihenfolge beachten (Abhängigkeiten).  
**Kanon:** [`arctis_ghost_prompt_series.md`](arctis_ghost_prompt_series.md), [`arctis_ghost_project_plan.md`](arctis_ghost_project_plan.md) §6.

**Stand im Repo:** **P1–P14 erledigt** — inkl. §15-Erlebnis-Schicht **P9–P14** (Explain, Sandbox/Dry-run, Heartbeat, Profile/Auto-Recipe/Verify, `ghost meta`, Lifecycle-Hooks). Details und Links je Abschnitt unten (**erledigt**).

---

## Abhängigkeiten (Kurz)

```text
P1 doctor          → kein harter Blocker
P2 writer          → idealerweise nach P1 (doctor kann Writer-Pfade prüfen)
P3 state           → nach Writer (Artefakt-Pfade fest)
P4 init-demo       → nach doctor + writer (oder minimaler Stub-Writer)
P5 recipes         → nach state + writer
P6 demos polish    → parallel möglich
P7 openapi         → parallel möglich
P8 branding        → nach Writer/Envelope-Schema klar
P9–P14 §15         → nach stabiler CLI + optional Hooks-Contract
```

---

## P1 — `ghost doctor`

```markdown
# Ghost P1 — `ghost doctor`

## Ziel
Implementiere `ghost doctor` im Paket `arctis_ghost`: ein Subcommand, das die lokale Ghost-Konfiguration und die Erreichbarkeit der Arctis-API prüft.

## Anforderungen
- CLI: `ghost doctor` (optional `--profile` wie andere Commands).
- Prüfe: `load_config()` erfolgreich; `api_base_url` erreichbar (HEAD oder GET auf eine leichte Route, z. B. `/health` oder `/openapi.json` — nutze was im Repo existiert, sonst dokumentiere Fallback).
- Wenn `api_key` gesetzt: ein authentifizierter Smoke-Call (z. B. GET mit `X-API-Key`) gegen einen 401/404-sicheren Endpunkt — ohne destructiven Write.
- Ausgabe: strukturiert, nutze bestehendes `arctis_ghost.ansi` (OK/Warn/Fehler farbig), Exit-Code 0 bei OK, 1 bei harten Fehlern (Config broken, URL unreachable).
- Kein `import arctis.engine`.

## Dateien
- `arctis_ghost/cli.py`, neu z. B. `arctis_ghost/doctor.py`
- Tests: `tests/ghost/test_doctor.py` (HTTP mock, keine echten Calls)

## Akzeptanz
- `python -m pytest tests/ghost/test_doctor.py` grün
- `ghost doctor --help` sichtbar
```

---

## P2 — Writer + Envelope (atomar)

```markdown
# Ghost P2 — Writer & Envelope (atomar)

## Ziel
Implementiere ein Writer-Subsystem: nach erfolgreichem Run Artefakte unter einem konfigurierbaren Basis-Pfad ablegen — **atomar** (Tempfile → rename).

## Layout (MVP)
- `outgoing/<run_id>/envelope.json`
- `outgoing/<run_id>/skill_reports/<skill_id>.json`
- Optional Stretch: `routing.json`, `cost.json` extrahiert aus Run-JSON (nur wenn klar definiert)

## Anforderungen
- Konfiguration: z. B. `output_dir` / `outgoing_root` in `ghost.yaml` + Env-Override.
- API: reine Funktionen, z. B. `write_run_artifacts(run: dict, *, root: Path) -> None`
- `envelope.json`: mindestens `run_id`, `schema_version`, Timestamp (ISO), optional Teilmenge `skill_reports` Keys — **keine** Engine-Imports.
- JSON: `sort_keys=True`, deterministisch wo möglich.
- CLI: erweitere `ghost run` optional um `--write-artifacts` ODER separater `ghost pull-artifacts RUN_ID` nach `fetch` — wähle **einen** klaren MVP-Weg und dokumentiere in Docstring.

## Tests
- `tests/ghost/test_writer.py`: tmp_path, atomar (kein halbes File sichtbar), gültiges JSON.

## Akzeptanz
- pytest grün; kein Rich; Windows-kompatibel (Path).
```

---

## P3 — Lokaler State, Hashing, Skip/Reuse, `--force`

```markdown
# Ghost P3 — Lokaler State & Idempotenz (Client)

## Ziel
Implementiere lokalen State unter `.ghost/state/` (oder konfigurierbar): Content-Hash über **canonicalisiertes Input + workflow_id + recipe_id (optional)**.

## Verhalten
- Standard: bei gleichem Hash → **skip** (kein POST) und Ausgabe der gespeicherten `run_id` ODER klare Meldung — exaktes Verhalten in Doku festhalten (kompatibel mit Plan §6.4).
- `ghost run --force`: immer neuer Execute-Call.
- State-Dateien: JSON, klein, migrationsfestes `schema_version`.

## Integration
- Nur aktiv wenn Flag oder Config `state_enabled: true` — Default **false** bis explizit aktiviert, damit CI/Demos unverändert bleiben.

## Tests
- `tests/ghost/test_state.py`: Hash stabil, skip/reuse, force umgeht skip.

## Akzeptanz
- Keine Abhängigkeit von Arctis-Interna außer HTTP; keine Engine-Imports.
```

---

## P4 — `ghost init-demo`

```markdown
# Ghost P4 — `ghost init-demo`

## Ziel
Implementiere `ghost init-demo`: legt ein Demoverzeichnis mit `ghost.yaml`-Stub, Beispiel-`input.json`, README mit Verweis auf `docs/demo_60.md` und `docs/demo_matrix.md` an.

## Anforderungen
- Zielverzeichnis: Argument oder `.` default; keine Überschreibung ohne `--force`.
- Inhalt: minimal lauffähig (Platzhalter workflow_id klar markiert).
- Keine Engine-Imports.

## Tests
- `tests/ghost/test_init_demo.py`: tmp_path, assert Dateien existieren, YAML parsebar.

## Akzeptanz
- Konsistent mit Serie D1 / §15.1 Story; Doku-Link korrekt.
```

---

## P5 — Rezepte (`recipes/*.yaml`)

```markdown
# Ghost P5 — Rezepte

## Ziel
Implementiere Rezept-Dateien (YAML) gemäß Plan §6.2: `workflow_id`, `skills[]`, `input_mapping`, optional `defaults`, `output_mapping` (MVP: nur was für ersten Pfad nötig).

## CLI
- `ghost run --recipe path/to/recipe.yaml --input path/to/file.txt` (oder äquivalent).
- Merge: recipe defaults < file input < CLI overrides ( dokumentieren).

## Validierung
- Pydantic-Modelle für Rezept-Schema; klare Fehlermeldungen.

## Tests
- `tests/ghost/test_recipes.py`: golden recipe, fehlerhaftes YAML.

## Akzeptanz
- Kein `arctis.engine`; nutzt bestehenden `ghost_run` + Config.
```

---

## P6 — Demo-60 & Demo-Matrix Feinschliff

```markdown
# Ghost P6 — Demo-Dokumente finalisieren

## Ziel
Align `docs/demo_60.md` mit `docs/arctis_ghost_demo_60.md` (Storyboard, Begriffe, Schritte). Align `docs/demo_matrix.md` mit `docs/arctis_ghost_demo_matrix.md` (ehrliche Labels: Roadmap/Pilot).

## Anforderungen
- Keine falschen „alles implementiert“-Claims; Verweise auf offene Serien-Punkte (Writer, doctor, state) wo nötig.
- Optional: `tests/docs/test_demo_matrix.md` analog `test_demo_60_links.py`.

## Akzeptanz
- pytest `tests/docs/` grün; Links intern konsistent.
```

---

## P7 — OpenAPI & Developer Experience

```markdown
# Ghost P7 — OpenAPI / Examples

## Ziel
Verbessere OpenAPI und Beispiele für Customer-Execute: `skills`-Array, `skill_reports` in `execution_summary`, Header `X-Run-Id` / `Location`.

## Anforderungen
- Erweitere bestehende Sync-Tests (`tests/api/test_openapi_sync.py` o. ä.) falls vorhanden.
- Pro Skill-ID ein kurzes Example oder gemeinsame Komponente — Scope so wählen, dass PR klein bleibt.

## Akzeptanz
- API-Tests + OpenAPI-Sync grün.
```

---

## P8 — Branding / Freemium (PLG light)

```markdown
# Ghost P8 — Branding & Status-Sichtbarkeit (D4)

## Ziel
Minimale PLG-Basis: optionale Branding-Felder im **lokalen** `envelope.json` (Writer aus P2), plus lokale Status-Datei z. B. `__STATUS.txt` oder `limits/freemium.py` Stub — **serverseitige Limits nur anzeigen**, nicht erzwingen (Plan §8).

## Anforderungen
- Kein Marketing ohne Implementierung: Felder dokumentiert, Defaults harmlos.
- Tests für Writer-Felder optional.

## Akzeptanz
- Doku in `docs/demo_matrix.md` oder neuem kurzen `docs/ghost_plg.md` verlinkt.
```

---

## P9 — E1 Explain / Insights (§15.2 / §15.4)

```markdown
# Ghost P9 — Explain & Insights (Epic H light)

## Ziel
Erweitere Ghost CLI um **read-only** Kommandos oder Flags, die strukturierte Kurz-Erklärungen aus bereits gefetchten Run-Daten liefern (kein zweiter Governance-Pfad).

## Scope MVP
- Entweder: `ghost explain RUN_ID` (nutzt `ghost_fetch`, rendert Text) **oder** Erweiterung von `ghost evidence` mit `--brief`.
- Keine neuen Server-Endpunkte ohne explizite Anforderung.

## Akzeptanz
- Tests mit Mock-Fetch; keine Engine-Imports im Ghost-Paket.
```

---

## P10 — E2 Safety / Sandbox (§15.3 / §15.6) — **erledigt (Pilot)**

```markdown
# Ghost P10 — Safety / Sandbox (Pilot)

## Ziel
Dokumentiere und implementiere **clientseitige** Sandbox-Hinweise: z. B. max. Dateigröße für `--input`, Pfad-Validierung (kein `..`), dry-run Modus für `ghost run --recipe`.

## Akzeptanz
- Klare Fehlermeldungen; Tests für Path-Traversal-Ablehnung.
```

**Umsetzung im Repo:** `resolve_under_cwd` (kein Escape, keine absoluten Pfade), `MAX_JSON_BYTES` / `MAX_CLI_FILE_BYTES`, `GhostInputError`, `tests/ghost/test_paths_security.py`, **`ghost run --dry-run`** (`arctis_ghost.cli`), Doku `docs/ghost_cli_reference.md` / `docs/security_production.md`.

---

## P11 — E3 Heartbeat / Remote (§15.10 / §15.11) — **erledigt**

```markdown
# Ghost P11 — Heartbeat & Remote (Betrieb)

## Ziel
Optionaler Heartbeat: periodischer ping an konfigurierbare URL oder Metrik-Datei — **opt-in**, default off.

## Akzeptanz
- Kein Daemon-Pflichtprodukt; nur CLI oder einfacher Loop mit max iterations.
```

**Umsetzung:** [`arctis_ghost/heartbeat.py`](../arctis_ghost/heartbeat.py), CLI `ghost heartbeat` (`--url`, `--use-api-health`, `--metrics-file`, `--interval`, `--count`), YAML/Env in `GhostConfig`, Matrix [`ghost_p11_test_matrix.md`](ghost_p11_test_matrix.md).

---

## P12 — E4 Profiles / Auto-Recipe / Verify lokal (§15.5 / §15.7 / §15.8) — **erledigt**

```markdown
# Ghost P12 — Profiles, Auto-Recipe, lokales Verify

## Ziel
- Profile: bereits teilweise in `ghost.yaml` — erweitern um recipe-defaults pro Profil.
- Auto-Recipe: heuristische Wahl eines Rezepts aus Ordnernamen (documented, begrenzt).
- Verify lokal: Hash/Schema-Check des `envelope.json` gegen Run-Fetch (read-only).

## Akzeptanz
- Tests für Verify happy-path und mismatch.
```

**Umsetzung:** `GhostConfig.default_recipe` / `ARCTIS_GHOST_DEFAULT_RECIPE`, `ghost run --raw-json`, `--auto-recipe` + `ARCTIS_GHOST_AUTO_RECIPE`, `arctis_ghost/auto_recipe.py`, `envelope.py` + `verify.py`, CLI `ghost verify`, Matrix [`ghost_p12_test_matrix.md`](ghost_p12_test_matrix.md), Doku [`ghost_cli_reference.md`](ghost_cli_reference.md).

---

## P13 — E5 Predict / Replay / Multi-Region / Meta (§15.12–15.15) — **erledigt**

```markdown
# Ghost P13 — Predict, Replay, Multi-Region, Meta (Epic K light)

## Ziel
Nur **Planungs**- und Stub-Implementierung oder ein read-only `ghost meta`, das konfigurierte Endpoints und Versionen ausgibt — kein Produktions-Multi-Region ohne Backend.

## Akzeptanz
- Klare „Pilot/Roadmap“-Labels in Doku; minimale Code-Änderungen.
```

**Umsetzung:** [`arctis_ghost/meta.py`](../arctis_ghost/meta.py) (`ghost_meta_dict`), CLI **`ghost meta`**, Doku [`ghost_p13_roadmap.md`](ghost_p13_roadmap.md), [`ghost_p13_test_matrix.md`](ghost_p13_test_matrix.md), [`ghost_cli_reference.md`](ghost_cli_reference.md) (P13).

---

## P14 — E6 Extensions + Hook-Contract (§15.9 zuletzt) — **erledigt**

```markdown
# Ghost P14 — Extensions & Lifecycle Hooks

## Ziel
Definiere einen stabilen **Hook-Contract** (Python entrypoints oder configgesteuerte Shell-Hooks): pre-run, post-run, on-error — **ohne** parallele Policy-Engine.

## Regeln
- Hooks sind subprocess/shell mit explizitem Timeout; default keine Hooks.
- Dokumentiere Sicherheitswarnungen.

## Akzeptanz
- Tests mit dummy hook script in tmp_path.
```

**Umsetzung:** [`arctis_ghost/hooks.py`](../arctis_ghost/hooks.py), `ghost run` Integration + `--no-hooks`, YAML/Env in `GhostConfig`, Doku [`ghost_hooks_p14.md`](ghost_hooks_p14.md), [`ghost_p14_test_matrix.md`](ghost_p14_test_matrix.md), [`ghost_cli_reference.md`](ghost_cli_reference.md) (P14); `ghost meta` → `capabilities.lifecycle_hooks` (Pilot).

---

## Nutzung

1. Nächsten Prompt **komplett kopieren** (inkl. Überschrift `# Ghost Pn — …`).  
2. In Cursor einfügen und ausführen lassen.  
3. Nach Merge: nächster Prompt in der empfohlenen Reihenfolge.

**Referenz:** [arctis_ghost_prompt_series.md](arctis_ghost_prompt_series.md) für offizielle A–E-IDs.

---

## Nach P14 (keine weiteren P-Prompts)

Die Ghost-P-Serie ist **abgeschlossen**. Als Nächstes: **G0** (Finalisierung bis Publish) und optional **A0** (Zero-Interface / „Ultra Edition“) — siehe **[arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md)**.

**G0-Prompts zum Kopieren:** **[ghost_g0_implementation_prompts.md](ghost_g0_implementation_prompts.md)** (G1–G6).
