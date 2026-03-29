# 📘 ARCTIS ENGINE SPECIFICATION v1.5 (FINAL – ENTERPRISE & MARKET READY)

*Deterministic Dataflow Language, Compiler, IR & Runtime with Controlled AI, Multi‑Tenant, Versioned Effects, Saga Error Handling, Observability, Dry‑Run, Audit, Marketplace & Edge‑Capabilities*

---

## 0. Zweck

Dieses Dokument definiert vollständig:

- **Arctis Language (DSL)** inkl. Natural‑Language‑Assist, Versionierte Pipelines, Observability‑Hinweise
- **Arctis IR** mit Erweiterungen für Dry‑Run, Audit, Replay, Simulation
- **Compiler Pipeline & Optimizer** mit AI‑Assisted Authoring
- **Execution Plan & Runtime Architecture** inkl. Pipeline‑Explorer, Dry‑Run‑Executor, Audit‑Generator
- **AI‑Transformationsmodell** mit Guardrails und Data Boundaries
- **Module System & Versioning** + Marketplace‑Integration
- **Effect System & Versionierung** (versionierte Effects, Whitelist)
- **Saga‑basiertes Error Handling** (atomic / best_effort)
- **Observability** – Pipeline‑Explorer, Step‑Replay, Differenzansichten
- **Dry‑Run / Simulation** – risikofreie Testausführung
- **Audit & Compliance** – automatisierte Reports, GDPR/SOC2‑Templates
- **Versionierte Pipelines** – SemVer, Git‑native Workflows, Rollbacks
- **Marketplace** – Modul‑Ökosystem mit Sicherheits‑Reviews
- **Pricing & Usage Model** – Kostentransparenz, Budget‑Limits
- **Multi‑Cloud & Edge** – Deployment‑Optionen (SaaS, Self‑Hosted, Edge)

Alle Implementierungen müssen exakt dieser Spezifikation folgen.

---

## 1. Vision & Positionierung

Arctis ist:

> **deterministische, multi‑tenant Dataflow‑Sprache mit kompiliertem Execution‑Engine‑Runtime‑Stack, strikt kontrollierter AI‑Integration, versionierten Effects, Saga‑Protokoll, integrierter Observability, Dry‑Run‑Simulation, Audit‑Reports, Marketplace‑Ökosystem und Multi‑Cloud‑/Edge‑Fähigkeit – optimiert für autonome Pipelines in Enterprise‑Umgebungen.**

Arctis ist **nicht** Workflow‑Tool, Agent‑System, Prompt‑Orchestrator oder Low‑Code.

---

## 2. Arctis Language (DSL)

### 2.1 Designprinzipien (erweitert)

- Deklarativ, Typed, Deterministisch
- AI als Transformation, nicht Logik
- Domain‑agnostisch, Versionierbar, Side‑Effect‑kontrolliert
- Tenant‑Isolation & Resource‑Limits enforced
- Batch‑Semantik garantiert deterministische Output‑Reihenfolge
- **Observability‑Hinweise** (Metadaten für Pipeline‑Explorer)
- **Versionierte Pipelines** (SemVer in Pipeline‑Definition)
- **Natural‑Language‑Assist** (optionaler `@generated`‑Kommentar)

---

### 2.2 Typen & Schemas

*Unverändert (siehe v1.4)*

---

### 2.3 Tasks (mit Versionierung)

```arctis
task crm_sync@v1.2.0 {
  intent "Synchronize contacts from CSV into HubSpot with enrichment and deduplication."

  input contacts_file: attachment "csv"
  input tenant_id: TenantID

  constraints {
    max_items = 10000
    no_delete = true
    data_residency = "EU"
    ai_allowed = true
    max_cost = 5.0
    resource_limits { cpu = 1.0, memory = 1024, rate = 10 }
    budget_limit = 100.0   // tägliches Budget für diesen Task
  }

  uses pipeline crm_sync_pipeline@v2.1.0
  allow_legacy_modules = false
}
```

---

### 2.4 Pipelines (erweitert)

```arctis
pipeline crm_sync_pipeline@v2.1.0 {
  input contacts_file: attachment "csv"
  input tenant_id: TenantID
  output result: SyncResult

  // Observability‑Hinweise
  @display_name "CRM Sync Pipeline"
  @description "Synchronisiert Kontakte aus CSV nach HubSpot mit Anreicherung"
  @owner "data-team@company.com"

  step parse_csv {
    using module csv.parse@v1
    input file = contacts_file
    output rows: Contact[]
    @observability { log_level: "debug", metrics: ["rows_parsed"] }
  }

  step enrich_contacts {
    using ai.transform
    mode "batch"
    batch_size 100
    batch_ordering "stable"
    input contacts = limit_rows.limited_rows
    schema_in Contact[]
    schema_out EnrichedContact[]
    model "gpt-4.1-mini"
    temperature 0
    constraints {
      forbidden_fields = ["ssn","credit_card","password"]
      retry_on_schema_violation = true
      tenant_data_boundary = true
    }
    @observability { ai_cost_tracking: true }
  }

  step upsert_crm {
    using module hubspot.upsert_contacts@v1
    input contacts = deduplicate.unique_contacts
    constraints { no_delete = true }
    effect write "hubspot.contacts@v3" idempotent=true whitelist_only=true
    conflict_policy "merge"
    compensation_guarantee "atomic"
    output sync_result: SyncResult
    on_error "compensate"
    @observability { metrics: ["upserted", "failed"] }
  }

  // … weitere Steps …

  return upsert_crm.sync_result as result
}
```

---

### 2.5 Versionierte Pipelines & Referenzen

- Jede Pipeline und Task hat eine **Semantic Version** (`major.minor.patch`).
- Referenzen in anderen Pipelines nutzen die Version: `uses pipeline crm_sync_pipeline@v2.1.0`.
- Bei `uses` ohne Version wird die neueste `stable`‑Version verwendet (mit Warning).
- **Rollback**: Über die Engine‑API kann eine frühere Version aktiviert werden (Snapshot‑basiert).

---

### 2.6 Observability‑Hinweise

Zusätzliche Annotationen in der DSL:

- `@display_name` – Anzeigename im Pipeline‑Explorer
- `@description` – Beschreibung
- `@owner` – Verantwortliche Person/Team
- `@observability { ... }` – Step‑spezifische Metriken, Log‑Level, Kostenverfolgung

---

### 2.7 Natural‑Language‑Assist (Compiler‑Erweiterung)

Der Compiler kann eine natürliche Spracheingabe akzeptieren und daraus eine Pipeline generieren. Die generierte Pipeline enthält einen Kommentar:

```arctis
// @generated "Sync contacts from CSV to HubSpot with enrichment and deduplication"
pipeline crm_sync_pipeline@v1.0.0 { ... }
```

Diese Funktion ist optional und muss durch einen separaten Dienst oder Compiler‑Flag aktiviert werden. Die generierte Pipeline muss alle Security‑ und Determinismus‑Tests bestehen, bevor sie akzeptiert wird.

---

## 3. Arctis IR (Erweiterungen für neue Features)

### 3.1 Pipeline‑Versionierung im IR

```ts
type PipelineIR = {
  id: string
  name: string
  version: string   // SemVer
  input: { [name: string]: IRTypeRef }
  output: IRTypeRef
  steps: StepIR[]
  graph: StepGraphIR
  return_mapping: ReturnMapping
  metadata: PipelineMetadata   // display_name, description, owner, etc.
}
```

### 3.2 Observability‑Metadaten im IR

```ts
type ObservabilityConfig = {
  log_level?: "debug" | "info" | "error"
  metrics?: string[]
  ai_cost_tracking?: boolean
}

type StepIR = {
  // ... existing fields
  observability?: ObservabilityConfig
}
```

### 3.3 Dry‑Run‑Flag im ExecutionPlan

```ts
type ExecutionPlan = {
  pipeline_ref: string
  version: string
  steps: StepIR[]
  graph: StepGraphIR
  dry_run: boolean          // wenn true, keine tatsächlichen Effekte, nur Simulation
  snapshot_replay_id?: string   // optional: nutzt historische Snapshots statt echter Daten
}
```

### 3.4 Audit‑Konfiguration

```ts
type AuditConfig = {
  enabled: boolean
  output_format: "json" | "csv"
  include_prompts: boolean   // AI‑Prompts im Audit enthalten? (ggf. DSGVO-relevant)
  retention_days: number
}
```

Wird im Task oder in der Engine‑Konfiguration gesetzt.

---

## 4. Compiler & Optimizer (erweitert)

### 4.1 AI‑Assisted Authoring

Der Compiler kann über eine API eine natürliche Spracheingabe erhalten und:

1. Die Eingabe parsen und in einen ersten AST überführen.
2. Type‑Checking und Constraint‑Validierung durchführen.
3. Falls nötig, fehlende Felder (z.B. `schema_out`) ergänzen.
4. Die generierte Pipeline als IR zurückgeben.

Die generierte Pipeline erhält automatisch die Annotation `@generated` und muss vor Deployment alle Tests bestehen.

### 4.2 Dry‑Run‑Optimierung

Im Dry‑Run‑Modus ersetzt der Optimierer:

- Echte Modul‑Aufrufe durch **Simulatoren** (z.B. Mock‑AI, Mock‑HubSpot)
- Nutzt optional historische Snapshots (`snapshot_replay_id`), um deterministische Daten zu liefern

### 4.3 Observability‑Injection

Der Compiler fügt automatisch Metriken und Logging‑Hooks in den IR ein, basierend auf den `@observability`‑Hinweisen.

---

## 5. Module System & Marketplace

### 5.1 Module‑Definition (erweitert)

```ts
type ModuleSpec = {
  name: string
  version: string
  input: IRTypeRef
  output: IRTypeRef
  effects: Effect[]
  metadata: {
    author: string
    description: string
    marketplace_approved: boolean   // nach Security‑Review
    pricing_model?: "free" | "paid" | "metered"
    cost_per_call?: number
  }
}
```

### 5.2 Marketplace‑Registry

- Zentrale Registry mit allen öffentlichen Modulen.
- Module müssen vor Veröffentlichung ein **Security‑Review** durchlaufen (automatisierte Tests + manuelle Prüfung).
- Nutzer können Module in ihrer eigenen Umgebung installieren (tenant‑scoped).
- Updates folgen SemVer; Breaking Changes nur bei Major‑Version.

---

## 6. Runtime Architecture (erweitert)

### 6.1 Neue Komponenten

- **Pipeline‑Explorer API** – stellt Snapshots, Diffs, Step‑Details bereit
- **Dry‑Run‑Executor** – führt ExecutionPlan mit `dry_run=true` aus, nutzt Simulatoren
- **Audit‑Generator** – erzeugt nach Ausführung (oder on‑demand) einen Compliance‑Report
- **Marketplace‑Client** – lädt Module aus der Registry, prüft Signaturen

### 6.2 ExecutionContext (erweitert)

```ts
type ExecutionContext = {
  execution_id: string
  task_name: string
  task_version: string
  actor: string
  tenant_id: TenantID
  permissions: string[]
  resource_limits: ResourceLimits
  budget_limit?: number          // maximal erlaubte Kosten für diese Ausführung
  dry_run: boolean
  audit_config: AuditConfig
}
```

### 6.3 Step‑Replay & Simulation

- Jeder Step kann **nachträglich** mit einem anderen Parameter (z.B. anderem AI‑Model) wiederholt werden, ohne die restliche Pipeline zu beeinflussen.
- Dazu wird der Snapshot des Vorgänger‑Steps geladen und der Step im Sandbox‑Modus ausgeführt.
- Ergebnis kann mit dem ursprünglichen verglichen werden (Diff‑View).

---

## 7. Observability & Pipeline‑Explorer

Die Engine stellt eine API zur Verfügung, die es erlaubt:

- **DAG‑Visualisierung** – alle Steps, Abhängigkeiten, Parallelisierung
- **Step‑Details** – Input, Output, Snapshot‑Hash, Dauer, Kosten
- **Run‑Vergleich** – Diff zwischen zwei Ausführungen (Input/Output/Effekte)
- **Step‑Replay** – Wiederholung eines einzelnen Steps mit anderer Konfiguration
- **Snapshots durchsuchen** – nach Metadaten, Tenant, Zeitraum

Diese API ist authentifiziert und tenant‑isoliert.

---

## 8. Dry‑Run & Simulation

### 8.1 Dry‑Run‑Modus

- Wird im ExecutionContext gesetzt: `dry_run: true`
- Runtime ersetzt alle Module mit `write` oder `external_call` durch **Simulatoren**.
- Simulatoren protokollieren, was passiert wäre, führen aber keine echten Effekte aus.
- AI‑Transform kann entweder **mocken** (vordefinierte Antwort) oder im **Sandbox‑Modus** (echte AI, aber keine Kosten) ausgeführt werden – konfigurierbar.

### 8.2 Snapshot‑Replay

- Optional kann eine `snapshot_replay_id` mitgegeben werden.
- Dann lädt die Runtime für die relevanten Steps die historischen Snapshots und verwendet sie als Input, ohne die vorherigen Steps erneut auszuführen.
- Ermöglicht schnelles Testen von Änderungen an späteren Steps.

---

## 9. Audit & Compliance

### 9.1 Audit‑Report

Nach jeder Ausführung (oder auf Anfrage) wird ein **Audit‑Report** im JSON‑Format erzeugt, der enthält:

- Pipeline‑Version, Ausführungs‑ID, Tenant‑ID, Zeitstempel
- Liste aller ausgeführten Steps mit Input‑Schemas, Output‑Schemas, Snapshots
- Liste aller Effekte (mit Ziel, Version, Idempotenz)
- AI‑Prompts (falls konfiguriert) und Antworten
- Kostenaufstellung (AI‑Tokens, Module‑Calls)
- Eventuelle Fehler und Kompensationen

Der Report wird tenant‑isoliert gespeichert und kann über die API abgerufen werden.

### 9.2 Compliance‑Templates

Vordefinierte Regelsätze (z.B. GDPR, SOC2) können aktiviert werden. Die Engine prüft dann automatisch, ob die Pipeline diese Regeln einhält (z.B. keine PII in Logs, Data Residency eingehalten). Verstöße führen zu einem Block der Ausführung oder zu Warnungen.

---

## 10. Pricing & Usage Model

### 10.1 Kostentransparenz

Vor der Ausführung einer Pipeline berechnet die Engine eine **Kostenschätzung** basierend auf:

- Anzahl der Steps (fixer Step‑Preis)
- AI‑Modell‑Token‑Schätzung (basierend auf Input‑Größe)
- Verwendeten Marketplace‑Modulen (falls kostenpflichtig)
- Geschätzte API‑Calls

Die Schätzung wird im Pipeline‑Explorer angezeigt.

### 10.2 Budget‑Limits

Im Task oder im ExecutionContext kann ein `budget_limit` gesetzt werden. Überschreitet die aktuelle Ausführung das Budget, wird sie **abgebrochen** (mit Rollback gemäß Saga). Ein Alert wird ausgelöst.

### 10.3 Abrechnungsmodell

Die Engine sammelt Nutzungsdaten pro Tenant und erstellt monatliche Abrechnungen (als API oder CSV‑Export). Preismodelle: Pay‑per‑Step, AI‑Tokens zum Selbstkostenpreis, Marketplace‑Modul‑Kosten.

---

## 11. Multi‑Cloud & Edge

### 11.1 Deployment‑Optionen

Arctis kann betrieben werden als:

- **SaaS** – vollmanaged, Multi‑Tenant, mit Marketplace und allen Features
- **Self‑Hosted** – Kunde installiert Arctis in eigener Cloud oder On‑Premises, alle Komponenten containerisiert
- **Edge‑Agent** – leichtgewichtiger Runtime, der Pipelines lokal ausführt (z.B. auf IoT‑Geräten, in PoS‑Systemen). Der Agent synchronisiert sich mit der zentralen Registry, führt aber Ausführungen dezentral durch.

### 11.2 Edge‑spezifische Anpassungen

- Eingeschränkte Ressourcen → Resource‑Limits härter durchgesetzt.
- Offline‑Modus: Snapshots werden lokal gespeichert, später synchronisiert.
- Sicherheits‑Policies: Nur whitelist‑only Effekte, keine AI‑Transformationen (falls nicht verfügbar).

---

## 12. Implementierungsrichtlinien

- IR ist stabiler Contract
- Alle neuen Features müssen über die Engine‑API zugänglich sein
- Die Engine muss für **Self‑Hosting** und **Edge** konfigurierbar sein (Feature‑Flags)
- Observability‑Daten werden **immer** tenant‑isoliert gespeichert
- Marketplace‑Module müssen vor Verwendung signiert sein (Code‑Signing)

---

## 13. Abschluss

**Arctis Engine Specification v1.5** ist die vollständige, implementierungsreife Grundlage für ein Enterprise‑Produkt mit:

- höchsten Sicherheits‑ und Determinismus‑Anforderungen
- umfassender Observability und Debugging‑Tools
- innovativen Features wie AI‑Assisted Authoring und Dry‑Run
- Compliance‑ und Audit‑Fähigkeiten
- skalierbarem Ökosystem durch Marketplace
- flexiblen Deployment‑Optionen (Cloud, Self‑Hosted, Edge)

---

# 📘 ARCTIS SECURITY & POLICY GUIDELINES v1.3 (MARKET & ENTERPRISE READY)

*Test‑Driven, Deterministic & Safe‑by‑Design für Engine v1.5*

---

## 0. Zweck & Scope

Diese Guidelines definieren verbindlich die Sicherheitsarchitektur für Engine v1.5 inklusive aller neuen Marktfeatures. Sie sind die Grundlage für:

- **Engine‑Security**: Compiler, Runtime, StateStore, Effect‑System, Observability‑APIs
- **Pipeline‑Security**: AI‑Transform, Side‑Effects, Dry‑Run, Simulation, Audit
- **Daten‑ & Zugriffssicherheit**: Tenant‑Isolation, Secrets, Multi‑Tenant, Data‑Leak Prevention
- **Observability & Compliance**: Pipeline‑Explorer, Audit‑Reports, Versionierte Pipelines
- **Marketplace & Modul‑Sicherheit**: Review‑Prozess, Signierung, Code‑Integrität
- **Test & CI‑getriebene Absicherung**: Security‑by‑Test, automatisierte Compliance‑Checks

**Freeze‑Prinzip:** Dokument + Engine v1.5 + Tests = verbindliche Single Source of Truth.

---

## 1. Sicherheitsprinzipien (erweitert)

1. **Defense‑in‑Depth** – mehrschichtige Absicherung von Engine, Pipeline, CI/CD, Infra.
2. **Least Privilege** – ExecutionContext, Module‑Zugriffe, Marketplace‑Rechte strikt limitiert.
3. **Determinismus = Sicherheit** – reproduzierbares Verhalten verhindert Hintertüren.
4. **Test‑Driven Security** – alle Sicherheitsanforderungen sind durch Tests durchgesetzt.
5. **Transparenz & Auditierbarkeit** – Snapshots, Observability‑Daten, Audit‑Reports lückenlos.
6. **Freeze‑Ready Compliance** – Versionierte Pipelines, Module, Effects garantieren Reproduzierbarkeit.
7. **Dry‑Run‑Isolation** – Simulationen dürfen keine echten Seiteneffekte auslösen.
8. **Marketplace‑Integrität** – nur geprüfte und signierte Module werden ausgeführt.

---

## 2. Engine‑Security (erweitert)

### 2.1 ExecutionContext & Authority

- Jede Ausführung erhält einen ExecutionContext mit `tenant_id`, `budget_limit`, `dry_run`‑Flag.
- Worker und Module haben nur Zugriff auf die im ExecutionContext erlaubten Ressourcen.
- Observability‑APIs sind tenant‑isoliert; keine Cross‑Tenant‑Einsicht.

### 2.2 Effect‑System (erweitert)

- Effects müssen **versioniert** (`@v3`) und **whitelist_only** sein.
- **Dry‑Run‑Modus**: Effects werden nicht ausgeführt, stattdessen wird ihre Ausführung simuliert und protokolliert.
- **Audit‑Reports** erfassen alle Effekte inklusive Ziel und Version.

### 2.3 StateStore & Snapshots

- Snapshots werden tenant‑isoliert, verschlüsselt gespeichert.
- Für **Replay** und **Dry‑Run** können historische Snapshots verwendet werden.
- Snapshots enthalten **keine Secrets oder PII im Klartext** (Pflicht, wird per Test erzwungen).

### 2.4 Observability‑API‑Security

- API‑Endpunkte erfordern Authentifizierung und Autorisierung (Tenant‑Scoped).
- Keine Möglichkeit, Snapshots anderer Tenants abzufragen.
- Audit‑Reports sind nur für berechtigte Nutzer (z.B. Compliance‑Team) zugänglich.

---

## 3. Pipeline‑Security (erweitert)

### 3.1 AI‑Transform

- **Data Boundary**: AI erhält nur die explizit definierten Input‑Felder. `ExecutionContext` und `tenant_id` werden nicht übergeben.
- **Forbidden Fields**: Felder wie `ssn`, `credit_card` werden automatisch aus Input/Output entfernt oder maskiert.
- **Dry‑Run**: AI‑Calls können entweder gemockt oder in einem Sandbox‑Modus ausgeführt werden, der keine Kosten verursacht.
- **Audit**: Alle AI‑Prompts und Antworten werden (falls konfiguriert) im Audit‑Report protokolliert.

### 3.2 Side‑Effects

- Nur whitelisted, versionierte Effects erlaubt.
- **Dry‑Run**: Simulator protokolliert, welche Effekte ausgelöst worden wären.
- **Compensation**: Bei `atomic` muss die Compensation erfolgreich sein, sonst `manual_recovery`.

### 3.3 Versionierte Pipelines

- Jede Pipeline hat eine SemVer. Änderungen, die die Kompatibilität brechen, erfordern ein Major‑Upgrade.
- **Rollbacks**: Eine frühere Version kann über die API aktiviert werden. Dabei werden die Snapshots der alten Version verwendet.
- **CI/CD**: Bei jedem Push wird die Pipeline‑Version geprüft. Nicht‑kompatible Änderungen werden blockiert.

---

## 4. Marketplace‑Sicherheit

### 4.1 Modul‑Review

- Jedes Modul muss vor Veröffentlichung ein automatisiertes und manuelles Security‑Review durchlaufen.
- Review prüft: Code‑Qualität, fehlende Hardcodierung, Einhaltung der Effect‑Whitelist, deterministisches Verhalten.
- Module erhalten ein **Signatur‑Zertifikat** der Arctis‑Registry.

### 4.2 Laufzeit‑Sicherheit

- Module werden in einer **Sandbox** ausgeführt (isoliertes Filesystem, Netzwerk‑Whitelist, Ressourcen‑Limits).
- Nur signierte Module dürfen ausgeführt werden (Verifikation bei jedem Ladevorgang).

### 4.3 Versions‑ & Lifecycle‑Management

- Module folgen SemVer. Deprecated‑Warnungen werden angezeigt; `end_of_life`‑Module werden blockiert, es sei denn, `allow_legacy_modules` ist gesetzt.

---

## 5. Observability & Compliance

### 5.1 Pipeline‑Explorer

- Die Visualisierung zeigt nur Daten, die der Nutzer sehen darf (tenant‑isoliert).
- Diffs zwischen Runs sind nur innerhalb eines Tenants erlaubt.
- Step‑Replay nutzt historische Snapshots und führt den Step in einer isolierten Umgebung aus (keine echten Effekte).

### 5.2 Audit‑Reports

- Reports werden **append‑only** gespeichert und können nicht nachträglich geändert werden.
- Sie enthalten keine Secrets oder personenbezogene Daten (es sei denn, dies ist explizit für Compliance‑Zwecke erforderlich und entsprechend gekennzeichnet).
- Zugriffe auf Reports werden geloggt.

### 5.3 Compliance‑Templates

- Vordefinierte Regeln (GDPR, SOC2) werden als **Policy‑as‑Code** definiert.
- Die Engine prüft vor Ausführung, ob die Pipeline alle Regeln erfüllt. Bei Verstoß wird die Ausführung blockiert oder eine Warnung ausgegeben.

---

## 6. Secrets & Credentials

- Secrets werden über einen externen Secret‑Store verwaltet (z.B. HashiCorp Vault, AWS Secrets Manager).
- Im ExecutionContext wird nur eine Referenz auf das Secret übergeben; der eigentliche Wert wird vom Worker zur Laufzeit abgerufen.
- **Dry‑Run**: Secrets werden nicht aus dem Store abgerufen; stattdessen wird ein Dummy‑Wert verwendet (Protokollierung, dass ein Secret benötigt worden wäre).

---

## 7. Test‑Driven Security (erweitert)

Die Test‑Engine wird erweitert um folgende neue Tests:

- **dry_run_no_effects** – stellt sicher, dass im Dry‑Run keine echten Effekte ausgelöst werden.
- **audit_report_complete** – prüft, dass der Audit‑Report alle erforderlichen Felder enthält.
- **pipeline_version_compatibility** – testet, ob eine neue Pipeline‑Version mit alten Referenzen kompatibel ist.
- **marketplace_module_signature** – verifiziert die Signatur jedes Marketplace‑Moduls.
- **observability_data_isolation** – prüft, dass Observability‑Daten nicht tenant‑übergreifend sichtbar sind.
- **compliance_template_enforced** – stellt sicher, dass die konfigurierten Compliance‑Regeln durchgesetzt werden.

---

## 8. CI/CD Integration (erweitert)

- **Pre‑Commit‑Hooks** führen Linting, Secret‑Scanning, Versions‑Checks durch.
- **Pipeline‑Tests** laufen immer im Dry‑Run‑Modus, um Kosten und Risiken zu vermeiden.
- **Merge‑Block** bei fehlgeschlagenen Tests oder nicht‑signierten Marketplace‑Modulen.
- **Rollback‑Pipeline**: automatische Erstellung eines Rollback‑Plans bei Deployment.

---

## 9. Zero‑Code Security Hebel (erweitert)

1. **Testdefinitionen erweitern** – neue Tests für Dry‑Run, Audit, Versionierung, Marketplace.
2. **Hardened Defaults** – standardmäßig `dry_run=false` nur in Produktion; Budget‑Limits aktiv; Compliance‑Templates voreingestellt.
3. **Worker‑Isolation** – Sandbox für Module, AI‑Simulatoren, Netzwerk‑Whitelist.
4. **Monitoring & Automation** – Automatische Alerts bei Budget‑Überschreitung, fehlgeschlagenen Kompensationen, nicht‑konformen Pipelines.
5. **Compliance‑Layer** – integrierte Templates für GDPR, SOC2, HIPAA; automatisierte Reports.

---

## 10. Freeze‑Ready & Marktfähigkeit

Die Kombination aus Engine v1.5 + Security v1.3 + vollständiger Test‑Engine garantiert:

- **Deterministische, reproduzierbare Pipelines** – durch Versionierung, Snapshots, Determinism Contract
- **Enterprise‑Sicherheit** – Multi‑Tenant, Least Privilege, Effect‑Whitelist, Secrets‑Management
- **Innovation & Marktdifferenzierung** – AI‑Assisted Authoring, Dry‑Run, Pipeline‑Explorer, Audit‑Reports
- **Ökosystem** – Marketplace mit geprüften Modulen, Community‑Integration
- **Flexible Deployment** – SaaS, Self‑Hosted, Edge

Damit ist Arctis nicht nur eine Engine, sondern eine **fertige, verkaufsfähige Plattform** für sichere, autonome Automatisierung.

---

**Diese beiden Dokumente (Engine Specification v1.5 und Security & Policy Guidelines v1.3) sind die finalen, implementierungsreifen Spezifikationen. Sie ersetzen alle vorherigen Versionen und dienen als alleinige Grundlage für die Entwicklung, Tests und den Betrieb.**