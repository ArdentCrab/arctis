# Arctis Ghost & Skill Engine — Projektplan (API-first)

**Status:** Spezifikation und Rollout-Fahrplan (Repo-gebunden).  
**Beziehung zu anderen Dokumenten:**

| Dokument | Rolle |
|----------|--------|
| [arctis_rollout_anleitung_jetzt_bis_produkt.md](arctis_rollout_anleitung_jetzt_bis_produkt.md) | Gesamt-Rollout, §12 Engine P0/P1, §13 Ghost-Grundlagen |
| [arctis_engine_and_security_spec_v1.5.md](arctis_engine_and_security_spec_v1.5.md) | Sicherheits- und Architekturzielbild |
| [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) | **60-Sekunden-Demo** (Storyboard, Checkliste, Einwände) |
| [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md) | **Demo-Matrix** für Landingpage (6 Module, Story-Arc, 20s / 60s / 3min) |
| [arctis_ghost_prompt_series.md](arctis_ghost_prompt_series.md) | **24-Prompt-Serie** (Cursor/Issues): Reihenfolge A–E, Scope vs. Phase C / H1–H4 |
| [arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md) | **Nach P14:** G0 (Publish-Querschnitt) & A0 (Zero-Interface Epics A1–A6) |
| [ghost_g0_implementation_prompts.md](ghost_g0_implementation_prompts.md) | **G1–G6** kopierfertige Agent-Prompts für G0 (Finalisierung) |
| `openapi.json` / `arctis/api/openapi_schema.py` | Verbindlicher HTTP-Kontrakt |

**Leitprinzip:** Ghost bleibt ein **HTTP-only**-Klient ohne `import arctis.engine`. Alle Governance-Entscheidungen laufen **serverseitig**; Ghost mappt Dateien, State und Artefakte.

---

## 1. Produktthese (Arctis-spezifisch)

Arctis trennt bereits **Engine** (Laufzeit), **API** (Tenant, Policy, Budget, Evidence) und **Customer Output** (strikt gefiltertes Ergebnis). Ghost schließt die Lücke zu **Zero-Interface-Betrieb**: Ordner, Rezepte, Idempotenz — ohne zweite Wahrheit neben der API.

Die **Skill Engine** (Skill-Envelope + `skill_reports`) macht Engine-Intelligenz **abrufbar und auditierbar**, ohne dass Clients Policy oder Routing duplizieren. Das ist das differenzierende Fundament; alles Weitere in [Abschnitt 9](#9-innovations-roadmap-beyond-mvp--horizonte) baut darauf auf.

---

## 2. Ist-Zustand im Repository (kurz)

- **`POST /customer/workflows/{workflow_id}/execute`** ([`arctis/api/routes/customer.py`](../arctis/api/routes/customer.py)): Template-Merge, Validierung, Engine-Lauf, Persistenz von `Run` inkl. `execution_summary` (Kosten, Tokens, Steps, Evidence). Request enthält heute faktisch nur **`input`** — kein **`skills`**-Array.
- **Antwort der Execute-Route:** HTTP-Body ist **nur** Customer Output v1 ([`arctis/customer_output.py`](../arctis/customer_output.py)) — **ohne** eingebettetes `run_id` / `execution_summary`. Ghost braucht dafür eine **explizite Kunden-Strategie** (siehe [§3.3](#33-antwort-execute-heute-vs-ghost-anforderung)).
- **Prompt-Matrix-API** ([`arctis/api/routes/prompt_matrix.py`](../arctis/api/routes/prompt_matrix.py)): eigenständige A/B-Persistenz, nicht mit Execute gekoppelt.
- **Auto-Optimize** ([`arctis/workflow/auto_optimize.py`](../arctis/workflow/auto_optimize.py), [`arctis/pipeline/auto_optimize.py`](../arctis/pipeline/auto_optimize.py)): interne DB-Optimierung, nicht als Customer-Skill exponiert.
- **Ghost-Code:** im Repo noch nicht als Paket angelegt; Zielbild in Rollout **§13**.

---

## 3. API-Schicht: Skill-Envelope

### 3.1 Request

Erweiterung des JSON-Bodys von `POST /customer/workflows/{workflow_id}/execute`:

```json
{
  "input": { "...": "..." },
  "skills": [
    { "id": "prompt_matrix", "params": { "mode": "advise" } },
    { "id": "routing_explain" },
    { "id": "cost_token_snapshot" }
  ]
}
```

- **`input`:** unverändert (Merge mit Workflow-Template, Validierung, Engine).
- **`skills`:** optional; Listeneinträge mit `id` und optionalem `params` (freies JSON-Objekt).
- **Unbekannte `id`:** **HTTP 422** mit klarer Fehlermeldung — kein Silent-Ignore (passt zu Rollout **§12 E1**: strikte Validierung vor Engine).

### 3.2 `execution_summary.skill_reports`

Serverseitig (und für Clients abrufbar) wird `execution_summary` um eine Map erweitert:

```json
"skill_reports": {
  "prompt_matrix": {
    "schema_version": "1.0",
    "payload": {},
    "provenance": {}
  }
}
```

Jeder Report: `schema_version`, skill-spezifisches `payload`, `provenance` (z. B. Workflow-Version, Modelle, Zeitstempel, optional `matrix_id`).

### 3.3 Antwort Execute: heute vs. Ghost-Anforderung

| Aspekt | Heute | Ziel für Ghost |
|--------|--------|----------------|
| HTTP 201 Body | Nur Customer Output v1 | Ghost benötigt zuverlässig **`run_id`** und Zugriff auf **`execution_summary`** (inkl. `skill_reports`) |
| Empfehlung (minimal-invasiv) | Response-Header **`Location`** oder **`X-Run-Id`** + dokumentiertes **`GET /runs/{run_id}`** | Rollout **§13.4** ist bereits auf Run-Fetch ausgelegt; Execute-Route soll dasselbe unterstützen |
| Alternative | Query `?include_execution_summary=true` oder zweites Antwort-Schema (Versionierung) | Bewusst im Epic „API Contract“ entscheiden und in OpenAPI festhalten |

**Ohne** diese Klärung können `skill_reports` in der DB landen, Ghost sie aber nicht ohne zusätzliche Heuristik aus der Execute-Response lesen.

### 3.4 SkillRegistry

Neues Modul unter z. B. `arctis/api/skills/`:

- **`SkillContext`:** `workflow_id`, `run_id` (wenn verfügbar), `tenant_id`, gemergter Input, Workflow-/Pipeline-Version, Request/Scopes wo nötig.
- **`SkillRegistry`:** Registrierung bekannter Skills; `resolve(id)` wirft bei unbekanntem `id` eine definierte Exception → 422 in der Route.
- **`run_pre_hooks` / `run_post_hooks`:** optional Pre-Run; Post-Run erzeugt die Map `skill_reports`.

**Einziger produktiver Einstieg:** [`customer.py`](../arctis/api/routes/customer.py) — **Mock- und Real-Pfad** jeweils mit derselben Skill-Kette (kein Drift).

### 3.5 Ablauf Customer-Execute (Ziel)

1. Body parsen: `input`, `skills` (Default: leere Liste).
2. Skill-IDs gegen Registry prüfen → sonst 422.
3. Optional `run_pre_hooks`.
4. Engine-Lauf wie heute.
5. `run_post_hooks` → `skill_reports`.
6. `execution_summary["skill_reports"]` setzen (keine stillen Überschreibungen bestehender Summary-Felder ohne Konvention).
7. Evidence-Envelope um Skill-Reports erweitern (konsistent mit **§12 E5**).

---

## 4. Engine-Skills (ID-Tabelle)

| Skill `id` | Code-Basis im Repo | Hinweis |
|------------|-------------------|---------|
| `prompt_matrix` | `MatrixRunner`, `MatrixRecommendationEngine`, optional `auto_optimize_prompt` | Default **`mode: advise`** (keine stille neue Workflow-Version); `apply` später nur mit Scope/Quota |
| `routing_explain` | `RunResult.execution_trace` / Schrittspuren | Entscheidungen aus Trace ableiten; leere sinnvolle Payload wenn keine Daten |
| `cost_token_snapshot` | `e6_cost_from_run_result`, `execution_summary_token_usage` | Strukturierter Breakdown pro Step, wo verfügbar |
| `pipeline_config_matrix` | Logik aus `auto_optimize_pipeline` | **Nur advise** in Welle 1 |
| `evidence_subset` | `EvidenceBuilder` / Highlights | Für kompakte Bundles und PLG-taugliche Auszüge |
| `reviewer_explain` | Review-Queue / `reviewer_policy` | Wenn kein Review: dokumentierter Leer- oder Info-Payload |

Payload-Beispiele und OpenAPI-`examples` sollten pro Skill gepflegt werden (Developer Experience und Ghost-Tests).

---

## 5. OpenAPI und Tests

- Request-Schema: optionales Feld `skills`.
- `execution_summary`: Dokumentation von `skill_reports` (z. B. `additionalProperties` oder gemeinsame `SkillReport`-Komponente).
- Bestehende **OpenAPI-Sync-Tests** erweitern; bei neuen Headern für `run_id` ebenfalls Schema + Tests.

---

## 6. Ghost-Paket (Zielarchitektur)

Verzeichnis-Vorschlag (kann mit Rollout **§13.2** kombiniert werden, z. B. top-level `ghost/` oder `tools/arctis_ghost/`):

```text
ghost/
  pyproject.toml
  arctis_ghost/
    config.py
    http_client.py
    recipes.py
    parsers/txt.py, json.py, excel.py (später)
    state/store.py, hashing.py
    writer/files.py
    cli.py
    limits/freemium.py
    tests/
```

**Hartes Verbot:** `from arctis...` im Ghost-Prozess.

### 6.1 Konfiguration

`config.yaml`: `base_url`, API-Key (z. B. über Env), `tenant_id`, `default_recipe`, Pfade (`incoming`/`outgoing`/`state`), `freemium_limit`, Branding-Flags. Validierung mit Pydantic.

### 6.2 Rezepte

`recipes/<name>.yaml`: `workflow_id`, `skills[]`, `input_mapping` (Parser + Feldzuordnung), `output_templates` (z. B. `summary_txt`, `result_json`, `envelope_json`, Liste der Skill-Reports als Einzelfiles).

**Einstieg API:** bevorzugt **`POST /customer/workflows/{workflow_id}/execute`** mit `{ input, skills }` — konsistent mit diesem Plan. `POST /pipelines/.../run` bleibt für pipeline-zentrierte Szenarien (siehe Rollout **§13.4**); Rezepte wählen einen Einstieg pro Use Case.

### 6.3 HTTP-Client

- `execute_workflow(workflow_id, input_dict, skills, idempotency_key=...)`
- Header: `Authorization`, **`Idempotency-Key`** (Anbindung an **§12 E6**), optional Mock-Header wie in Arctis üblich.
- **429:** `Retry-After`, begrenzte Wiederholungen.
- Fehler: Artefakte unter `outgoing/errors/`.

### 6.4 State und Idempotenz

- Content-Hash + Rezept + `workflow_id` als Schlüsselkomponenten (Hash allein reicht nicht immer).
- Verhalten bei gleichem Hash: **skip** oder **Reuse** — Produktregel im Rezept oder global config festlegen (kompatibel mit Rollout **§13.3** Smart Re-Run).

### 6.5 Writer (atomar)

- Temporäre Datei → Rename.
- `outgoing/approved/<stem>.skill_reports/<skill_id>.json`
- `envelope.json` mit `run_id`, `input_hash`, Teilmenge der `skill_reports`, Branding-Block (siehe [§8](#8-plg-wirtschaftlichkeit--branding)).

### 6.6 CLI (MVP)

`ghost watch`, `ghost run <file>`, `ghost evidence <run_id>`, `ghost doctor`, `ghost config init`.

---

## 7. End-to-End (Ghost + Skills)

1. Datei in `incoming/**`.
2. Rezept laden → Parser → `input_dict`.
3. Hash und Idempotency-Key; ggf. Skip.
4. Freemium prüfen (lokal + serverseitige Quota, siehe [§8](#8-plg-wirtschaftlichkeit--branding)).
5. `POST .../execute` mit `{ input, skills }`.
6. `run_id` und vollständige Summary per Header + **`GET /runs/{run_id}`** (oder vereinbartes Antwortschema).
7. Ausgabe: `result.json`, `summary.txt`, `envelope.json`, `skill_reports/*.json`.

---

## 8. PLG, Wirtschaftlichkeit, Branding

- **Freemium:** Anzeige z. B. `__STATUS.txt` oder im Envelope; **serverseitige** Limits (402/429) sind maßgeblich — der Client zeigt nur klar, nicht „erzwingt“ Sicherheit.
- **Evidence-Bundle:** Skill-Reports als differenzierender Inhalt; Branding-Felder z. B. `audited_by`, `branding_version`. **Hinweis:** JSON-Branding ersetzt keine kryptographische Verifikation; „signiertes Envelope“ = separates Epic.
- **Verify-Link:** optionaler Verweis `https://…/verify?run_id=…` nur wenn ein öffentlicher oder token-geschützter Verify-Pfad produktiv existiert (kein Marketing ohne Implementierung).

---

## 9. Innovations-Roadmap „Beyond MVP“ (Horizonte)

Die folgende Liste bündelt **Innovationsideen** in **Horizonte**, abhängig vom Skill-Envelope, stabiler Run-/Evidence-API und Ghost-MVP. Sie ist **nicht** als sofortiger Scope gedacht, sondern als priorisierte Backlog-Struktur.

### 9.1 Horizont H0 — Fundament (Pflicht vor Breite)

- Skill-Envelope + `skill_reports` + Run-Zugriff für Ghost (§3).
- Ghost MVP: Watch, TXT/JSON, HTTP-only, Evidence-kompatible Artefakte (Rollout §13.5 Phase B).

### 9.2 Horizont H1 — Reibungsarm am Dateisystem („Ghost Kernel Hooks“)

| Thema | Beschreibung | Abhängigkeiten / Risiko |
|-------|----------------|-------------------------|
| Hot-Folder-Konventionen | Virtuelle „Typen“ über Unterordner oder Namenskonvention (`incoming/invoice/` …) statt exotische Dateierweiterungen — **ohne** OS-Installer-Pflicht | Nur Ghost-Config + Doku |
| Explorer-Kontextmenü „Mit Arctis prüfen“ | Windows/macOS Shell-Extension ruft `ghost run` mit Pfad auf | Packaging, Codesigning, Support-Last |
| Virtueller Drucker „Audit“ | PDF nach `incoming/print/` | Treiber-Zertifizierung, hoher Wartungsaufwand — **spät** oder Partner |

### 9.3 Horizont H2 — Kognitive Schicht (Intent & Memory)

| Thema | Beschreibung | Abhängigkeiten |
|-------|----------------|----------------|
| Intent aus Dateiname | Heuristik → Vorschlag für Rezept/Workflow (immer **override** durch explizites Rezept) | Lokale ML optional; keine serverseitige Pflicht |
| Ghost Memory | Häufige Ordner/Skills aus State-DB lernen; Vorschläge | Datenschutz, Opt-in |
| Adaptive Rezepte | Skills/Rezepte aus Nutzungsstatistik vorschlagen | Kein automatisches Ändern von Produktiv-Rezepten ohne Confirm |

### 9.4 Horizont H3 — Physisch, Team, Ökonomie, Governance

| Thema | Beschreibung | Anbindung Arctis |
|-------|----------------|------------------|
| Camera-Drop / QR | Mobil → Datei → Ghost → API | Nur HTTP; kein Sonderprotokoll in der Engine |
| Audit-Stamp PDF | Wasserzeichen, QR, Hash auf Ausgabe | Ghost post-processing oder zukünftiger Export-Endpoint |
| UNC / NAS-Watch | Gleicher Watcher wie lokal | Netzwerk-Stabilität, File-Locks |
| Shared Ghost | Gemeinsame incoming/outgoing (Fileserver) | Berechtigungen, Konflikte — operativ |
| Chat-Integration (Slack/Teams) | Bot holt Anhänge, ruft API, postet Link/Evidence-Zusammenfassung | OAuth, separate Connectors |
| Ghost Digest | Tägliche Aggregation aus State + API-Metriken | Nutzung `GET /costs/report` o. Ä. wo vorhanden |
| Profit-Report / Forecast | Schätzung manueller Zeit vs. API-Kosten | Annahmen dokumentieren; keine falschen CFO-Zahlen |
| Invoice-Ready ZIP | Bundle für Buchhaltung | Ghost-only Zusammenpacken |
| Policy-Diff | Zwei Policy-Versionen vergleichen | Admin-API oder exportierte JSON |
| Shadow-Audit | Batch über alte Dateien | Rechtliche Klärung Aufbewahrung/PII |
| PII Local-Relay | Lokale Anonymisierung vor Cloud | Eigenes Modul, rechtliche Review-Pflicht |

### 9.5 Horizont H4 — Viralität & Ökosystem

| Thema | Beschreibung |
|-------|----------------|
| Verify-Link im Bundle | Nur mit echtem Verify-Backend |
| Recipe-Store / Templates | `templates/` im Ghost-Repo + Versionierung |
| Freemium-Clock | Sichtbar in `__STATUS.txt` / Envelope |

---

## 10. Rollout-Reihenfolge (empfohlen, Arctis-optimiert)

Die Reihenfolge ist auf **minimales Risiko** und **Abnahme gegen bestehende Tests** ausgelegt:

1. **API:** Skill-Envelope, 422 bei unbekannten IDs, `skill_reports` in DB, **Run-ID/Summary für Clients** (§3.3).
2. **API:** Skill `prompt_matrix` (`advise`).
3. **API:** Skills `routing_explain`, `cost_token_snapshot`.
4. **API:** Skills `pipeline_config_matrix` (advise), `evidence_subset`, `reviewer_explain`.
5. **OpenAPI + Tests** synchron halten.
6. **Ghost:** Paket-Skelett, Config, HTTP-Client, State, `doctor` / `run`.
6b. **Ghost PLG:** `init-demo` + Inhalt aus [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) (§15.1).
7. **Ghost:** `watch`, Writer, Skill-Report-Files, Envelope + Branding.
8. **Ghost Phase C** (Rollout §13.5): Review-Loop, Batch, Excel, ein Cloud-Adapter.
9. **Horizont H1–H4** nach Geschäftswert und Support-Kapazität einzeln epizen.

---

## 11. Epics für Issues (Copy-Paste)

| Epic | Inhalt |
|------|--------|
| **A — API Contract** | `skills` Request, 422, Response-Strategie Execute ↔ `GET /runs`, OpenAPI |
| **B — SkillRegistry** | Kontext, Registry, Pre/Post-Hooks, Tests Mock+Real |
| **C — Skills** | Reihenfolge: prompt_matrix → routing/cost → pipeline/evidence/reviewer |
| **D — Evidence** | E5-konforme Aufnahme von `skill_reports`; ggf. Verknüpfung PromptMatrix-API |
| **E — Ghost MVP** | Paket, CLI, Watch, Writer, keine Engine-Imports |
| **F — PLG** | Freemium-Anzeige, Branding-Felder, Demo-Ordner |
| **G — Beyond** | H1–H4 nach Priorität |

---

## 12. Abnahmekriterien (kompakt)

- Kein Ghost-Prozess importiert `arctis.engine`.
- Unbekannter Skill → **422** vor Engine.
- `skill_reports` stammen aus **demselben** Run wie Evidence (keine versteckte zweite Engine-Ausführung ohne Flag).
- OpenAPI und API-Tests grün nach Änderung.
- Ghost-Integrationstest: Fixture-Datei → HTTP → erwartete Files unter `outgoing/`.
- Rollout-Checkliste **§14** weiterhin erfüllbar.

---

## 13. Kurzreferenz: Qualitätshebel (aus Plan-Review)

1. **Server-Freemium / Skill-Allowlist** pro Plan — nicht nur Client-Zähler.
2. **Determinismus** der Skill-Pipeline.
3. **Idempotency-Key** inkl. Rezept + Workflow + normalisiertem Input.
4. **Signiertes Evidence** als separates, späteres Epic.

---

## 14. Demos & Landingpage-Story

- **Story-Arc & sechs Zielgruppen-Module** (C-Level, Security, Tech, Operations, Innovation, Audit): **[arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md)** — Struktur für Homepage („Wähle deine Demo“), **20 s / 60 s / 3 min** pro Kachel, SEO- und Sales-Hooks.
- **Konkretes 60-Sekunden-Storyboard** (live/trocken): **[arctis_ghost_demo_60.md](arctis_ghost_demo_60.md)**.

---

## 15. Ghost-Erlebnis- und Betriebsschicht (ohne API-Bruch, ohne Engine-Änderung)

Die folgenden Bausteine sitzen **über** HTTP-Client, State und Writer. Sie erhöhen PLG, Support-Qualität und Enterprise-Tauglichkeit; die Arctis-API bleibt die **einzige** Governance-Wahrheit.

| # | Baustein | Vorschlag (CLI / Artefakt) | Rolle | API-/Produkt-Notiz |
|---|-----------|------------------------------|-------|-------------------|
| 15.1 | **First-Run Experience** | `ghost init-demo` erzeugt `demo/incoming/`, `demo/recipes/…`, `README_FIRST_RUN.txt` | PLG: Time-to-Wow in unter einer Minute | Nutzt normalen Execute- oder Mock-Pfad |
| 15.2 | **Explain Mode** | `ghost explain <file>` → Recipe, `workflow_id`, Skills, Idempotency-Key, gewähltes Profil | Support-Last ↓, Vertrauen ↑ | Kein zusätzlicher Endpoint nötig; reine Client-Zusammenfassung |
| 15.3 | **Safety Layer** | Max. Dateigröße, Batch-Zwang bei Massen-Events, Vorschlag Default-Recipe, Stopp nach N Fehlern + `__SICHERUNG_RAUS.txt` | Schutz vor Fehlbedienung | Weiterhin nur gezielte Requests; keine Engine-Logik |
| 15.4 | **Insights** | `ghost insights` → `__INSIGHTS.txt` (Counts, Policy-Hits, geschätzte Einsparung) | Sichtbarkeit im Alltag | Zahlen aus lokalem State + ggf. `GET /costs/report` / Run-Metadaten |
| 15.5 | **Profiles** | `profiles/finance/`, `profiles/legal/`; Zuordnung `incoming/<profil>/…` → Rezept/Skills | Multi-Persona / Teams | Konfiguration nur lokal/tenant YAML |
| 15.6 | **Sandbox** | `ghost run <file> --sandbox` → Header `X-Arctis-Mock: true`, Ausgabe unter `outgoing/sandbox/` | IT-Piloten | Entspricht Rollout **§12 E4** |
| 15.7 | **Auto-Recipe** | `ghost auto-recipe <file>` → `recipes/auto_<hash>.yaml` (Heuristik: Typ, Pfad, grobe Inhaltsklassen) | Onboarding | Vorschlag immer **reviewbar**; kein Auto-Push ohne Mensch |
| 15.8 | **Verify (lokal)** | `ghost verify <envelope.json>` → Konsistenz Hash / `run_id` / referenzierte Skill-Report-Pfade | Prüfbarkeit ohne UI | **Kein** Ersatz für serverseitige Signatur; optional später API-Verify |
| 15.9 | **Extensions** | `ghost/extensions/*.py` (Hooks: nach Run, vor Upload, PDF-Stempel, Slack) | Erweiterbarkeit ohne Core-Fork | Plugins dürfen **keine** parallele Policy implementieren |
| 15.10 | **Heartbeat** | Periodisch `__HEARTBEAT.txt` (alive, letzter Run, Queue, Fehlerzähler) | Monitoring für IT | Kein neuer Server; Datei für RMM/Scripts |
| 15.11 | **Remote (Datei-Steuerung)** | `__COMMAND.pause` / `resume` / `flush` / `shutdown` im Watch-Root | Daemon-Fernbedienung ohne UI | Klar dokumentieren: wer Schreibrechte hat |
| 15.12 | **Predict** | `__FORECAST.txt` aus Rolling-State (Kosten/Tokens/Risiko-Schätzung) | CFO/COO-Story | Schätzungen transparent kennzeichnen |
| 15.13 | **Replay** | `ghost replay <run_id>` → erneutes Bundle / Diff-Hinweis | Revision | Nur wo API **Replay** / erneuter Export erlaubt ist (siehe `openapi.json` / Runs) |
| 15.14 | **Multi-Region** | `incoming/eu/` … → gewählte `base_url` in Config | Datenresidenz | Rein clientseitiges Routing; Region muss existieren |
| 15.15 | **Meta-Assistent** | `ghost ask "…"` → optional eigener Arctis-Workflow für Hilfe-Texte | Docs-on-demand | Opt-in; kein Pflichtpfad für Core |

**Rollout-Hinweis:** **15.1** (init-demo) und **15.6** (sandbox) am ehesten direkt nach Ghost-MVP; **15.3** (Safety) parallel; **15.9** (Extensions) erst nach stabiler Hook-Schnittstelle.

---

## 16. Epics (Erweiterung)

Zusätzlich zu §11:

| Epic | Inhalt |
|------|--------|
| **H — Ghost DX & PLG** | §15.1 FRE, §15.2 Explain, §15.4 Insights, Demo 60 |
| **I — Ghost Safety & Ops** | §15.3 Safety, §15.10 Heartbeat, §15.11 Remote |
| **J — Ghost Erweiterung** | §15.5 Profiles, §15.7 Auto-Recipe, §15.8 Verify, §15.9 Extensions |
| **K — Ghost Advanced** | §15.12 Predict, §15.13 Replay, §15.14 Multi-Region, §15.15 Meta |

---

*Revision: an Repository-Pfade und Rollout §12–§13 gebunden; Demos (Matrix + Demo 60) in §14; **Erlebnis-Schicht §15**; Epics/Erweiterung §16; Cursor-Reihenfolge in [arctis_ghost_prompt_series.md](arctis_ghost_prompt_series.md).*
