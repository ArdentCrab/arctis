# Ghost P13 — Predict / Replay / Multi-Region / Meta (§15.12–15.15)

**Epic K (light):** Diese Bausteine sind in der **Ghost-CLI** absichtlich **nicht** als Produktions-Multi-Region-Router oder Policy-Engine umgesetzt.

| Thema | Label | Kurzbeschreibung |
|--------|--------|------------------|
| **Predict** | **Roadmap** | Kein Ghost-CLI-Feature; ggf. nur serverseitig / später. |
| **Replay** | **Roadmap** | Kein Ghost-CLI-Feature. |
| **Multi-Region** | **Pilot** | Ein `api_base_url` aus `ghost.yaml` / Umgebung; **kein** clientseitiges Failover zwischen Regionen. |
| **`ghost meta`** | **Pilot** | Read-only JSON: Endpunkt-URL, Profil, Runtime, Paketversion — **ohne** API-Key-Material. |

Details zur CLI: [`ghost_cli_reference.md`](ghost_cli_reference.md) (Abschnitt P13).
