# Ghost P14 — Lifecycle Hooks — Testmatrix

**Ziel:** `arctis_ghost.hooks` und `ghost run` Hook-Integration (E6 / §15.9).  
**Automated:** `tests/ghost/test_hooks_p14.py`.

| ID | Szenario | Erwartung |
|----|-----------|-----------|
| **K01** | `pre_run` schreibt empfangenes JSON | `hook` = `pre_run`, Execute-Body korrekt, danach POST |
| **K02** | `pre_run` Exit 42 | Kein HTTP-Request |
| **K03** | `post_run` nach 201 | `run_id` im Payload |
| **K04** | HTTP 500 | `on_error`-Hook läuft, CLI Exit 1 |
| **K05** | `--no-hooks` trotz `hook_pre_run` | Hook läuft nicht, POST erfolgt |
| **K06** | `--dry-run` mit `hook_pre_run` | Hook läuft nicht |

## Manuell

- Nicht-`.py`-Hook (z. B. Shell): ausführbar machen und Pfad in YAML testen (POSIX vs. Windows).
