# Ghost P11 — Heartbeat / Remote — Testmatrix

**Ziel:** Abdeckung für `arctis_ghost.heartbeat` und `ghost heartbeat` (E3 / §15.10–15.11).  
**Automated:** `tests/ghost/test_heartbeat_p11.py` (pytest, `case_id` = Matrix-ID).

| ID | Szenario | Erwartung |
|----|-----------|-----------|
| **H01** | `run_heartbeat_loop`: HTTP mock → 200, 1 Tick | Exit `0`, ein Ping |
| **H02** | HTTP mock → 500, 1 Tick | Exit `1` |
| **H03** | HTTP transport error (`None` status) | Exit `1` |
| **H04** | Nur `--metrics-file`, 3 Ticks, `interval=0` | 3 NDJSON-Zeilen, Exit `0` |
| **H05** | URL + Metrikdatei, 200 | Zeile enthält `http_status` 200, Exit `0` |
| **H06** | `validate_heartbeat_url("ftp://x")` | `ValueError` |
| **H07** | Metrikpfad `../outside` (CWD-bound) | `ValueError` / CLI-Fehler |
| **H08** | CLI: keine URL / kein `--use-api-health` / keine Metrik-Quelle | Exit `1`, Fehlertext |
| **H09** | CLI: `--count 0` | Exit `1` |
| **H10** | `requests_mock`: `GET` konfigurierte URL, `--count 2` | 2 Requests, Exit `0` |

## Manuell / Staging

- Heartbeat gegen echte API `GET /health` mit gültigem `ghost.yaml` (`api_base_url`) und `--use-api-health --count 5 --interval 10`.
- Metrikdatei auf Netzlaufwerk: Schreibrechte und Rotation (Ops), nicht Teil des Ghost-Pakets.

## Konfiguration (Kurz)

| Quelle | Variablen / YAML |
|--------|-------------------|
| Env | `ARCTIS_GHOST_HEARTBEAT_URL`, `ARCTIS_GHOST_HEARTBEAT_METRICS_FILE`, `ARCTIS_GHOST_HEARTBEAT_INTERVAL` |
| Profil | `heartbeat_url`, `heartbeat_metrics_file`, `heartbeat_interval_seconds` |
