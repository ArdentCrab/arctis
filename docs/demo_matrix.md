# Ghost Demo‑Matrix (Skills, Routing, Evidence)

**Zweck:** Ein **Showcase‑Artefakt** für Ghost und die Customer‑Execute‑Skills — kompakt, tabellarisch, ohne neue Produktfeatures.  
Dient README, Docs, Schulungen und Demo‑Videos als **Referenzkarte**.

**Landingpage & Rollen:** Die **sechs Erlebnis‑Module** (C‑Level, Security, Tech, …), Kuratier‑Regeln und Story‑Arc stehen in [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md). Diese Datei bleibt die **technische** Matrix (Skills, Routing, Evidence).

**Ghost CLI — ehrliche Einordnung:** Befehle wie `run`, `watch`, `evidence`, **`explain`** (Kurzfassung pro Run-ID), `fetch`, `doctor`, `pull-artifacts`, `init-demo` und Rezepte (`run --recipe`) sind im Repo umgesetzt (siehe [ghost_implementation_prompts.md](ghost_implementation_prompts.md), Stand im Kopf). **Lokales PLG light (P8):** optionale Branding‑Felder in `envelope.json` und `__STATUS.txt` unter `outgoing_root` — [ghost_plg.md](ghost_plg.md); **ohne** serverseitige Durchsetzung durch den Client. **P10–P11** sind im CLI umgesetzt (Sandbox/Dry-Run; **`ghost heartbeat`** + Matrix [`ghost_p11_test_matrix.md`](ghost_p11_test_matrix.md)). **P12–P14** (Verify, Meta, Hooks, …) bleiben **Roadmap** — in Modul‑Texten der Landingpage‑Matrix als *Pilot* / *Roadmap* labeln.

**Verknüpfungen**

| Dokument | Nutzen |
|----------|--------|
| [demo_60.md](demo_60.md) | End‑to‑End‑Ablauf in ~60 s (`run` → `watch` → `evidence`) |
| [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md) | Story‑Module & Zielgruppen (Landingpage / Erzählbogen) |
| [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) | Kanonische Skill‑Tabelle & Architektur |

---

## 1. Skill‑Matrix

Alle hier gelisteten Skills sind **über das Execute‑Envelope** (`skills` im Body von `POST /customer/workflows/{workflow_id}/execute`) ansprechbar.  
Sie sind **advise‑only** (keine Engine‑/Policy‑Mutation durch den Skill selbst) und schreiben ihre Auswertung nach **`execution_summary.skill_reports[<skill_id>]`** (und spiegeln sich im **Evidence‑Envelope** unter `skill_reports`, konsistent mit E5).

| Skill `id` | Kurzbeschreibung | Typische Nutzdaten | Wo sichtbar (Ghost / API) |
|------------|------------------|--------------------|----------------------------|
| `prompt_matrix` | Schnappschuss zu Prompt‑/Matrix‑Kontext des Laufs (Advise‑Modus Standard). | `RunResult`, Pipeline‑Kontext | `skill_reports.prompt_matrix`; `ghost evidence` → Abschnitt **Skill Reports** |
| `routing_explain` | Lesbare Zusammenfassung aus `routing_decision` / Router‑Trace / Observability. | `output`, `execution_trace`, `observability` | `skill_reports.routing_explain` |
| `cost_token_snapshot` | Strukturierter Kosten‑ & Token‑Breakdown (E6‑kompatibel). | `RunResult`, Kostenfelder | `skill_reports.cost_token_snapshot`; passt zu **Costs & Tokens** in Run‑Summary |
| `input_shape` | Überblick über gemergtes Input‑/Template‑Shape (ohne Business‑Logik). | `SkillContext.merged_input`, Template | `skill_reports.input_shape` |
| `pipeline_config_matrix` | Matrix aus Engine‑Steps (Modelle, Temperaturen), Routing‑Kurzform, Policy‑Metadaten. | `pipeline_version`, `RunResult` | `skill_reports.pipeline_config_matrix` |
| `evidence_subset` | Deterministische Teilmenge aus dem Evidence‑Bundle (konfigurierbare Keys). | `evidence`, andere Reports | `skill_reports.evidence_subset` |
| `reviewer_explain` | Lesbarer Audit‑/Reviewer‑/Moderations‑Kontext aus Trace & `routing_decision`. | `execution_trace`, `policy_enrichment` | `skill_reports.reviewer_explain` |

**Hinweis:** Konkrete **Payload‑Felder** pro Skill können sich mit Engine‑Versionen leicht erweitern; stabil bleiben **`schema_version`**, **`provenance.skill_id`**, **`provenance.mode: advise`** und die Einbettung unter `skill_reports`.

---

## 2. Routing‑Matrix

Routing ist **produktseitig** an die Pipeline und den Governance‑Router gebunden. Die Ghost‑CLI zeigt eine **kompakte** Zeile (`ghost watch`), das Evidence‑Rendering eine **JSON‑Sektion** (`ghost evidence` → **Routing Decision**).

| Aspekt | Inhalt (konzeptionell) | Wo es typischerweise steckt |
|--------|-------------------------|-----------------------------|
| **Governance‑Routen (Katalog)** | `approve`, `manual_review`, `reject` — stabile Benennung für Erklärungen und Demos. | Skill `routing_explain` / Router‑Semantik (siehe Code‑Katalog) |
| **Entscheidungsobjekt** | Strukturierte Route, ggf. Modul‑Metadaten (`routing_decision` im Step‑Output). | `run.output[…].routing_decision` bzw. Spiegel in `execution_summary` je nach Lauf |
| **Modellbezug** | Welches Modell der Router oder ein AI‑Step referenziert, steht oft neben der Route oder in Step‑Outputs. | Kompakt in `watch`: `Routing: … (model=…)`; voll in **Routing Decision** JSON |
| **Scores / Policy** | Zusatzfelder (Scores, Policy‑Version) können in `policy_enrichment` / Skill‑Reports erscheinen — nicht jede Installation füllt alle Felder. | `execution_summary` / `skill_reports.*` / Evidence `policy_evidence` |

**Ehrliche Labels:** Fehlen Router‑ oder Policy‑Daten, liefern advise‑Skills **leere oder erklärende** Payloads — das ist **korrektes** Verhalten, kein Demo‑Fehler.

---

## 3. Evidence‑Matrix

Zwei Ebenen sind zu unterscheiden: **Run‑API** (`GET /runs/{run_id}`) und **Evidence‑Envelope** (E5) innerhalb der Summary.

### 3.1 Run‑Objekt (API‑Überblick)

| Bereich | Felder (typisch) | Ghost‑CLI |
|---------|------------------|-----------|
| Identität / Status | `run_id`, `status` (`running`, `success`, `failed`, …) | `watch` (farbig), `fetch` (JSON) |
| Ein-/Ausgabe | `input`, `output` | `evidence` (**Input** / **Output**), `watch` (kompakt) |
| Zusammenfassung | `execution_summary`: u. a. `cost`, `token_usage`, `steps`, `evidence`, `skill_reports` | `evidence` (**Costs & Tokens**, **Skill Reports**); `watch` (Kostenzeile) |

### 3.2 Evidence‑Envelope (`execution_summary.evidence`)

Gebaut durch `EvidenceBuilder` (Customer‑Execute); Schlüssel sind **stabil** und JSON‑freundlich:

| Schlüssel | Bedeutung (Kurz) |
|-----------|-------------------|
| `input_evidence` | Kanonisiertes Eingabe‑JSON + Roh‑`input` |
| `template_evidence` | Workflow‑Template‑Merge |
| `policy_evidence` | Reviewer‑Policy / Governance‑Snapshot |
| `routing_evidence` | Routing‑Metadaten (sofern aufgezeichnet) |
| `engine_evidence` | Step‑Trace‑Auszug (`steps`, `intermediate`) |
| `mock_evidence` | Mock‑Laufmarker + Input (Mock‑Pfad) |
| `cost_evidence` | Kostenstruktur |
| `snapshot_evidence` | Snapshot‑ID + Blob‑Referenz |
| `skill_reports` | Spiegel von `execution_summary.skill_reports` (E5 / A4) |

**Ghost `evidence`** blendet dieses tiefe Envelope nicht vollständig aus — es fokussiert **Input**, **Output**, **Routing Decision**, **Costs/Tokens** und **Skill Reports** aus der Summary, damit Demos **lesbar** bleiben. Für das **volle** Bundle: API `GET /runs/{run_id}/evidence` (wenn in deiner Umgebung freigeschaltet) oder `fetch` + Navigation im JSON.

---

## 4. Kurzablauf für Demos

1. **Skills wählen** — aus der Skill‑Matrix die passenden `id`s ins Execute‑JSON legen (siehe [demo_60.md](demo_60.md)).  
2. **Routing erklären** — mit `routing_explain` + Sektion **Routing Decision** in `ghost evidence`.  
3. **Evidence erzählen** — mit `cost_token_snapshot`, `pipeline_config_matrix`, `evidence_subset` (optional) die **Matrix** „von außen nach innen“ füllen.

Damit ist die **technische Demo‑Matrix** als **Ghost‑Referenzkarte** komplett; Erweiterungen (Tabellen‑Layout, zusätzliches ANSI) können auf diesem Gerüst aufsetzen, ohne die Faktenbasis zu ändern. **Marketing-/Modul‑Texte** bitte an [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md) spiegeln und gegen den **Implementierungs‑Stand** ([ghost_implementation_prompts.md](ghost_implementation_prompts.md)) prüfen.
