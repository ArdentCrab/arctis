# Ghost Demo‑60

Dies ist ein **technischer Walkthrough** (Terminal, ~60 Sekunden) für **Arctis Ghost** — komplementär zum **Storyboard** für Live/Video in [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) (Hook, Erzählfolge, Einwände).

**Kernaussage (eine Zeile):** Datei + Konfiguration → **Run** über die **bestehende** Customer‑API → **Watch** / **Evidence** mit **Skill‑Reports** und Routing — ohne Engine‑Import im Client, nur HTTP.

Er demonstriert:

- Ghost‑Config (`ghost.yaml`, Umgebungsvariablen)
- Run‑Ausführung (`ghost run` oder Rezept)
- Live‑Follow (`ghost watch`)
- Evidence‑Rendering (`ghost evidence`)
- Skill‑Reports (Auszug in Evidence; bei Execute mit `skills`‑Array auch in `GET /runs/{id}`)
- Routing‑Entscheid (kompakt in `watch`, ausführlicher in `evidence`)
- Kosten/Token‑Snapshot (Skill `cost_token_snapshot` und `execution_summary`)

**Stand im Repo (ehrlich):** CLI umfasst u. a. `doctor`, `pull-artifacts` (lokale `envelope.json` / `skill_reports/`), `init-demo`, lokaler **State** (`state_enabled`), **Rezepte** (`--recipe`). **P10–P11:** Sandbox/Dry-Run und **`ghost heartbeat`** (opt-in, siehe [ghost_p11_test_matrix.md](ghost_p11_test_matrix.md)). **Noch nicht** (siehe [ghost_implementation_prompts.md](ghost_implementation_prompts.md) P12–P14): z. B. lokales Verify, Meta, Hooks, weitere PLG‑Automation. Die **API** kann deterministische Demos mit Header **`X-Arctis-Mock: true`** unterstützen; der Ghost‑HTTP‑Client setzt diesen Header **standardmäßig nicht** — ggf. separater Aufruf (z. B. `curl`) oder zukünftiges CLI‑Flag.

Alle unten genannten **ghost**‑Befehle sind **1:1 im Terminal** ausführbar. Voraussetzung: Arctis‑API läuft (z. B. `http://localhost:8000`) und du hast einen gültigen **Workflow** sowie **API‑Key**.

---

## Setup

### Ghost installieren

Im Projektroot (Repository mit `pyproject.toml`):

```bash
pip install -e .
```

Damit steht das Kommandozeilen‑Tool **`ghost`** (bzw. `python -m arctis_ghost`) zur Verfügung.

### Config anlegen

Lege im Arbeitsverzeichnis eine `ghost.yaml` an. **`workflow_id` muss eine echte UUID** deines Workflows sein (nicht der Platzhalter `default`).

```yaml
active_profile: default
profiles:
  default:
    api_base_url: http://localhost:8000
    workflow_id: "00000000-0000-0000-0000-000000000000"  # ← durch deine Workflow‑UUID ersetzen
```

Optional: API‑Key per Umgebung (überschreibt ggf. Werte aus der YAML):

```bash
export ARCTIS_API_KEY="your-api-key-secret"
```

Weitere Optionen (Profile, Retries, Idempotency, **State**, **outgoing_root**): siehe Paket `arctis_ghost` und `ghost run --help` / `ghost --help`.

**Schnellstart‑Ordner:** `ghost init-demo [VERZEICHNIS]` legt `ghost.yaml`, `input.json` und `README.md` an (siehe Abschnitt 4).

---

## 1. Run starten

Erstelle eine Datei `input.json` mit **Execute‑Body** (Request an `POST /customer/workflows/{id}/execute`):

```json
{
  "input": {
    "query": "What is the capital of France?"
  },
  "skills": [
    {"id": "prompt_matrix"},
    {"id": "routing_explain"},
    {"id": "cost_token_snapshot"}
  ]
}
```

Starte den Run:

```bash
ghost run input.json
```

Die Ausgabe ist **nur die Run‑UUID** (eine Zeile), z. B.:

```text
4f3a1c2d-e29b-41d4-a716-446655440000
```

Diese UUID für die nächsten Schritte kopieren (`RUN_ID`).

---

## 2. Live‑Follow

```bash
ghost watch 4f3a1c2d-e29b-41d4-a716-446655440000
```

Ersetze die UUID durch deine `RUN_ID`. Der Bildschirm wird regelmäßig geleert und neu gezeichnet; typisch siehst du u. a.:

- **Status** farbig (`pending` / `running` / `success` oder `completed` / `failed`)
- **Kompakte** Zeilen zu Input, Output, Routing, Skill‑Namen, Kosten/Tokens

Beispielhaft (ohne ANSI‑Escape‑Sequenzen):

```text
=== Watching Run 4f3a1c2d-e29b-41d4-a716-446655440000 ===

Status: running

Input: {"query":"What is the capital of France?"}
Output: {}
Routing: approve (model=gpt-4.1-mini)
Skills: cost_token_snapshot, prompt_matrix, routing_explain
Cost: 0.0012 USD | tokens {"completion_tokens":18,"prompt_tokens":12}
```

Wenn der Lauf fertig ist, endet `watch` mit Exit‑Code **0** bei Erfolg (`success`/`completed`). Bei **Ctrl+C** brichst du ab (Exit‑Code **130**).

---

## 3. Evidence anzeigen

```bash
ghost evidence 4f3a1c2d-e29b-41d4-a716-446655440000
```

Ausgabe ist **strukturiert** (Überschriften mit ANSI‑Farben) plus **ungefärbtes** JSON pro Abschnitt. Auszug inhaltlich (Farbcodes weggelassen):

```text
=== Evidence for Run 4f3a1c2d-e29b-41d4-a716-446655440000 ===

--- Input ---
{
  "query": "What is the capital of France?"
}

--- Output ---
{
  "answer_step": "Paris"
}

--- Routing Decision ---
{
  "route": "approve",
  "model": "gpt-4.1-mini"
}

--- Costs & Tokens ---
cost:
0.0012

token_usage:
{
  "completion_tokens": 18,
  "prompt_tokens": 12
}

--- Skill Reports ---
--- Skill: cost_token_snapshot ---
{
  "payload": { ... },
  "provenance": { ... },
  "schema_version": "1.0"
}
```

Konkrete Pipeline‑Outputs hängen von deiner **Definition** und dem Engine‑Lauf ab; die **Befehle** und **Abschnitte** bleiben gleich.

---

## 4. Hilfskommandos (Diagnose, Artefakte, Demo‑Scaffold)

- **`ghost doctor`** — prüft `ghost.yaml`/Env, `GET /health`, optional mit `ARCTIS_API_KEY` `GET /pipelines`.
- **`ghost pull-artifacts RUN_ID`** — lädt den Run und schreibt unter `outgoing_root` (YAML/Env `outgoing_root` bzw. `ARCTIS_GHOST_OUTGOING_ROOT`) u. a. `envelope.json` (optional lokales **`branding`** aus Config), `skill_reports/*.json` und **`__STATUS.txt`** (Hinweis-Datei, keine API‑Durchsetzung; siehe [ghost_plg.md](ghost_plg.md)).
- **`ghost explain RUN_ID`** — ein **GET /runs** und kompakte Textzeilen (Input/Routing/Skills/Cost); volle JSON‑Abschnitte mit `ghost evidence`.
- **`ghost init-demo [VERZEICHNIS]`** — legt `ghost.yaml`‑Stub, `input.json`, `README.md` an (ohne `--force` kein Überschreiben).
- **`ghost run --recipe recipes/….yaml --input daten.json`** — Rezept (Defaults, `skills`, `input_mapping` json/text) bauen den Execute‑Body; optional `--merge-json`, `--workflow-id` (CLI > Rezept > Profil).

Lokaler **State** (Skip/Reuse gleicher Execute‑Bodies): in `ghost.yaml` `state_enabled: true` oder `ARCTIS_GHOST_STATE_ENABLED=on`; **`ghost run --force`** erzwingt immer einen neuen POST.

---

## 5. Optional: Roh‑JSON zum Run

```bash
ghost fetch 4f3a1c2d-e29b-41d4-a716-446655440000
```

Liefert das vollständige Run‑Objekt als JSON (ohne Evidence‑Layout).

---

## Fertig

**Ghost Demo‑60** zeigt in kurzer Folge:

| Schritt | Befehl | Inhalt |
|--------|--------|--------|
| Config | `ghost.yaml` + Env | Basis‑URL, Workflow, API‑Key |
| Optional | `ghost doctor` | Erreichbarkeit `/health`, optional `/pipelines` mit Key |
| Run | `ghost run input.json` (oder `--recipe … --input …`) | Execute inkl. Skills |
| Live | `ghost watch RUN_ID` | Polling, Statusfarben, Kompaktzeilen |
| Kurz | `ghost explain RUN_ID` | Kompakte Zeilen (ohne volle Skill‑JSON‑Blöcke) |
| Evidence | `ghost evidence RUN_ID` | Input/Output/Routing/Costs/Skill‑Reports |
| Optional | `ghost pull-artifacts RUN_ID` | Lokale Artefakte unter `outgoing_root/<run_id>/` |

Als Nächstes eignet sich die **Demo‑Matrix**: [demo_matrix.md](demo_matrix.md) — Skill‑, Routing‑ und Evidence‑Referenz; **Landingpage‑Module** und Erzählbogen in [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md).
