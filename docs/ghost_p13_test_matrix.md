# Ghost P13 — Meta / Roadmap — Testmatrix

**Ziel:** `ghost meta` und `ghost_meta_dict` (E5 / §15.12–15.15).  
**Automated:** `tests/ghost/test_meta_p13.py`.

| ID | Szenario | Erwartung |
|----|-----------|-----------|
| **M01** | `ghost_meta_dict` mit gesetztem API-Key | JSON enthält **keinen** Key-String; `credentials_configured: true` |
| **M02** | `ghost_meta_dict` Default-Config | `schema_version`, `kind`, `capabilities.*.status` (roadmap/pilot) |
| **M03** | `ghost meta` CLI | Exit 0, parsebares JSON mit `config` / `runtime` |

## Manuell

- Installiertes Paket: `ghost meta` → `package.version` gesetzt; bei editable ohne Metadata ggf. `null`.
