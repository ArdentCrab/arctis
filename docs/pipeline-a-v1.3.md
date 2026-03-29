# Arctis Pipeline Specification v1.3 (Engine-aligned)
**pipeline:** pipeline-a  
**status:** stable (an **Arctis Engine** Python-Implementierung und **Engine Spec v1.5** angeglichen)  
**author:** Noah  
**basis:** vollständige Übernahme von **v1.2** (Engine‑Abschnitte, Policies, Module, Engine‑Mapping **unverändert**) + **v1.3 Produkt‑/Go‑to‑Market‑Ergänzungen** (marktreif).

**Cross-Reference:** Technische Tiefe zu IR, Security und Marketplace siehe `docs/arctis_engine_and_security_spec_v1.5.md`. Dieses Dokument ist die **Pipeline‑A Produkt‑/Policy‑Spezifikation** mit exakter Abbildung auf die **jetzigen Engine‑Schnittstellen**.

---

## Purpose
Diese Spezifikation beschreibt die vollständige Architektur, Module, Policies, DSL und das Produkt‑Design der **Pipeline A**.  
Sie dient als:
- Technische Referenz für die Implementierung  
- Einheitliche Sprache für Cursor‑basierte Entwicklungen  
- Grundlage für alle zukünftigen Pipelines (Pipeline B, etc.)  
- Engine‑kompatibles Policy‑Set  

**Ausführungspfad (Implementierung):** `parse_pipeline` → `check_pipeline` → `generate_ir` → `optimize_ir` → `Engine.run(IRPipeline, tenant_context, …)`.

---

## Product Positioning & Messaging (v1.3)

### Zielgruppen
| Segment | Bedarf | Arctis Pipeline A Antwort |
|---------|--------|---------------------------|
| **Mid‑Market / Enterprise IT** | Governance, Audit, deterministische KI‑Entscheidungen | Immutable Versionen, Snapshots, Replay, Policy‑Layer ohne Agent‑Chaos |
| **Compliance / Risk** | Nachvollziehbarkeit, DSGVO, TOMs | Tenant‑Isolation, Residency, Audit‑Reports, Löschkonzepte (siehe DSGVO‑Abschnitt) |
| **Produkt‑ & Ops‑Teams** | Schnelle Integration, wenig Betrieb | Zero‑Maintenance‑SLA‑Rahmen, Sandbox, Wizard |
| **Entwickler** | Klare IR, testbare Runs | Engine‑Schnittstellen unverändert dokumentiert, DSL → IR → `Engine.run` |

### Value Proposition
- **Deterministische KI‑Entscheidungen** mit **versionierten Pipelines** und **replay‑fähigen Snapshots** — keine „Black Box“ in Produktion.
- **Strikte Trennung:** AI‑Transform (`ai`), Effects (`effect`), Kompensation (`saga`), Erweiterungen (`module`) — entspricht der implementierten Engine.
- **Betriebsentlastung:** Self‑Service‑Wizard, Workflows, Rate‑Limits & Operational Policies als Rahmen; SLA‑Ziele für Verfügbarkeit und Incident‑Reaktion (siehe SLA‑Abschnitt).

### Differenzierung
| Thema | Typische Prompt‑Tools / Agent‑Frameworks | Pipeline A |
|-------|------------------------------------------|------------|
| Determinismus | Oft schwierig garantierbar | `temperature=0`, IR‑Graph, Replay |
| Side‑Effects | Oft implizit | Explizite `effect`/`saga`, Idempotenz‑Policy |
| Multi‑Tenant‑Isolation | Variiert | `tenant_id`‑Durchgängigkeit, Snapshot‑/Run‑Zugriffskontrolle |
| Audit | Add‑on | Audit & Snapshot als Kernmodul‑Konzept |

### Pricing‑Begründung (Kurz)
- **Basispreis (199–499 €)** deckt **plattformseitige** Betriebs‑ und Supportkosten, API‑/UI‑Nutzung und Standard‑Module ab.
- **Upsells** (Analytics, Multi‑Model, Integrations) reflektieren **Mehrwert** (Drift‑Einblick, Modell‑Fallbacks, zusätzliche Connectors) und **höheren Integrations‑/Support‑Aufwand**.
- **Keine Setup‑Gebühren:** Onboarding über Wizard + Dokumentation; langfristige Bindung über Produktqualität, nicht durch Einmalgebühren.

---

## Architecture Overview
Pipeline A besteht aus **6 Layern** (Produktlogik); die **Engine** mappt diese auf **Compiler + IR + Runtime**:

| Layer | Beschreibung | Engine‑Zuordnung |
|-------|----------------|------------------|
| 1. Input Layer | Sanitizer, Schema‑Validation, Prompt‑Sanitization, Forbidden‑Fields, Budget‑Limits, Residency‑Enforcement | **ComplianceEngine** (Budget, Residency, Resource‑Limits), **AITransform** (Secrets im Prompt), Vorverarbeitung als **`module`‑Steps** oder extern vor `Engine.run` |
| 2. AI Decision Layer | Deterministischer LLM‑Aufruf, Output‑Validation, Confidence‑Thresholds, Weighted Routing (optional) | **`ai`**‑Steps (`AITransform`); Validierung/Routing als **`module`** oder Folge‑Graph |
| 3. Routing Layer | Entscheidungs‑Routing zu Effect‑Chains (approve, reject, manual_review) | **IR‑DAG** (`IRNode.next`); kein eigener Step‑Typ `router` — Verzweigung über Graph‑Topologie |
| 4. Effects Layer | Ausführung von Effekten (HTTP, SQL, Email, Webhook, etc.) mit Idempotenz & Saga‑Rollback | **`effect`** (`EffectEngine`), **`saga`** (`SagaEngine`) |
| 5. Audit & Replay Layer | Audit‑Reports (JSON/PDF), Snapshot‑Speicherung, Snapshot‑Replay, Observability (Logs, Traces) | **`AuditBuilder`**, **`SnapshotStore`**, **`ObservabilityTracker`**; Replay via `Engine.run(..., snapshot_replay_id=...)` |
| 6. Deployment & Config Layer | Self‑Service‑Wizard, Konfigurations‑UI, Versioning, Zero‑Maintenance‑Architektur | Produkt/Control‑Plane; **ModuleRegistry** für signierte Marketplace‑Module |

Alle Layer sind **engine‑kompatibel** und auf **Zero‑Maintenance** ausgelegt.

---

## SLA & Service Level — Zero‑Maintenance konkret (v1.3)

**Zero‑Maintenance** bedeutet für den Kunden: **kein Betrieb der Arctis‑Laufzeit‑Logik** (Deployments der Engine‑Minor‑Updates, Skalierung der Control‑Plane, Patch‑Management der verwalteten SaaS‑Schicht). Es bedeutet **nicht** die Abwesenheit von **Kunden‑Pflichten** (eigene LLM‑Keys, gültige Konfiguration, Einhaltung der Fair‑Use‑Limits).

### Verfügbarkeit (Zielwerte, Produktions‑SaaS)
| Metrik | Ziel | Messfenster |
|--------|------|-------------|
| **API‑Verfügbarkeit** | ≥ 99,5 % | rolling 30 Tage (exkl. geplanter Wartung) |
| **Control‑Plane (UI)** | ≥ 99,0 % | rolling 30 Tage |
| **Geplante Wartung** | ≤ 4 h / Monat | Ankündigung ≥ 48 h (E‑Mail / Statuspage) |

*Hinweis:* Abweichungen sind in **AVV** / individuellen Enterprise‑Verträgen definierbar.

### Incident‑Handling
| Schweregrad | Definition | Erstreaktion | Status‑Update |
|---------------|------------|--------------|---------------|
| **P1 — Kritisch** | Gesamtausfall API oder Datenverlust‑Risiko | ≤ 30 min (werktags) | alle 60 min |
| **P2 — Hoch** | Wesentliche Degradation (z. B. >10 % Fehlerquote) | ≤ 4 h | alle 4 h |
| **P3 — Mittel** | Einzelne Funktionen / UI | nächster Arbeitstag | nach Fix |
| **P4 — Niedrig** | Kosmetik, Feature‑Requests | Backlog | nach Planung |

**Kanäle:** Support‑Ticket (siehe Support‑Abschnitt), Statuspage für **P1/P2**.

### Recovery‑Ziele (RTO / RPO)
| Objekt | RTO (Recovery Time Objective) | RPO (Recovery Point Objective) |
|--------|------------------------|------------------------|
| **Konfiguration** (Pipelines, Workflows, Keys‑Metadaten) | ≤ 4 h | ≤ 1 h |
| **Audit / Snapshots** (persistiert) | ≤ 8 h | ≤ 24 h |
| **Tenant‑Billing‑Daten** | ≤ 24 h | ≤ 24 h |

*Engine‑Hinweis:* In‑Memory‑Snapshots der Referenz‑Engine sind **persistenz**‑seitig vom Produkt zu übernehmen; RPO bezieht sich auf die **persistierte** Produktvariante.

### Fehlerklassen (für SLA & Support)
| Klasse | Beispiele | Verantwortung |
|--------|-----------|----------------|
| **A — Plattform** | Arctis‑API‑5xx, Region‑Ausfall | Arctis |
| **B — Kundenkonfiguration** | Ungültiges Schema, fehlende Keys, Quota‑Überschreitung | Kunde |
| **C — Drittanbieter** | LLM‑Provider‑Outage, Ziel‑HTTP‑Endpoint des Kunden | Kunde / Drittanbieter (mit Unterstützung bei Integration) |
| **D — Geplante Änderungen** | Major‑Version‑Migration, Deprecation | Arctis (kommuniziert) |

### Self‑Healing‑Mechanismen (Produktziel)
- **Retry / Backoff** gemäß Operational Policies (automatisch für transient Netzwerk‑Fehler).
- **Circuit Breaker** (automatisches Abfangen, kein „Hammering“ bei 5xx).
- **Health‑Checks** der Control‑Plane; automatische **Neustarts** instanzer Kompaktservices (Implementierungsdetail).
- **Kein** Self‑Healing für **fachlich falsche** Pipeline‑Configs — Kunde erhält klaren `ARCTIS_*`‑Code.

### Grenzen der Verantwortung
- **Keine Garantie** für Verfügbarkeit oder Latenz **externer** LLM‑ oder Kunden‑Endpoints.
- **Kein** 24/7‑Support im Standard‑Preis inklusive (siehe **Support‑Abschnitt**); optional **Enterprise** mit SLA‑Anhang.
- **Compliance‑Nachweise** (SOC2, ISO) als **Roadmap** / Enterprise‑Angebot; nicht Bestandteil des Basis‑SaaS‑Dokuments in v1.3.

---

## Engine: Pflicht‑Schnittstellen (Single Source of Truth)

Dieser Abschnitt benennt **alle** für Pipeline A relevanten öffentlichen Schnittstellen der aktuellen Python‑Engine (`arctis.engine`, `arctis.compiler`).

### Compiler & IR
| Schnittstelle | Signatur / Struktur | Rolle |
|---------------|---------------------|--------|
| `parse_pipeline` | `(pipeline_definition: str \| dict) -> PipelineAST` | Akzeptiert **dict** mit `name`, `steps` (Liste von Steps) oder **einzeiligen** Pipeline‑Namen (ohne Steps). |
| `check_pipeline` | `(ast: PipelineAST) -> None` | Strukturvalidierung (einzigartige Namen, `next`‑Referenzen, keine Zyklen). |
| `generate_ir` | `(ast: PipelineAST) -> IRPipeline` | Lowering zu Graph: `IRNode(name, type, config, next: list[str])`, `entrypoints`. |
| `optimize_ir` | `(ir: IRPipeline) -> IRPipeline` | Erreichbare Knoten, normalisierte Kanten, deterministische Ordnung. |
| `StepAST` | `name, type, config: dict, next: str \| None` | Ein Step; flache Zusatzfelder werden in `config` gemerged. |
| `IRNode` | wie oben; `next` ist **Liste** (derzeit pro Step typisch ein Ziel). |
| `IRPipeline` | `name, nodes: dict[str, IRNode], entrypoints: list[str]` | Eingabe für `Engine.run`. |

### Laufzeit‑Schritttypen (`IRNode.type`)
Nur diese vier Typen werden von `Engine.run` ausgeführt:

| `type` | Pflicht‑`config` / Semantik |
|--------|-----------------------------|
| `ai` | `input` (beliebig), `prompt` (str). Optional weitere Keys nach Schema‑Erweiterung. |
| `effect` | Dict für `EffectEngine`: `type` ∈ `{write, delete, upsert}`, `key` (str, nicht leer), `value`. |
| `saga` | `action`: dict, `compensation`: dict (beide Pflicht nach `SagaEngine.validate_compensation`). |
| `module` | `using`: registrierter Modulname (String); Signaturprüfung über `ModuleRegistry.verify_signature`. |

### Tenant‑Kontext (`TenantContext`)
Pflichtattribute für `Engine.run` (Validierung in `runtime._validate_tenant_context`):

| Attribut | Typ | Bedeutung |
|----------|-----|-----------|
| `tenant_id` | `str` | Mandanten‑Isolation (Snapshots, Observability, Effects‑Lookup). |
| `data_residency` | `str` | Muss zu **`Engine.ai_region`** passen für AI (`AITransform.enforce_boundaries`); Default `"US"`. |
| `budget_limit` | `float \| None` | Obergrenze für **simulierte** CPU‑Kosten (`ComplianceEngine.enforce_budget`). |
| `resource_limits` | `dict` oder Objekt mit `cpu` / `memory` / `time` bzw. `max_wall_time_ms` | Grenzen für simulierte CPU, Speicher, Laufzeit. |
| `dry_run` | `bool` | Im Kontext vorhanden (Compliance‑Tests); Persistenz von Effekten gemäß Suite/Policy. |

Zusätzlich nutzt die Engine intern **`Engine.service_region`** (z. B. `set_service_region`) für **`ComplianceEngine.enforce_residency`** gegenüber `tenant_context.data_residency`.

### Engine‑Klasse (`Engine`) — öffentliche API
| Methode | Zweck |
|---------|--------|
| `run(ir, tenant_context, snapshot_replay_id=None) -> RunResult` | Haupteintritt; bei gesetztem `snapshot_replay_id` Replay aus `SnapshotStore` (Tenant‑Check). |
| `get_snapshot(tenant_context, snapshot_id)` | Snapshot lesen (Tenant‑Isolation). |
| `get_effects(tenant_context, run_id=None)` | Effect‑Store (Tenant/Run‑Isolation). |
| `observability_trace(tenant_context, run_id)` | Observability‑Payload pro Run. |
| `build_audit_report(...)` | Vollständiger Report (10 Positionsargumente) oder Kurzform löst `ComplianceError` aus — siehe Implementierung. |
| `load_module(...)` / `tamper_module(...)` | Marketplace‑Module laden / Test‑Tampering. |
| `set_ai_region` / `set_service_region` | Region für AI bzw. Service für Residency. |
| `set_simulated_*_for_next_run` | CPU, Speicher, Laufzeit für nächsten Lauf (deterministische Kosten). |
| `inject_failure` / `inject_compensation_failure` | Test‑Hooks für Saga. |
| `collect_ai_transform_prompts` | Gesammelte Prompts der letzten AI‑Steps. |

### Subsysteme (Implementierungskontrakte)
| Komponente | Kern‑API |
|------------|----------|
| `AITransform` | `validate_schema`, `enforce_boundaries`, `run_transform` → deterministisches `{"result": "deterministic:<sha256>"}`. |
| `EffectEngine` | `validate_effect`, `is_idempotent`, `apply_effect` → Records mit `key`, `type`, `value`, `version`, `idempotent`. |
| `SagaEngine` | `validate_compensation`, `execute_saga`, `rollback`. |
| `ComplianceEngine` | `enforce_budget`, `enforce_residency`, `enforce_resource_limits`. |
| `SnapshotStore` | `save_snapshot`, `load_snapshot`, `list_snapshots` — Payload: `pipeline_name`, `tenant_id`, `execution_trace`, `output`. |
| `AuditBuilder` | `build_report(ir, tenant_context, run_id, snapshot_id, execution_trace, effects, output, observability, compliance_info, timestamp)`. |
| `ObservabilityTracker` | `record_step`, `build_trace` → `{dag, steps}`. |
| `PerformanceTracker` | `compute_step_costs`, `compute_cost`, `record_usage`. |
| `ModuleRegistry` | `load_module`, `verify_signature` (unsigned / mismatch → `SecurityError`). |

### `RunResult` (Ausgabe von `Engine.run`)
Felder: `output`, `effects`, `snapshots` (Handle mit `id` / `primary_id`), `execution_trace` (`RunTrace` mit `run_id`), `audit_report`, `observability`, `cost`, `step_costs`, `cost_breakdown`.

### Ausnahmen
`SecurityError`, `ComplianceError`, `SagaError` (`arctis.errors`); Validierungsfehler oft `ValueError`. Produkt‑Error‑Codes (`ARCTIS_*`) unten sind **normativ** für API‑Layer; die Engine mappt semantisch auf diese Meldungen/Exceptions.

---

## Policies (gruppiert)

### Prompt Policy
- Prompts dürfen **keine dynamischen Felder** enthalten, die nicht im Input‑Schema definiert sind.
- Prompts müssen **deterministisch** sein (keine Zufallselemente außerhalb von `temperature=0`).
- Jede Änderung am Prompt erzeugt eine neue Pipeline‑Version.
- Snapshots referenzieren exakt die Prompt‑Version, die beim Run verwendet wurde (Produkt); technisch speichert der Snapshot **`output`** und **`execution_trace`** (erweiterbar um Prompt‑Version in `AuditBuilder`/Metadaten).

### Effect Policy
- Jeder Effect muss **idempotent** sein (gleiche `key` + gleiche semantische Wirkung — Engine: `EffectEngine.is_idempotent`).
- Jeder Effect muss eine **kompensierende Aktion** definieren (für Saga‑Rollback), falls er nicht rein lesend ist — technisch über **`saga`**‑Steps mit `compensation`.
- Effects dürfen **keine AI‑Calls** enthalten.
- **Whitelist (Engine):** erlaubte `type`‑Werte: `write`, `delete`, `upsert`.

### Routing Policy
- Routing darf **keine dynamischen Modelle** aktivieren (Ausnahme: Multi‑Model‑Upsell, das explizit aktiviert sein muss).
- Routing muss **deterministisch** sein (gleicher Confidence‑Wert führt immer zum gleichen Ziel) — im IR: feste Kanten, deterministische Step‑Reihenfolge (`sorted` Nachfolger in der Queue).
- Routing‑Entscheidungen werden im Snapshot festgehalten und sind replay‑fähig (über gespeicherten `output` / Trace).

### Security Policy
- **Keine Secrets** im Prompt, im Audit‑Report, im Snapshot, in Logs, in Effect‑Payloads.
- Secrets (LLM‑Keys, Arctis‑Keys) werden nur im verschlüsselten Key‑Store gehalten und niemals im Klartext geloggt.
- Alle externen Aufrufe (LLM, Effects) müssen über TLS 1.3 erfolgen (Produkt/Deployment); Engine: `AITransform.enforce_boundaries` prüft **verbotene Secret‑Strings** in `Engine.forbidden_secrets`.

### Versioning Policy
- Jede Änderung an einer Pipeline (Prompt, Schema, Routing, Effects) erzeugt eine neue **immutable Version**.
- Versionen folgen **Semantic Versioning** (`major.minor.patch`).
- Snapshots referenzieren die exakte Pipeline‑Version (Produkt); IR‑`name` ist der Pipeline‑Name im Compiler.
- Replays nutzen dieselbe Version wie der Original‑Run (über `snapshot_replay_id`).

### Workflow Policy
- Workflows speichern wiederverwendbare Pipeline‑Ausführungen.
- Workflows bestehen aus: Name, Pipeline‑ID, Pipeline‑Version, Input‑Template, Metadata.
- Workflows dürfen keine Pipeline‑Konfiguration überschreiben.
- Workflows sind pipeline‑versioned und immutable.
- Workflows sind tenant‑scoped.
- Workflows dürfen keine Secrets enthalten.
- Workflows müssen deterministisch bleiben.
- Workflows dürfen nur Felder enthalten, die im Input‑Schema der Pipeline definiert sind.

### Operational Policies
- **Retry Policy**: max_retries 3, exponentieller Backoff (100ms, 300ms, 900ms), retry_on: Netzwerk‑Timeouts, 5xx‑Fehler.
- **Circuit Breaker**: failure_threshold 5 innerhalb 60s, open_after 30s, reset_after 30s.
- **Rate‑Limit**: pro Tenant 1000/min, pro Pipeline 100/min, pro API‑Key 200/min.

### Testing Policies
- **Unit Test Policy**: Jedes Modul muss Unit‑Tests für Determinismus, Fehler‑Codes, Idempotenz haben.
- **Integration Test Policy**: Jede Pipeline‑Version durchläuft End‑to‑End‑Tests mit Mock‑LLM und Mock‑Effects.
- **Replay Test Policy**: Jeder Test‑Snapshot muss replizierbar sein (identisches Ergebnis) — Engine: `Engine.run(..., snapshot_replay_id=...)`.

### Future‑Proofing Rules
- Neue Upsells als **Modul** definieren, optional aktivierbar, Policies einhaltend (`ModuleRegistry` + signierte Artefakte).
- Neue Pipelines als eigenständige Specs, können auf Module von Pipeline A zurückgreifen.
- Engine‑Updates abwärtskompatibel; bei Breaking Changes neue `major`‑Version, alte bleibt für existierende Pipelines erhalten.

---

## Module Definitions (alphabetisch)

Jedes Modul folgt diesem Schema:

```md
### Module: <name>
type: <input|ai|routing|effect|audit|config>
status: default|optional|upsell
description: <kurze Beschreibung>

inputs:
  - <feld>: <typ>
outputs:
  - <feld>: <typ>

policies:
  - <policy 1>
  - <policy 2>

engine:
  compatible: true|false
  notes: <engine‑spezifische Hinweise>

errors:
  - <error_case>
```

### Default Module (immer enthalten)

#### Module: ai_decision
type: ai  
status: default  
description: Deterministischer LLM‑Aufruf (Transform).  
inputs: `input: any`, `prompt: string`  
outputs: `result: string` (deterministischer Hash‑String in aktueller Engine)  
policies:  
  - temperature = 0 (Produkt; Engine liefert deterministischen Output unabhängig von echtem LLM im Stub)  
  - Data‑Residency: `tenant_context.data_residency` ≡ `Engine.ai_region`  
  - keine Secrets in `prompt` (`forbidden_secrets`)  
engine: compatible: true  
notes: IR‑`type`: **`ai`**; Konfiguration siehe `AITransform`.  
errors: `ARCTIS_AI_001` (model_error), `ARCTIS_AI_002` (invalid_output_schema)

#### Module: ai_output_validator
type: ai  
status: default  
description: Validiert LLM‑Output gegen Schema.  
inputs: `output: object`  
outputs: `validated_output: object`  
policies:  
  - Schema aus Pipeline‑Config  
engine: compatible: true  
notes: Als **`module`**‑Step mit `using: <validator>@…>` oder Erweiterung von `AITransform`; derzeit Konzept/Produkt.  
errors: `ARCTIS_AI_003` (output_schema_mismatch)

#### Module: audit_reporter
type: audit  
status: default  
description: Erzeugt Audit‑Berichte und speichert Snapshots.  
inputs: `run_context: object`  
outputs: `report_url: string`, `snapshot_id: string`  
policies:  
  - JSON‑Report immer, PDF optional  
  - Snapshot enthält Input, Prompt, Modell‑ID, Seed, Temperatur, Output, Effects‑Logs (Produkt); Engine: `SnapshotStore` + `AuditBuilder`  
engine: compatible: true  
errors: `ARCTIS_AUDIT_001` (report_generation_failed)

#### Module: budget_limiter
type: input  
status: default  
description: Bricht Pipeline ab, wenn Kostenlimit überschritten wird.  
inputs: `estimated_cost: number`, `limit: number`  
outputs: `status: string`  
policies:  
  - Pre‑flight Schätzung (Token)  
  - Post‑flight Check  
engine: compatible: true  
notes: Umsetzung über **`ComplianceEngine.enforce_budget`** und simulierte Kosten (`set_simulated_cpu_units_for_next_run`).  
errors: `ARCTIS_INPUT_006` (budget_exceeded)

#### Module: confidence_router
type: routing  
status: default  
description: Entscheidet basierend auf Confidence über das Ziel (approve, reject, manual_review).  
inputs: `confidence: number`  
outputs: `route: string`  
policies:  
  - thresholds: approve >= 0.7, reject <= 0.3, sonst manual_review  
  - thresholds sind pro Pipeline konfigurierbar  
engine: compatible: true  
notes: **Kein** eigener IR‑Typ; Abbildung als **verzweigter DAG** (`next`) oder **`module`**, das Routen berechnet.  
errors: `ARCTIS_ROUTING_001` (invalid_threshold)

#### Module: effect_executor
type: effect  
status: default  
description: Führt eine Effect‑Chain aus.  
inputs: `effects: list`, `context: object`  
outputs: `results: list`  
policies:  
  - Idempotenz (`key`‑basiert)  
  - Saga‑Rollback bei Fehlern  
engine: compatible: true  
notes: IR‑`type`: **`effect`**; ein Step pro logischem Effect oder Sequenz über Graph.  
errors: `ARCTIS_EFFECT_001` (effect_failed), `ARCTIS_EFFECT_002` (rollback_failed)

#### Module: forbidden_fields_enforcer
type: input  
status: default  
description: Stellt sicher, dass bestimmte Felder nicht im Prompt erscheinen.  
inputs: `prompt: string`, `forbidden_fields: list`  
outputs: `enforced_prompt: string`  
policies:  
  - Kann strenger sein als Sanitizer  
  - Entfernt Felder, nicht nur maskieren  
engine: compatible: true  
notes: Ergänzt `AITransform` / Modul vor AI; Engine unterstützt `forbidden_secrets` Listen auf Prompt‑Ebene.  
errors: `ARCTIS_INPUT_005` (forbidden_field_in_prompt)

#### Module: prompt_sanitizer
type: input  
status: default  
description: Entfernt Prompt‑Injection‑Patterns.  
inputs: `prompt_template: string`, `context: object`  
outputs: `sanitized_prompt: string`  
policies:  
  - Standard‑Filterliste („Ignore previous instructions“, System‑Prompt‑Überschreibungen)  
  - Optional erweiterbar durch Kunde  
engine: compatible: true  
notes: Typisch **`module`** oder Preprocessing außerhalb der Engine.  
errors: `ARCTIS_INPUT_004` (prompt_injection_detected)

#### Module: residency_enforcer
type: input  
status: default  
description: Wählt LLM‑Endpunkt basierend auf Region aus.  
inputs: `request: object`, `allowed_regions: list`  
outputs: `selected_endpoint: string`  
policies:  
  - Mapping von API‑Keys zu Regionen  
  - Fallback auf andere Region, falls erlaubt  
engine: compatible: true  
notes: **`ComplianceEngine.enforce_residency`** (Tenant `data_residency` vs `Engine.service_region`); AI: **`AITransform.enforce_boundaries`** (Tenant vs `ai_region`).  
errors: `ARCTIS_INPUT_007` (no_endpoint_in_region)

#### Module: sanitizer
type: input  
status: default  
description: Entfernt oder maskiert Felder basierend auf Kunden‑Regeln.  
inputs: `raw_input: object`  
outputs: `sanitized_input: object`  
policies:  
  - darf keine neuen Felder hinzufügen  
  - muss deterministisch sein  
  - Pfad‑basiertes Redact (JSON‑Path)  
engine: compatible: true  
notes: Als **`module`** oder Vorverarbeitung.  
errors: `ARCTIS_INPUT_001` (forbidden_field_detected), `ARCTIS_INPUT_002` (invalid_json)

#### Module: schema_validator
type: input  
status: default  
description: Validiert Input gegen JSON‑Schema.  
inputs: `input: object`  
outputs: `validated_input: object`  
policies:  
  - Schema muss vom Kunden definiert werden  
  - Kann deaktiviert werden  
engine: compatible: true  
notes: Als **`module`**‑Step; Compiler validiert nur Pipeline‑Struktur, nicht JSON‑Schema.  
errors: `ARCTIS_INPUT_003` (schema_validation_failed)

#### Module: workflow_manager
type: config  
status: default  
description: Ermöglicht Kunden, wiederverwendbare Workflows für Pipelines zu speichern.  
inputs:
  - pipeline_id: string
  - pipeline_version: string
  - input_template: object
  - metadata: object
outputs:
  - workflow_id: string
policies:
  - Workflows sind pipeline‑versioned (immutable)
  - Workflows sind tenant‑scoped
  - Workflows dürfen keine Secrets enthalten
  - Workflows dürfen nur Felder enthalten, die im Input‑Schema der Pipeline definiert sind
engine:
  compatible: true
  notes: Workflows sind reine Konfiguration; sie erzeugen keine Engine‑Steps, füllen aber **`ai`‑`input`** / Kontext beim Aufruf.
errors:
  - `ARCTIS_WORKFLOW_001` (invalid_template)
  - `ARCTIS_WORKFLOW_002` (pipeline_version_not_found)
  - `ARCTIS_WORKFLOW_003` (forbidden_field_in_workflow)
  - `ARCTIS_WORKFLOW_004` (workflow_name_conflict)

---

### Upsell Modules (Optional / Bezahlt)

#### Module: advanced_integrations
type: effect  
status: upsell  
description: Erweiterte Integrationen (Slack, Teams, Jira, ServiceNow, HubSpot, Pipedrive, Notion, Airtable, Google Sheets, PostgreSQL Advanced, MySQL Advanced).  
engine: compatible: true  
notes: Müssen als **`effect`**‑Konfiguration oder externe Connectors abbildbar sein; Idempotenz‑Policy bleibt.

#### Module: analytics_pack
type: optional  
status: upsell  
description: Erweiterte Analytics und Drift‑Monitoring.  
features:
  - Decision‑Trends
  - Confidence‑Heatmaps
  - Drift‑Alerts
  - Token‑Cost‑Analytics
  - Latenz‑Analytics
  - Error‑Analytics
engine: compatible: true  
notes: Nutzt **`ObservabilityTracker`** / `audit_report` als Datenbasis.

#### Module: multi_model_engine
type: ai  
status: upsell  
description: Multi‑Model Fallback, Cost‑Optimized Routing, Region Switching.  
policies:
  - Model‑Switching muss deterministisch sein
  - Fallback‑Kette muss definiert sein
  - Residency wird weiterhin eingehalten
engine: compatible: true  
notes: Erweiterung um **`ai`**‑Konfiguration und Policy‑Schicht; keine zweite AI‑Instanz ohne Review.

---

## Key Management Policy

### Customer LLM Keys
- Kunden müssen eigene LLM‑Keys eintragen (OpenAI, Anthropic, Azure, Gemini, Mistral).
- Keys werden **verschlüsselt** gespeichert (AES‑256, tenant‑separat).
- Keys können rotiert werden; alte Keys werden nach definierter Frist gelöscht.
- Keys sind **tenant‑scoped** und dürfen nicht zwischen Tenants geteilt werden.
- Keys werden **nie geloggt**.
- Pro Key können Modelle und erlaubte Regionen definiert werden.

### Arctis API Key
- Jeder Kunde erhält einen eigenen Arctis‑Key (tenant‑scoped).
- Der Key ist **pipeline‑scoped** (kann auf eine oder mehrere Pipelines beschränkt werden).
- Key ist rotierbar.
- Key wird für alle API‑Aufrufe verwendet (Ausführung, Konfiguration, Audit‑Abruf).
- Key darf nicht zwischen Tenants geteilt werden.

---

## DSGVO & Datenschutz — TOMs & Verarbeitung (v1.3)

Dieser Abschnitt ergänzt die **Security Policy** und **Key Management Policy** um **Art. 32 DSGVO** (TOMs), **Auftragsverarbeitung** und **Rollen** — ohne die dortigen technischen Engine‑Fakten zu ändern.

### Datenflussdiagramm (logisch)

```text
[Kunde / Endnutzer]
        |
        v  (HTTPS TLS 1.3)
[Arctis API / UI] ------> [Tenant-scoped Speicher]
        |                      (Konfig, Metadaten, Keys verschlüsselt)
        v
[Pipeline Engine / Compiler] ------> [Snapshots & Audit Reports]
        |                                    |
        v                                    v
[LLM Provider (Kunden-Key)]          [Object Storage / DB]
        ^                                    |
        |                                    v
        +------------ [Effects-Ziele] <-------+
              (Kunden-Endpunkte / Connectors)
```

**Prinzip:** Verarbeitung **tenant‑isoliert**; **keine** Secrets in Logs/Audit im Klartext (siehe Security Policy).

### Speicherorte (Produktannahme)
| Datenart | Typischer Speicher | Region |
|----------|-------------------|--------|
| Tenant‑Metadaten, Pipeline‑Versionen | PostgreSQL (verschlüsselte Ruhezustands‑Festplatte) | gemäß **Deployment‑Region** / Kundenwahl |
| LLM‑Keys (Kunde) | Spalte `encrypted_key` (AES‑256, tenant‑separat) | wie oben |
| Snapshots / Audit‑Artefakte | DB JSONB + Object Storage (PDF) | wie oben |
| Logs / Traces | zentralisiertes Logging (keine Secrets) | EU oder US‑Cluster je nach Produktlinie |

### Verschlüsselung
- **Transit:** TLS 1.3 für alle externen APIs (Security Policy).
- **Ruhend:** Datenbank‑ und Volume‑Verschlüsselung (Cloud‑Provider‑Standard); **Application‑Layer** für LLM‑Keys (AES‑256).
- **Backups:** ebenfalls verschlüsselt; Zugriff nur für **least‑privilege** Ops‑Rollen.

### Zugriffskontrolle
| Rolle | Rechte |
|-------|--------|
| **Tenant Admin (Kunde)** | Voller Zugriff auf eigene Pipelines, Keys (rotate), Workflows, Billing‑Lesen |
| **Tenant Developer** | API‑Keys, begrenzte Pipelines, keine Billing‑Änderung |
| **Arctis Support (L1/L2)** | Nur mit **explizitem Ticket‑Token** / Zeitfenster; kein direkter Key‑Export |
| **Arctis Ops** | Infrastruktur; **kein** Zugriff auf Klartext‑Kundendaten ohne Audit‑Trail |

### Löschkonzept
- **Kunden‑initiiert:** Tenant‑Offboarding → Löschung personenbezogener Metadaten nach **definierter Frist** (z. B. 30–90 Tage für Rechnungsnachweise je Rechtsraum).
- **Snapshots / Runs:** konfigurierbare **Retention** (z. B. 90 / 365 Tage); danach automatische Löschung oder Anonymisierung der **personenbezogenen** Anteile im Input.
- **Keys:** nach Rotation **Grace‑Period**, dann unwiederbringliche Löschung der alten Ciphertext‑Version.

### Auftragsverarbeitung (AVV)
- **Verantwortlicher:** Kunde (sofern personenbezogene Daten von Endnutzern verarbeitet werden).
- **Auftragsverarbeiter:** Arctis (für die Plattform‑Verarbeitung).
- **Inhalt AVV:** Zweckbindung, TOMs, Unterauftragsverarbeiter‑Liste (Cloud‑Provider), **Drittlandtransfers** nur mit geeigneten Garantien (SCC / Angemessenheitsbeschluss).

### Rollen & Verantwortlichkeiten (RACI‑Kurz)
| Thema | Kunde | Arctis |
|-------|-------|--------|
| Rechtmäßigkeit der Verarbeitung | **R/A** | C |
| TOMs technisch umsetzen | C | **R/A** |
| LLM‑Provider‑Verträge | A | I |
| Inhalt der Pipelines / Prompts | **R/A** | I |

*(R=Responsible, A=Accountable, C=Consulted, I=Informed)*

---

## Technical Details

### Database Schema (PostgreSQL / kompatibel)

```sql
-- tenants
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- pipeline_versions (immutable)
CREATE TABLE pipeline_versions (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    pipeline_id UUID NOT NULL,
    version TEXT NOT NULL,        -- semver
    config JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, pipeline_id, version)
);

-- pipelines (current version pointer)
CREATE TABLE pipelines (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    name TEXT NOT NULL,
    current_version_id UUID REFERENCES pipeline_versions(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- snapshots
CREATE TABLE snapshots (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    pipeline_id UUID REFERENCES pipelines(id),
    pipeline_version_id UUID REFERENCES pipeline_versions(id),
    snapshot_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- audit_reports (JSON, PDF stored in S3, reference in DB)
CREATE TABLE audit_reports (
    id UUID PRIMARY KEY,
    snapshot_id UUID REFERENCES snapshots(id),
    report_type TEXT,             -- 'json', 'pdf'
    storage_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- api_keys (Arctis keys)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    key_hash TEXT NOT NULL UNIQUE,
    pipeline_ids JSONB,           -- []UUID or null for all
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- llm_keys (customer keys, encrypted)
CREATE TABLE llm_keys (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    provider TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    models JSONB,                 -- allowed models
    regions JSONB,                -- allowed regions
    created_at TIMESTAMP DEFAULT NOW(),
    rotated_at TIMESTAMP
);

-- workflows
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    name TEXT NOT NULL,
    pipeline_id UUID REFERENCES pipelines(id),
    pipeline_version_id UUID REFERENCES pipeline_versions(id),
    input_template JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

-- effect_logs (for observability)
CREATE TABLE effect_logs (
    id UUID PRIMARY KEY,
    snapshot_id UUID REFERENCES snapshots(id),
    effect_type TEXT,
    status TEXT,
    error_code TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Hinweis Engine‑Snapshot (In‑Memory):** Felder `pipeline_name`, `tenant_id`, `execution_trace`, `output` — bei Persistenz in JSONB zu übernehmen.

### API Design (REST)

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/pipelines/{id}/execute` | POST | Führt Pipeline mit gegebenem Input aus. Body: `{"input": {...}}`. Returns: `decision`, `confidence`, `snapshot_id`, `audit_url`. |
| `/pipelines/{id}/audit/{run_id}` | GET | Liefert Audit‑Report (JSON). Optional `?format=pdf`. |
| `/pipelines/{id}/versions` | POST | Erstellt eine neue Pipeline‑Version aus der aktuellen Konfiguration. |
| `/keys/llm` | POST | Speichert einen neuen LLM‑Key (verschlüsselt). |
| `/keys/arctis/rotate` | POST | Rotiert den Arctis‑Key des Tenants. Gibt neuen Key zurück. |
| `/snapshots/{id}/replay` | POST | Replay eines Snapshots. Liefert identische Entscheidung (Engine: gleiche Logik wie `Engine.run(..., snapshot_replay_id=...)`). |
| `/workflows` | GET | Liste aller Workflows des Tenants. |
| `/workflows` | POST | Erstellt einen Workflow. Body: `{name, pipeline_id, pipeline_version, input_template, metadata}`. |
| `/workflows/{id}/run` | POST | Führt Workflow aus. Body: `{variables}` (füllt Input‑Template). Returns wie `/pipelines/execute`. |
| `/workflows/{id}` | PUT | Aktualisiert Workflow (nur name/metadata, nicht pipeline/version/template). |
| `/workflows/{id}` | DELETE | Löscht Workflow. |

**Engine‑Eintritt (aktuell):** Python `Engine.run(IRPipeline, tenant_context, snapshot_replay_id=None)` — REST ist die geplante/parallele Produkt‑Hülle.

### Error Codes (normiert)

| Code | Bedeutung | Engine‑Zuordnung (typisch) |
|------|-----------|----------------------------|
| `ARCTIS_INPUT_001` | forbidden_field_detected | Modul / Policy |
| `ARCTIS_INPUT_002` | invalid_json | Parser außerhalb Compiler |
| `ARCTIS_INPUT_003` | schema_validation_failed | Modul |
| `ARCTIS_INPUT_004` | prompt_injection_detected | Modul |
| `ARCTIS_INPUT_005` | forbidden_field_in_prompt | Policy / `AITransform` |
| `ARCTIS_INPUT_006` | budget_exceeded | `ComplianceError` (budget) |
| `ARCTIS_INPUT_007` | no_endpoint_in_region | Residency / Deployment |
| `ARCTIS_AI_001` | model_error | AI‑Provider |
| `ARCTIS_AI_002` | invalid_output_schema | `AITransform` |
| `ARCTIS_AI_003` | output_schema_mismatch | Validator‑Modul |
| `ARCTIS_ROUTING_001` | invalid_threshold | Konfiguration |
| `ARCTIS_EFFECT_001` | effect_failed | `SecurityError` / Effect |
| `ARCTIS_EFFECT_002` | rollback_failed | Saga / `RuntimeError` injiziert |
| `ARCTIS_AUDIT_001` | report_generation_failed | Audit‑Pfad |
| `ARCTIS_WORKFLOW_001` | invalid_template | Control‑Plane |
| `ARCTIS_WORKFLOW_002` | pipeline_version_not_found | Control‑Plane |
| `ARCTIS_WORKFLOW_003` | forbidden_field_in_workflow | Control‑Plane |
| `ARCTIS_WORKFLOW_004` | workflow_name_conflict | Control‑Plane |

### Logging Format (JSON)
```json
{
  "timestamp": "2026-03-21T12:34:56Z",
  "tenant_id": "uuid",
  "snapshot_id": "uuid",
  "module": "ai_decision",
  "severity": "info",
  "message": "LLM call succeeded",
  "duration_ms": 123,
  "metadata": {}
}
```

### Tracing (OpenTelemetry)
- Jede Pipeline‑Ausführung erhält eine eindeutige Trace‑ID (Produkt).
- Jedes Modul erzeugt Spans mit `span_id`, `parent_span_id`.
- Spans enthalten: Modulname, Dauer, Input‑/Output‑Größen, Error‑Code.
- **Engine‑Observability:** `ObservabilityTracker.build_trace` liefert DAG + Step‑Liste (`duration_ms` pro Step, deterministisch aus simulierter Laufzeit).

---

## Demo‑Umgebung & Sandbox (v1.3)

Ziel: **risikofreies Ausprobieren** ohne Produktions‑Keys, ohne dauerhafte Nebenwirkungen — aligned mit `dry_run`‑Kontext und Engine‑Tests.

### Architektur (Sandbox‑Tenant)
```text
+------------------+     +----------------------+
| Sandbox UI       |     | Sandbox API          |
| (gleiche Oberfläche)   | /sandbox/* Präfix    |
+--------+---------+     +----------+-----------+
         |                            |
         v                            v
+--------+----------------------------------------+
| Dedizierter Tenant "sandbox-{user}"           |
| - Rate-Limits enger (z.B. 60/min)             |
| - Keine Produktions-Connectors               |
| - TTL auf Snapshots (z.B. 7 Tage)            |
+------------------------------------------------+
         |
         v
+--------+----------------------------------------+
| Engine.run(IRPipeline, TenantContext dry_run)   |
| Fake-LLM oder stub (deterministischer Hash)    |
+------------------------------------------------+
```

### Beispiel‑Pipelines (Sandbox‑Starter)
| Name | Zweck | IR‑Typen |
|------|-------|----------|
| `demo_minimal_ai` | Ein `ai`‑Step + ein `effect` (write) | `ai`, `effect` |
| `demo_with_module` | `module` (mock validator) → `ai` | `module`, `ai` |
| `demo_saga` | `saga` mit Test‑Kompensation | `saga` |

*(Konkrete YAML‑Snippets analog **DSL Examples**; Sandbox importiert Templates.)*

### Beispiel‑Workflows
- **„Quick credit sample“** — füllt `input_template` mit Demo‑Feldern (`amount`, `country`), **keine** echten PII.
- **„Ticket triage sample“** — verknüpft mit **Ticket Prioritization** Use‑Case (siehe Use‑Case‑Bibliothek).

### Fake‑LLM‑Key‑Modus
- UI‑Toggle **„Demo / Fake LLM“**: speichert **keinen** echten Provider‑Key; setzt intern **Sandbox‑Flag** + optional **`dry_run: true`** im `TenantContext`.
- API‑Header `X-Arctis-Sandbox: true` erzwingt denselben Modus für Automation.
- **Deterministische** Antworten (wie Referenz‑`AITransform`: Hash über Input+Prompt) — reproduzierbar für Demos und Schulungen.

### Reset‑Mechanismus
| Aktion | Wirkung |
|--------|---------|
| **„Sandbox zurücksetzen“** | Löscht Workflows/Snapshots **nur** im Sandbox‑Tenant; keine Auswirkung auf Produktions‑Tenants |
| **TTL‑Job** | Entfernt abgelaufene Snapshots automatisch |
| **Session‑Reset** | Optional: neuer anonymisierter Sandbox‑Sub‑Tenant pro Session |

---

## Engine Compatibility & Constraints

### Engine‑Step Mapping
| Spec‑Module | IR/runtime `type` | Notes |
|-------------|---------------------|-------|
| ai_decision | `ai` | `AITransform` |
| ai_output_validator | `module` | `using` → registriertes Validator‑Modul |
| audit_reporter | audit (system) | `AuditBuilder` + `SnapshotStore`, kein User‑`type` |
| budget_limiter | (compliance) | `ComplianceEngine.enforce_budget` |
| confidence_router | — | DAG‑Verzweigung oder `module`; kein `router`‑Typ |
| effect_executor | `effect` | `EffectEngine` |
| forbidden_fields_enforcer | `module` / policy | ergänzt AI‑Grenzen |
| prompt_sanitizer | `module` | |
| residency_enforcer | (compliance) | `ComplianceEngine` + `AITransform` |
| sanitizer | `module` | |
| schema_validator | `module` | |
| workflow_manager | – | Config only, kein Engine‑Step |
| Saga / Kompensation | `saga` | `SagaEngine` |

### Engine Constraints
- AI‑Steps dürfen keine Effects enthalten (eigener `type` `ai` ohne Side‑Effects in einem Step).
- Effects dürfen keine AI‑Calls enthalten (nur `effect`‑Typ).
- Routing darf keine AI‑Calls enthalten (Routing = Graph oder `module` ohne AI).
- Ein **IR‑Knoten** hat genau einen **`type`** aus `{ai, effect, saga, module}`.
- **`module`** muss `config.using` setzen und im `ModuleRegistry` registriert + signiert sein.

---

## UI Specification

### Dashboard
- **Pipelines**: Liste aller Pipelines, Status, Version, letzte Ausführung.
- **Workflows**: Liste aller Workflows (Name, Pipeline, Version, Tags). Aktionen: Run, Edit, Delete.
- **Recent Runs**: Letzte Ausführungen mit Decision, Confidence, Snapshot‑Link.

### Workflow Creation Screen
- Name, Beschreibung, Tags (frei).
- Pipeline auswählen (Dropdown mit Version).
- Input‑Template definieren (JSON‑Editor oder Formular mit Feldern aus Pipeline‑Input‑Schema). Validierung gegen Schema.
- Speichern → Workflow‑ID wird erzeugt.

### Workflow Execution Screen
- Formular basierend auf Workflow‑Template.
- Variablen werden ausgefüllt (nur die als `{{variable}}` markierten Felder).
- Button „Run Workflow“ → Ausführung der referenzierten Pipeline.
- Ergebnisanzeige: Decision, Confidence, Audit‑Link, Snapshot‑ID.

### Workflow Editing Screen
- Nur Name, Beschreibung, Tags änderbar. Pipeline, Version, Template sind immutable (erfordert neuen Workflow).

### Key Management Screen
- Liste der LLM‑Keys (Provider, Models, Regions, erstellt am, rotiert am).
- Button „Add Key“ (Provider, Key, Models, Regions).
- Button „Rotate“ (ersetzt Key, alte Version wird nach 30 Tagen gelöscht).
- Button „Delete“.

### Audit Viewer
- Snapshot‑Liste mit Filtern (Pipeline, Zeitraum).
- Detailansicht: Input, Output, Prompt, Decision, Confidence, Trace (Spans), Effects‑Logs.
- Button „Replay“ → startet neuen Run mit identischen Parametern (`snapshot_replay_id`).
- Download als PDF.

---

## UI Wireframes (ASCII) & Interaktion (v1.3)

Textuelle Wireframes für **Wizard**, **Pipeline‑Editor**, **Workflow‑Manager**, **Workflow‑Execution**, **Audit‑Viewer**, **Key‑Management**, **Billing**. Die in **UI Specification** genannten Listen bleiben gültig; hier **Layout**, **Interaktion** und **Validierung**.

### Wizard (Onboarding — 10 Schritte)
```
+------------------------------------------------------------------+
|  Arctis  >  Neuer Workspace                         [Abbrechen]  |
+------------------------------------------------------------------+
|  Fortschritt: [=====>        ]  Schritt 3 von 10                |
|                                                                  |
|  Wie lautet Ihre Zielbranche?                                   |
|  ( ) Fintech   ( ) Support   ( ) HR   ( ) Sonstiges             |
|                                                                  |
|  [Zurück]                                    [Weiter]            |
+------------------------------------------------------------------+
```
**Interaktion:** „Weiter“ nur bei gültiger Auswahl; **Zurück** behält Draft im LocalStorage; letzter Schritt → **Pipeline‑Vorschau** + **„Deploy v1.0.0“**.  
**Validierung:** Pflichtfelder pro Step; keine Secrets eingeben (Hinweisbanner).

### Pipeline‑Editor (IR / Steps)
```
+------------------------------------------------------------------+
|  Pipeline: credit_decision   v1.2.0 (immutable)    [Version+]   |
+----------+-------------------------------------------+-----------+
| Schritte |  Step: decide (ai)                        | Eigenschaft.|
| [+]      |  +----------------------------------+    | prompt: ... |
| validate |  | input | prompt (Editor)          |    | input: ...  |
| decide   |  +----------------------------------+    | [Schema]    |
| effect   |  next: [ effect v]                   |    |             |
+----------+-------------------------------------------+-----------+
|  [Validieren]   [IR anzeigen]   [Testlauf]                       |
+------------------------------------------------------------------+
```
**Interaktion:** Drag‑Sort optional; **next** als Dropdown nur auf existierende Steps; **Testlauf** öffnet Side‑Panel mit `RunResult`‑Preview.  
**Validierung:** `check_pipeline`‑Regeln (keine Zyklen, alle `next` gültig); Step‑Typ nur `ai|effect|saga|module`; `module` verlangt `using`.

### Workflow‑Manager
```
+------------------------------------------------------------------+
|  Workflows                                    [+ Workflow]       |
+------------------------------------------------------------------+
|  Name          Pipeline        Version   Tags        Aktionen   |
|  small_credit  credit_decision 1.0.0     credit      Run Edit ..|
+------------------------------------------------------------------+
|  Filter: [________]  Sort: Name v                             |
+------------------------------------------------------------------+
```
**Interaktion:** **Run** → navigiert zu **Workflow‑Execution**; **Edit** nur Metadaten/Tags.  
**Validierung:** `input_template` nur Keys aus Pipeline‑Input‑Schema; keine Secrets (Pattern‑Scan).

### Workflow‑Execution
```
+------------------------------------------------------------------+
|  Workflow: small_credit   Pipeline credit_decision @ 1.0.0       |
+------------------------------------------------------------------+
|  amount (EUR)    [__________]   required, >0                   |
|  customer_id     [__________]   pattern: ^C-[0-9]+$              |
|                                                                  |
|  [Ausführen]                                                     |
+------------------------------------------------------------------+
|  Ergebnis:  decision: ...  |  snapshot_id: ...  | [Audit öffnen]|
+------------------------------------------------------------------+
```
**Interaktion:** Submit → POST `/workflows/{id}/run`; Fehler mit `ARCTIS_*` inline.  
**Validierung:** JSON‑Schema client‑seitig + server‑seitig.

### Audit‑Viewer (Detail)
```
+------------------------------------------------------------------+
|  Snapshots > run-2026-03-21T12:00Z                    [Replay]   |
+----------+-------------------------------------------------------+
| Filter   |  Tabs: [ Übersicht | Input/Output | Trace | Effects ] |
| Pipeline |  Trace (DAG):  validate -> decide -> effect          |
| Zeitraum |  Spans: step decide  12ms                           |
+----------+-------------------------------------------------------+
|  [PDF herunterladen]                                             |
+------------------------------------------------------------------+
```
**Interaktion:** **Replay** setzt `snapshot_replay_id`; Bestätigungsdialog bei Produktion.  
**Validierung:** Tenant‑Scope — fremde IDs → 403.

### Key‑Management
```
+------------------------------------------------------------------+
|  LLM-Schlüssel                              [+ Schlüssel]         |
+------------------------------------------------------------------+
|  Provider   Region   Modelle (kurz)    Status    Aktionen       |
|  OpenAI     EU       gpt-4o-mini       aktiv     Rotate Delete  |
+------------------------------------------------------------------+
|  Hinweis: Schlüssel werden nie im Klartext angezeigt.            |
+------------------------------------------------------------------+
```
**Interaktion:** **Add** öffnet Modal (Provider, Key einmalig, Modelle, Regionen); **Rotate** Grace‑Period‑Hinweis.  
**Validierung:** Key‑Format provider‑spezifisch; keine Speicherung ohne Verschlüsselungs‑ACK.

### Billing
```
+------------------------------------------------------------------+
|  Abrechnung > Abo & Nutzung                                     |
+------------------------------------------------------------------+
|  Plan: Pipeline A (Pro)              299 EUR / Monat            |
|  Add-ons: [x] Analytics  [ ] Multi-Model                      |
|                                                                  |
|  Nutzung (laufender Monat):    Runs: 12.400 / 50.000            |
|                                Overages: 0 EUR                   |
|                                                                  |
|  [Rechnungen PDF]   [Zahlungsmittel]   [Plan ändern]            |
+------------------------------------------------------------------+
```
**Interaktion:** **Plan ändern** → Upsell‑Flow mit **Lizenzcheck** (`ARCTIS_LICENSE_001` bei fehlender Lizenz).  
**Validierung:** Zahlungsmittel PCI‑delegiert (Stripe o. Ä.); keine Kartennummern in Arctis‑Logs.

---

## DSL Examples

### Pipeline Definition (Compiler‑Format — JSON / YAML)
Entspricht `parse_pipeline` (**dict** mit `name` und `steps`). Jeder Step: `name`, `type` (`ai` \| `effect` \| `saga` \| `module`), `config`, optional `next`.

```yaml
# credit_decision.pipeline.yaml — Pipeline A → Engine IR
name: credit_decision
steps:
  - name: validate_input
    type: module
    config:
      using: "schema.validate@1.0.0"
    next: decide

  - name: decide
    type: ai
    config:
      input: "{{workflow_input}}"
      prompt: |
        Entscheide über den Kreditantrag. Optionen: approve, reject.
        Eingabe: {{workflow_input}}
    next: route_placeholder

  - name: route_placeholder
    type: module
    config:
      using: "router.confidence@1.0.0"
    next: apply_effect

  - name: apply_effect
    type: effect
    config:
      type: write
      key: "credit:decision:{{id}}"
      value: "{{decision}}"

  # optional: Saga für kompensierbare Schritte
  - name: notify_saga
    type: saga
    config:
      action:
        op: notify
      compensation:
        op: rollback_notify
```

**Hinweis:** `check_pipeline` / `generate_ir` prüfen **nicht**, ob `module`‑Namen im Registry existieren — das erzwingt `Engine.run` über `SecurityError` bei fehlender Registrierung.

### Legacy YAML (Pipeline‑Metadaten + Routing‑Darstellung)
Die frühere Darstellung mit `config.ai`, `routing.approve` als HTTP/Email bleibt als **Produkt‑/Authoring‑Sicht** gültig; der **Compiler** erwartet die **Step‑Liste** wie oben. Transformation von „routing branches“ → IR‑Graph ist Aufgabe des Pipeline‑Compilers oder der Konfigurations‑UI.

```yaml
# credit_decision — semantische Pipeline-A Konfiguration (vor Lowering)
version: "1.0"
name: credit_decision
description: "Entscheidet über Kreditanträge"

config:
  input_schema: "schemas/credit_request.json"
  forbidden_fields: ["ssn", "dob"]
  prompt_template: |
    Entscheide über den Kreditantrag:
    {{input}}
    Entscheidungen: approve, reject
    Begründe kurz.
  ai:
    model: "gpt-4"
    temperature: 0
    seed: 42
    confidence_thresholds:
      approve: 0.7
      reject: 0.3
  routing:
    approve:
      - type: http
        url: "https://crm.example.com/approve"
        method: POST
        body: "{{decision}}"
    reject:
      - type: email
        to: "credit@example.com"
        subject: "Ablehnung"
        body: "{{decision.reason}}"
    manual_review:
      - type: slack
        channel: "#credit-review"
        message: "Manuelle Prüfung nötig: {{input.id}}"
  audit:
    report_format: ["json", "pdf"]
    snapshot: true
  observability:
    logs: true
    traces: true
```

### Workflow DSL (YAML)
```yaml
# workflow_small_credit.yaml
workflow:
  name: "credit_small_amount"
  pipeline: "credit_decision"
  version: "1.0.0"
  input_template:
    amount: "{{variable}}"
    country: "DE"
    customer_id: "{{variable}}"
  metadata:
    description: "Kleinkredite unter 1000€"
    tags: ["credit", "small"]
```

---

## Use‑Case‑Bibliothek (v1.3)

Fünf vollständige **Pipeline‑A**‑Beispiele (Produkt‑/Authoring‑Sicht + Engine‑taugliche Kurz‑IR). **Engine‑Typen** unverändert: `ai`, `effect`, `saga`, `module`.

### 1) Credit Decision
**Beschreibung:** Automatische Vorprüfung von Kreditanträgen mit dokumentierter Entscheidung und persistiertem Effect.

**Input‑Schema (JSON Schema — Ausschnitt):**
```json
{
  "type": "object",
  "required": ["application_id", "amount", "currency", "country"],
  "properties": {
    "application_id": { "type": "string" },
    "amount": { "type": "number", "minimum": 0 },
    "currency": { "type": "string", "enum": ["EUR", "USD"] },
    "country": { "type": "string", "minLength": 2 }
  },
  "additionalProperties": false
}
```

**Prompt (Kern):** „Klassifiziere den Antrag als **approve**, **reject** oder **manual_review**. Gib **confidence** zwischen 0 und 1 und eine **kurze Begründung** ohne personenbezogene Zusatzdaten.“

**Routing (semantisch):** `approve` → Effect CRM‑Write; `reject` → Effect Benachrichtigung; `manual_review` → Effect Queue‑Ticket (alle als **`effect`**/`saga` im IR‑Graph modelliert).

**Effects (Engine‑konform):** z. B. `type: write`, `key: "credit:{application_id}"`, `value: { "decision": "...", "confidence": 0.82 }`.

**Beispiel‑Workflow:** `workflow_credit_small` — `input_template` mit `amount`, `country`, `application_id`; Tags `credit`, `demo`.

---

### 2) Vendor Approval
**Beschreibung:** Freigabe oder Ablehnung von Lieferantenanfragen basierend auf strukturierten Kriterien.

**Input‑Schema (Ausschnitt):**
```json
{
  "type": "object",
  "required": ["vendor_id", "category", "annual_spend"],
  "properties": {
    "vendor_id": { "type": "string" },
    "category": { "type": "string" },
    "annual_spend": { "type": "number" }
  }
}
```

**Prompt:** „Bewerte **compliance_risk** (low/medium/high) und **approval** (approved/rejected/review). Nutze nur die gelieferten Felder.“

**Routing:** `approved` → Effect ERP‑Upsert; `rejected` → Effect Archiv; `review` → manuelle Queue (Effect).

**Effects:** `write` / `upsert` mit idempotenter `key: "vendor:{vendor_id}"`.

**Beispiel‑Workflow:** `workflow_vendor_fast_track` — nur `vendor_id` + `annual_spend` als Variablen.

---

### 3) Ticket Prioritization
**Beschreibung:** Support‑Tickets mit Priorität (P1–P4) und Routing an Teams.

**Input‑Schema (Ausschnitt):**
```json
{
  "type": "object",
  "required": ["ticket_id", "subject", "body"],
  "properties": {
    "ticket_id": { "type": "string" },
    "subject": { "type": "string" },
    "body": { "type": "string", "maxLength": 8000 }
  }
}
```

**Prompt:** „Weise **priority** (P1–P4) und **team** (billing|tech|general) zu. Keine Speicherung von Kundendaten außerhalb der Felder.“

**Routing:** Mapping `team` → unterschiedliche Effect‑Keys (z. B. `write` auf `queue:{team}:{ticket_id}`).

**Effects:** mehrere `write`‑Steps oder ein aggregierter Step (Graph).

**Beispiel‑Workflow:** `workflow_triage_support` — Variablen `ticket_id`, `subject`.

---

### 4) Document Classification
**Beschreibung:** Eingaben (Metadaten + Kurztext) in Kategorien **invoice**, **contract**, **other** klassifizieren.

**Input‑Schema (Ausschnitt):**
```json
{
  "type": "object",
  "required": ["doc_id", "excerpt"],
  "properties": {
    "doc_id": { "type": "string" },
    "excerpt": { "type": "string", "maxLength": 4000 }
  }
}
```

**Prompt:** „Klassifiziere in **label** und **confidence**. Bei Unsicherheit **manual_review**.“

**Routing:** `label` steuert nachfolgende `module`‑Verarbeitung oder `effect` (Archivpfad).

**Effects:** `upsert` auf `doc:{doc_id}` mit Klassifikationsergebnis.

**Beispiel‑Workflow:** `workflow_classify_batch` — Template mit `doc_id`, `excerpt`.

---

### 5) Risk Flagging
**Beschreibung:** Transaktionen mit **risk_score** 0–100 und **flag** (none|review|block).

**Input‑Schema (Ausschnitt):**
```json
{
  "type": "object",
  "required": ["tx_id", "amount", "channel"],
  "properties": {
    "tx_id": { "type": "string" },
    "amount": { "type": "number" },
    "channel": { "type": "string", "enum": ["web", "api", "branch"] }
  }
}
```

**Prompt:** „Berechne **risk_score** und **flag**. Begründung max. 2 Sätze, keine personenbezogenen Daten erfinden.“

**Routing:** `flag=block` → Effect Sperre; `review` → manuelle Prüfung; `none` → nur Audit‑Log.

**Effects:** `write` mit `key: "risk:{tx_id}"`; optional **`saga`** wenn nachfolgende Freigabe kompensiert werden muss.

**Beispiel‑Workflow:** `workflow_risk_high_value` — Variablen `tx_id`, `amount`.

---

## Onboarding Flow (User Journey)
1. **Tenant‑Creation**: Kunde registriert sich → neuer Tenant, Arctis‑Key wird generiert.
2. **LLM‑Key‑Setup**: Kunde fügt eigene LLM‑Keys hinzu (verschlüsselt).
3. **Erste Pipeline generieren**: Wizard führt durch 10 Fragen → erzeugt Pipeline‑Version 1.0.0 (Compiler‑konformes `steps`‑IR).
4. **Test‑Run**: Kunde kann einen ersten Run über die API oder UI starten (`Engine.run` / REST).
5. **Workflow erstellen** (optional): Kunde speichert häufig genutzte Inputs als Workflow.
6. **Upgrade**: Kunde aktiviert Upsells über das Dashboard.

---

## Support, Onboarding & Betrieb (v1.3)

### Ticket‑Flow
```text
[Kunde] -> Portal/Email -> Ticket (P3/P4)
                |
                v
         L1 Triage (SLA je nach Plan)
                |
        +-------+-------+
        v               v
   Wissensbasis      L2 Engineering
   (FAQ/Troubleshoot)   (P1/P2 Escalation)
```

| Stufe | Inhalt | Ziel‑Frist (Standard) |
|-------|--------|------------------------|
| **L1** | Account, Billing, erste Fehleranalyse | 1 Werktag |
| **L2** | Technische Integration, `ARCTIS_*`‑Codes | 2 Werktage |
| **L3** | Plattform‑Bugs, Eskalation an Produkt | nach Schweregrad |

### FAQ‑Struktur (Informationsarchitektur)
1. **Erste Schritte** — Tenant, Keys, erste Pipeline  
2. **Pipelines & IR** — Steps, `next`, häufige Compiler‑Fehler  
3. **Workflows** — Templates, Variablen, `ARCTIS_WORKFLOW_*`  
4. **Sicherheit** — Residency, Secrets, Rotation  
5. **Abrechnung** — Pläne, Upsells, `ARCTIS_LICENSE_001`  
6. **SLA & Status** — Wartungsfenster, Incident‑Kommunikation  

### Troubleshooting‑Guides (Stichworte)
| Symptom | Prüfschritte |
|---------|----------------|
| `403` / Tenant isolation | `tenant_id` in Request und Snapshot übereinstimmend? |
| `budget_exceeded` | `budget_limit` vs. simulierte Kosten; `set_simulated_*` prüfen |
| `non-idempotent effect` | Gleicher `key` mit anderem `value` — Keys policy‑konform? |
| `module not registered` / `unsigned module` | `load_module` / Signatur in **ModuleRegistry** |
| Residency‑Fehler | `data_residency` vs. `ai_region` / `service_region` |

### Monitoring für Arctis‑Admins (intern)
- **Golden Signals:** Latenz p50/p95, Fehlerquote, Queue‑Tiefe pro Region  
- **Tenant‑Health:** Rate‑Limit‑Treffer, wiederholte `ARCTIS_INPUT_006`, Spike bei `ARCTIS_EFFECT_001`  
- **Audit:** Änderungen an Pipeline‑Versionen, Key‑Rotationen, AVV‑relevante Löschjobs  
- **Alerting:** P1/P2 an On‑Call gemäß SLA‑Abschnitt  

---

## Product Plan & Pricing
| Komponente | Preis |
|------------|-------|
| Pipeline A (Default) | 199–499 € / Monat |
| Upsell 1: Analytics Pack | +99–149 € / Monat |
| Upsell 2: Multi‑Model Pack | +149–249 € / Monat |
| Upsell 3: Integrations Pack | +199–299 € / Monat |

**Alle Preise:** monatlich, keine Setup‑Gebühren, keine versteckten Kosten.  
**Upgrades:** Jederzeit möglich, pro‑rata.  
**Lizenz‑Service:** Prüft bei jedem Pipeline‑Run, ob die aktivierten Upsells lizenziert sind. Fehlende Lizenz führt zu Fehler `ARCTIS_LICENSE_001`.

---

## Beta‑Launch‑Plan (30 Tage) (v1.3)

### Phasen (Überblick)
| Woche | Fokus | Deliverables |
|-------|-------|--------------|
| **1** | **Foundations** | Sandbox live, Wizard MVP, 2 Demo‑Pipelines, Statuspage |
| **2** | **Early Access** | 5–10 Design‑Partner, Support‑Kanal, Feedback‑Formular in UI |
| **3** | **Hardening** | SLA‑Monitoring, Runbooks P1/P2, FAQ v1 aus echten Tickets |
| **4** | **Scale‑Readiness** | Onboarding‑Videos, Billing‑Self‑Service, Beta‑Review & Go/No‑Go |

### KPIs (Beta)
| KPI | Ziel (Indikativ) | Messung |
|-----|------------------|---------|
| **Aktivierung** | ≥ 70 % der eingeladenen Tenants mit erstem erfolgreichen Run | Analytics |
| **Zeit bis erster Run** | Median ≤ 30 min nach Key‑Setup | Produkt‑Events |
| **Fehlerquote** | < 2 % Runs mit nicht‑retrybarem `ARCTIS_*` (exkl. Kundenconfig) | Observability |
| **NPS (Beta)** | ≥ 30 (interner Sprint‑Check) | Umfrage Woche 3–4 |

### Feedback‑Schleifen
- **In‑Product:** „War das hilfreich?“ nach erfolgreichem Run; optional Screenshot‑Anhang bei Fehler.  
- **Wöchentlich:** 30‑min‑Call mit 2–3 Design‑Partnern (rotierend).  
- **Changelog:** Jede Woche **Release Notes** (auch bei nur Docs/Spec) — Transparenz baut Vertrauen.  
- **Engine‑Freeze:** Während Beta **keine** Breaking Changes an **IR‑Typen** ohne Major‑Version (siehe Future‑Proofing Policy).

---

## Version History
| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0 | 2026‑03‑21 | Initiale Spezifikation |
| 1.1 | 2026‑03‑21 | Umfassende Erweiterung: Policies, DB‑Schema, API, Workflow Manager, Error Codes, Logging, Tracing, Engine Constraints, Operational/Security/Testing Policies, Changelog‑Regeln, Future‑Proofing, Onboarding‑Flow, UI‑Screens |
| 1.2 | 2026‑03‑21 | Workflow Manager vollständig integriert (DSL, Policy, UI, API, DB, Error‑Codes, Engine‑Mapping). Module alphabetisch sortiert. Policies neu gruppiert. API‑Endpunkte für Workflows erweitert. UI‑Spec mit Workflow‑Details. Changelog aktualisiert. |
| 1.2‑engine | 2026‑03‑21 | **Engine‑Alignment:** Schnittstellenkatalog (`Engine`, Compiler, IR, TenantContext, Subsysteme), vier Laufzeit‑Step‑Typen, Effect‑Whitelist, kein `router`‑IR‑Typ, DAG‑Routing, RunResult/Snapshot/Audit/Observability, DSL‑Beispiel auf `parse_pipeline`‑Dict‑Format, Fehler‑Mapping, Cross‑Ref zu Engine Spec v1.5. |
| **1.3** | **2026‑03‑21** | **Marktreife Ergänzungen (nur additive Kapitel):** Product Positioning & Messaging; **SLA** (Verfügbarkeit, Incidents, RTO/RPO, Fehlerklassen, Self‑Healing, Verantwortungsgrenzen); **DSGVO/TOMs** (Datenfluss, Speicherorte, Verschlüsselung, Zugriff, Löschung, AVV, RACI); **Demo/Sandbox** (Architektur, Fake‑LLM, Reset); **Use‑Case‑Bibliothek** (5 Pipelines: Credit, Vendor, Ticket, Document, Risk); **Support & Ops** (Tickets, FAQ, Troubleshooting, Admin‑Monitoring); **UI‑Wireframes** (ASCII) für Wizard, Pipeline‑Editor, Workflow‑Manager, ‑Execution, Audit, Keys, Billing; **Beta‑Launch‑Plan** (30 Tage, KPIs, Feedback). **Unverändert:** sämtliche Engine‑Schnittstellen, Policies, Modulliste, Engine‑Step‑Mapping. |
| **1.3+launch** | **2026‑03‑21** | **Externe Referenz (nicht‑normativ):** `docs/arctis-indie-launch-v1.md` — Indie‑Launch‑Bauplan (Auth0/Supabase, Monitoring, DR, Legal, Support, E2E/Lasttests, Feature‑Flags, OpenAPI); verknüpft mit Beta‑Wochen 1–4. **Keine** Änderung an Engine‑ oder Pipeline‑Normen. |

---

### Changelog v1.3 — neue Abschnitte (Referenz)
| Nr. | Abschnitt | Kurzbeschreibung |
|-----|-----------|------------------|
| 1 | Product Positioning & Messaging | Zielgruppen, Value Prop, Differenzierung, Pricing‑Begründung |
| 2 | SLA & Service Level | Zero‑Maintenance, Verfügbarkeit, P1–P4, RTO/RPO, Fehlerklassen, Self‑Healing, Grenzen |
| 3 | DSGVO & Datenschutz (TOMs) | Datenfluss, Speicherorte, Verschlüsselung, Zugriff, Löschung, AVV, RACI |
| 4 | Demo‑Umgebung & Sandbox | Architektur, Beispiel‑Pipelines/Workflows, Fake‑LLM, Reset |
| 5 | Use‑Case‑Bibliothek | 5 vollständige Beispiele mit Schema, Prompt, Routing, Effects, Workflow‑Hinweis |
| 6 | Support, Onboarding & Betrieb | Ticket‑Flow, FAQ‑IA, Troubleshooting, Admin‑Monitoring |
| 7 | UI Wireframes (ASCII) | 7 Screens mit Interaktion & Validierung |
| 8 | Beta‑Launch‑Plan | 30‑Tage‑Plan, KPIs, Feedback‑Schleifen |
| — | *(siehe `docs/arctis-indie-launch-v1.md`)* | Operativer Indie‑Launch (Auth, Monitoring, DR, Legal, Tests) — **kein** zusätzliches Spez‑Kapitel |

---

**Nächste Schritte (optional):**  
- Operativer Launch‑Fahrplan (Indie, Prompt Matrix & Control‑Plane, ohne Spec‑Änderung): `docs/arctis-indie-launch-v1.md`.  
- Bei API‑Launch: OpenAPI mit denselben Feldern wie `RunResult` und `TenantContext`.  
- Bei Schema‑Erweiterung: `IRNode`/`PipelineAST` um optionale `version`‑Metadaten erweitern — Spec zuerst, dann Code.  
- **v1.3:** Rechtliche Finalisierung AVV‑Texte, exakte SLA‑Zahlen im Enterprise‑Angebot, SOC2‑Roadmap kommunizieren.
