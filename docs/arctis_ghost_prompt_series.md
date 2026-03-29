# Arctis Ghost — 24-Prompt-Serie (Cursor / Issues)

**Zweck:** Reihenfolge und Akzeptanzkriterien für API-first Ghost in **24** zusammenhängenden Prompts (Blöcke **A–E**), abgestimmt mit [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) §10–§11 und der **Erlebnis-Schicht [§15](arctis_ghost_project_plan.md#15-ghost-erlebnis--und-betriebsschicht-ohne-api-bruch-ohne-engine-änderung)**.

**Serien-Beschreibung (Scope):** Die Serie deckt den **kanonischen Umsetzungspfad** für **Skill-Envelope**, **SkillRegistry**, Customer-Execute inkl. **`skill_reports`**, Run-/Evidence-Zugriff für Ghost, **Ghost-MVP** (Paket ohne Engine-Import), **PLG** (`init-demo`, Demos, Branding/Freemium-Sichtbarkeit) und die in §15 / Epics **H–K** beschriebene **Erlebnis- und Betriebsschicht**.  
**Explizit nicht Ziel dieser 24 Prompts** (Out-of-Scope, weiterhin laut Spec separat epizen): **Ghost Phase C** — Review-Loop, Batch, Excel-Parser, Cloud-Adapter ([Projektplan §10 Punkt 8](arctis_ghost_project_plan.md#10-rollout-reihenfolge-empfohlen-arctis-optimiert), Rollout §13.5) — sowie die **Horizonte H1–H4** ([§9](arctis_ghost_project_plan.md#9-innovations-roadmap-beyond-mvp--horizonte)). Kryptographisch signiertes Envelope / serverseitige Verify ersetzt lokale Konsistenzprüfung nicht ([§8](arctis_ghost_project_plan.md#8-plg-wirtschaftlichkeit--branding), §15.8).

**Hinweis zur Nummerierung im Projektplan:** **§14** ist „Demos & Landingpage-Story“; die **Ghost-Erlebnis-Schicht** ist **[§15](arctis_ghost_project_plan.md#15-ghost-erlebnis--und-betriebsschicht-ohne-api-bruch-ohne-engine-änderung)** (nicht §14).

---

## Block A — API Contract & Skill-Pipeline

| # | ID | Ziel / Akzeptanz (kurz) |
|---|-----|-------------------------|
| 1 | **A1** | **Skill-Envelope** (`skills` im Execute-Body), **SkillRegistry** (`SkillContext`, `resolve` → **422** bei unbekannter `id`), **Pre/Post-Hooks**; in [`customer.py`](../arctis/api/routes/customer.py) **dieselbe Skill-Kette** auf **Mock- und Real-Pfad** (kein Drift). Siehe [§3.4–3.5](arctis_ghost_project_plan.md#34-skillregistry). |
| 2 | **A2** | `skill_reports` in `execution_summary`, Persistenz am Run; konform [§3.2](arctis_ghost_project_plan.md#32-execution_summaryskill_reports). |
| 3 | **A3** | Nach Execute: zuverlässige **Run-ID** (z. B. Header `Location` / `X-Run-Id`) und **abrufbare** Run-/Summary-Daten für Ghost — bevorzugt dokumentiertes **`GET /runs/{run_id}`** inkl. `execution_summary` / `skill_reports`; kein neuer Listen-Endpunkt nötig, wenn dieser Fetch ausreicht ([§3.3](arctis_ghost_project_plan.md#33-antwort-execute-heute-vs-ghost-anforderung)). |
| 4 | **A4** | Evidence **E5**-konform inkl. Skill-Reports (kein zweiter Run ohne Flag). **Gate:** OpenAPI + bestehende Sync-/API-Tests **grün** ([§5](arctis_ghost_project_plan.md#5-openapi-und-tests), Rollout §12 **E5**). |

---

## Block B — Skills (Rollout-Wellen)

| # | ID | Ziel / Akzeptanz (kurz) |
|---|-----|-------------------------|
| 5 | **B1** | Skill `prompt_matrix`, Default **`mode: advise`** ([§4](arctis_ghost_project_plan.md#4-engine-skills-id-tabelle)). |
| 6 | **B2** | Skills `routing_explain`, `cost_token_snapshot`. **`pipeline_config_matrix`:** nur **advise** in Welle 1 ([§4](arctis_ghost_project_plan.md#4-engine-skills-id-tabelle)). |
| 7 | **B3** | Skills `pipeline_config_matrix` (advise), `evidence_subset`, `reviewer_explain` — gemäß [§10 Schritte 3–4](arctis_ghost_project_plan.md#10-rollout-reihenfolge-empfohlen-arctis-optimiert). |

---

## Block C — Ghost-Paket (MVP-Pfad)

| # | ID | Ziel / Akzeptanz (kurz) |
|---|-----|-------------------------|
| 8 | **C1** | Paket-Skelett: **kein** `import arctis.engine` ([§6](arctis_ghost_project_plan.md#6-ghost-paket-zielarchitektur)). |
| 9 | **C2** | Config (`config.yaml`), Pydantic-Validierung ([§6.1](arctis_ghost_project_plan.md#61-konfiguration)). |
| 10 | **C3** | HTTP-Client: Execute-Aufruf, Header **`Idempotency-Key`**, **429** mit `Retry-After` und begrenzten Retries ([§6.3](arctis_ghost_project_plan.md#63-http-client), Rollout **E6**). |
| 11 | **C4** | State / Hashing / Idempotenz ([§6.4](arctis_ghost_project_plan.md#64-state-und-idempotenz)). |
| 12 | **C5** | Writer (atomar), Pfade für `skill_reports`-Dateien und Envelope ([§6.5](arctis_ghost_project_plan.md#65-writer-atomar)). |
| 13 | **C6** | CLI: `ghost doctor`, `ghost run` (erster erfolgreicher End-to-End-Pfad) ([§6.6](arctis_ghost_project_plan.md#66-cli-mvp)). |
| 14 | **D1** | **`ghost init-demo`** + Inhalt gemäß [§15.1](arctis_ghost_project_plan.md#15-ghost-erlebnis--und-betriebsschicht-ohne-api-bruch-ohne-engine-änderung) und [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) — **nach** C6, **vor** C7 (PLG vor Daemon-Ausbau, [§10 Schritt 6b](arctis_ghost_project_plan.md#10-rollout-reihenfolge-empfohlen-arctis-optimiert)). |
| 15 | **C7** | **`ghost watch`**, Writer komplett, Skill-Report-Files, Envelope + Branding-Basis ([§6](arctis_ghost_project_plan.md#6-ghost-paket-zielarchitektur), [§10 Schritt 7](arctis_ghost_project_plan.md#10-rollout-reihenfolge-empfohlen-arctis-optimiert)). |

---

## Block D — Demos & PLG

| # | ID | Ziel / Akzeptanz (kurz) |
|---|-----|-------------------------|
| 16 | **D2** | Demo-60-Storyboard und Artefakte an [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) ausrichten. |
| 17 | **D3** | Demo-Matrix-Hooks gemäß [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md): **Rezept-/Skript-Varianten**, **ehrliche Labels** („Roadmap“ / „Pilot“) — nicht alle Matrix-Zeilen als implementiert ausgeben. |
| 18 | **D4** | **Branding-Felder** im Envelope ([§8](arctis_ghost_project_plan.md#8-plg-wirtschaftlichkeit--branding)); **lokale Freemium-/Status-Sichtbarkeit** (z. B. `__STATUS.txt`, `limits/freemium.py`-Pfad aus [§6](arctis_ghost_project_plan.md#6-ghost-paket-zielarchitektur)); serverseitige Limits **anzeigen**, nicht erzwingen (Epic **F — PLG**). |

---

## Block E — §15 / Epics H–K (Erlebnis-Schicht)

| # | ID | Ziel / Akzeptanz (kurz) |
|---|-----|-------------------------|
| 19 | **E1** | §15.2 Explain, §15.4 Insights; Anknüpfung Demo 60 wo sinnvoll (Epic **H**). |
| 20 | **E2** | §15.3 Safety, §15.6 Sandbox (Epic **H** / Piloten). |
| 21 | **E3** | §15.10 Heartbeat, §15.11 Remote (Epic **I**). |
| 22 | **E4** | §15.5 Profiles, §15.7 Auto-Recipe, §15.8 Verify (lokal) (Epic **J** — **ohne** 15.9). |
| 23 | **E5** | §15.12 Predict, §15.13 Replay, §15.14 Multi-Region, §15.15 Meta (Epic **K**). |
| 24 | **E6** | **§15.9 Extensions** — **zuletzt**, nach stabiler Hook-Schnittstelle ([Rollout-Hinweis §15](arctis_ghost_project_plan.md#15-ghost-erlebnis--und-betriebsschicht-ohne-api-bruch-ohne-engine-änderung)); zuerst **Hook-Contract** (Lifecycle-Hooks, keine parallele Policy). *Falls mehrere §15-Bausteine in einem Prompt gebündelt werden:* Betrieb (15.10/15.11) → Predict / Replay / Multi-Region / Meta (15.12–15.15) → **Extensions am Ende**. |

---

## Referenzen

| Dokument | Nutzen |
|----------|--------|
| [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) | Kanonischer Fahrplan, §3 Skills, §6 Ghost, §8 PLG, §9 Horizonte, §10 Reihenfolge, §15 Erlebnis |
| [arctis_rollout_anleitung_jetzt_bis_produkt.md](arctis_rollout_anleitung_jetzt_bis_produkt.md) | E1–E6 Engine-P0/P1, §13 Ghost |
| [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) | 60-Sekunden-Demo |
| [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md) | Landingpage-Module (Scope beachten) |

---

## Nach Block E (P9–P14 erledigt)

Es folgen **keine weiteren P-Prompts**. Die nächste planbare Arbeit ist:

- **G0** — Release, CI, README/E2E, Sicherheitsdoku, PyPI-/Paket-Entscheid ([arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md)); **Prompts G1–G6:** [ghost_g0_implementation_prompts.md](ghost_g0_implementation_prompts.md).
- **A0** — Zero-Interface-Produktlinie (Hot-Folder, Sidecar, Stamps, Symlinks, Clipboard, zusammengeführte Flows); **Launch-Regel** (nur G0 vs. G0+A0) teamfestlegen — siehe dieselbe Roadmap.
