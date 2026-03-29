# Ghost — Staging-E2E (Checkliste)

```
Status: Noch nicht ausgeführt — Staging-API-Run steht aus.
Datum: —
```

**Zweck:** Einmaliger oder wiederholter **End-to-End-Nachweis** gegen eine **Staging-Arctis-API** (nicht Produktion). Keine Secrets in diesem Dokument ablegen.

## Voraussetzungen

- Staging-**API-Base-URL** (HTTPS).
- **API-Key** nur über Umgebung (`ARCTIS_API_KEY`) oder Secret-Store — nicht in `ghost.yaml` committen.
- Lokales Arctis-Repo mit installiertem Paket: `pip install -e ".[dev]"`.

## Konfiguration (Beispiel)

```bash
export ARCTIS_GHOST_API_BASE_URL="https://staging.example.invalid"
export ARCTIS_API_KEY="***"   # aus Secret-Manager
```

Optional: `ghost.yaml` im Arbeitsverzeichnis mit `api_base_url` und Profil; Key weiterhin bevorzugt per Env.

## Checkliste

| # | Schritt | Erwartung | Notizen |
|---|---------|-----------|---------|
| 1 | `ghost doctor` | Exit 0; `/health` erreichbar | Bei Key: authentifizierter Smoke-Call |
| 2 | `ghost run …` | `run_id` (UUID) auf stdout | Minimaler Execute-Body oder Rezept |
| 3 | `ghost fetch <run_id>` oder `ghost watch <run_id>` | Run-JSON / Terminalstatus | |
| 4 | `ghost pull-artifacts <run_id>` | `outgoing/<run_id>/envelope.json`, `skill_reports/` | |
| 5 | `ghost verify <run_id>` | `envelope verify: OK` | Gleiche Config wie bei pull-artifacts |
| 6 | (optional) Hooks | Nur mit Testskript unter CWD | `ghost run --no-hooks` zum Vergleich |

## Redaction

- Logs/Exports für interne Doku: **URLs anonymisieren**, **keine Keys**, **keine Kundendaten** aus `execute_body` kopieren.

## Akzeptanz

- [ ] Durchlauf von einem Maintainer ausgeführt oder reviewt  
- [ ] Datum / Umgebung (Staging-Name) intern vermerkt  
