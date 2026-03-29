# Ghost P12 — Profiles / Auto-Recipe / Verify — Testmatrix

**Ziel:** Abdeckung für Profil-`default_recipe`, `--auto-recipe` / `ARCTIS_GHOST_AUTO_RECIPE`, `ghost verify`, und `envelope_payload_from_run` (E4 / §15.5–15.8).  
**Automated:** `tests/ghost/test_cli_run.py`, `tests/ghost/test_verify_p12.py` (pytest).

| ID | Szenario | Erwartung |
|----|-----------|-----------|
| **V01** | `verify_envelope_against_run`: Artefakte wie `pull-artifacts`, gleicher Run | OK |
| **V02** | Verify: API-`status` ≠ `envelope.json` | Mismatch, Hinweis auf `status` |
| **V03** | Verify: `run_id` in Datei manipuliert | Mismatch |
| **V04** | `ghost run` mit `default_recipe` im Profil | POST mit Rezept-Body |
| **V05** | `ghost run --raw-json` trotz `default_recipe` | Voller JSON-Body, kein Rezept |
| **V06** | `ghost run --auto-recipe` + `recipe.yaml` im CWD | Rezept wird gewählt |
| **V07** | `ghost run --recipe` + `--raw-json` | CLI-Fehler |
| **V08** | `ghost verify` + Mock `GET /runs/{id}` + lokales `envelope.json` | Exit 0 bei Konsistenz |
| **V09** | `ghost verify` bei Status-Diskrepanz | Exit 1 |

## Manuell / Staging

- Profil mit `default_recipe` und echter API: `ghost run input.json` ohne `--recipe`.
- Auto-Recipe: Verzeichnis `recipes/<ordnername>.yaml` anlegen, `ARCTIS_GHOST_AUTO_RECIPE=1`, `ghost run …`.

## Konfiguration (Kurz)

| Quelle | Variablen / YAML |
|--------|------------------|
| Profil | `default_recipe` (Pfad relativ zur CWD) |
| Env | `ARCTIS_GHOST_DEFAULT_RECIPE`, `ARCTIS_GHOST_AUTO_RECIPE` (`1`/`true`/…) |
