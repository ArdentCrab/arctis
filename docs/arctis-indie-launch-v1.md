# Arctis — Indie Launch‑Ready Bauplan (Prompt Matrix & Control‑Plane)

**Status:** operativer Fahrplan (nicht normativ für IR/Engine)  
**Normative Basis:** `docs/pipeline-a-v1.3.md` (Pipeline A, APIs, Rollen, SLA‑Rahmen, DSGVO/TOMs)  
**Ziel:** maximal liefern mit **wenig Parallel‑Prozessen** — eine klare Checkliste statt zusätzlicher „Governance‑Schichten“.

Dieses Dokument setzt die **Prompt Matrix** (systematische Ausführung/Evaluierung von Pipelines über Inputs und ggf. Modelle) und die **Control‑Plane** (Konfiguration, Keys, Runs) in einen **umsetzbaren Launch‑Pfad** für einen Solo‑/Indie‑Betrieb. Es **ändert keine Engine‑Schnittstellen**; es konkretisiert nur Betrieb, Auth, Monitoring und Go‑to‑Market.

---

## Leitplanken (wenig Bürokratie)

| Regel | Konkret |
|--------|---------|
| **Eine Wahl pro Schicht** | Pro Thema maximal **zwei** Optionen (A/B); nach Spike **eine** festlegen — keine Endlos‑Evaluation. |
| **Managed first** | Auth, DB‑Backups, Logs, Error‑Tracking: möglichst **vom Anbieter** mitgeliefert (weniger eigener Betrieb). |
| **Spec bleibt Single Source** | Produktverhalten, Fehlercodes (`ARCTIS_*`), `TenantContext`, `RunResult`: weiterhin **nur** in v1.3 nachziehen; dieses Dokument ergänzt **Betrieb & Launch**. |
| **Intern ≠ Kunde** | Golden Signals, Provider‑Health, Plattform‑Budget: **eigenes** Grafana/Sentry‑Projekt — **nicht** im Kunden‑Dashboard (siehe v1.3 „Monitoring für Arctis‑Admins“). |

---

## Phasenüberblick (angebunden an Beta‑Launch v1.3)

Der **30‑Tage‑Beta‑Plan** in v1.3 bleibt der Rhythmus. Die **Launch‑Ready** Arbeitspakete unten sind **über Woche 1–4 verteilt** und müssen nicht als extra „Phase 6“ laufen — sie **verdichten** vor allem **Hardening (Woche 3)** und **Scale‑Readiness (Woche 4)**.

| Woche (v1.3) | Zusätzlicher Fokus (Launch‑Ready) |
|--------------|-----------------------------------|
| **1 — Foundations** | Auth‑Provider festlegen (Auth0 **oder** Supabase Auth); `api_keys`‑Pfad gegen Spec; **OpenAPI‑Skeleton** (Schema aus `RunResult` / `TenantContext` spiegeln). |
| **2 — Early Access** | **API‑Keys** für maschinellen Zugriff produktiv schalten (Scopes gemäß Key Management Policy); Support‑Inbox + **Statuspage** live. |
| **3 — Hardening** | **Sentry** + **Grafana Cloud** (oder vergleichbar); Alarme (Fehlerquote, LLM‑Provider, Budget); **DR‑Smoke‑Test** (einmaliger Restore‑Lauf). |
| **4 — Scale‑Readiness** | Auto‑Scale **mit Deckel** (min/max Instanzen, Queue‑Tiefe); **E2E** (Playwright) für kritische UI‑Pfade; **Lasttests** Control‑Plane API; Onboarding‑Assets (Video, PDF, Beispiel‑Workflows). |

**Phase 5** im Sinne dieses Dokuments = **alles Launch‑Kritische aus der Tabelle unten**, das nicht strikt Woche 1–2 ist — gedanklich **„vor Go‑Live abhaken“**, ohne separates Projekt‑Gate.

---

## 1 — Authentifizierung & Rollen (einfach, sicher)

**Bezug Arctis:** Rollen aus v1.3 (`Tenant Admin`, `Tenant Developer`) → in IdP als **App‑Rollen** oder **JWT‑Claims** mappen; **Arctis API Key** (Tabelle `api_keys`, tenant‑scoped) bleibt **Pflicht** für `Engine.run`/REST gemäß Spec — **keine** eigene User‑DB für Passwörter.

| Option | Passt gut wenn … |
|--------|-------------------|
| **Supabase Auth** | Du willst **Auth + Postgres** in einem Ökosystem; wenig Moving Parts. |
| **Auth0** | Du willst **reines IdP** und hostest DB/Control‑Plane separat (z. B. Render/Fly + RDS). |

**Minimal‑Scope v1:** Login für Dashboard; Rollen **admin** / **developer** (Mapping auf Tenant Admin / Developer); **kein** eigenes User‑Management UI über Profilverwaltung hinaus.

**Nicht in v1:** SSO/SAML (→ v2 Enterprise laut deiner Abgrenzung).

---

## 2 — Monitoring & Alerting (managed)

**Bezug Arctis:** Alarme sollen dieselben Symptome treffen wie in v1.3 SLA / Fehlerklassen (A–D): Plattform‑5xx, Degradation, Budget (`tenant_context.budget_limit` / Plattform‑Quota).

| Komponente | Rolle |
|------------|--------|
| **Sentry** (oder ähnlich) | Exceptions, Release‑Tracking, grobe Fehlerquote pro Service |
| **Grafana Cloud** (kostenloser Einstieg) oder Metrics des Hosters | Latenz, Request‑Rate, **künstlich aggregierte** Fehlerquote |

**Schwellen (Startwerte, anpassbar):**

- Fehlerquote **> 5 % über 5 min** (nur **5xx**/unhandled, nicht erwartete `4xx` aus Kundenconfig) → Page/Slack.
- LLM‑Provider: **Timeout‑Rate** oder **5xx** über Schwellwert → Incident + Statuspage‑Hinweis (Klasse **C** klar kommunizieren).
- **Budget:** Tenant‑ oder Plattform‑Limit erreicht / nahe → Warnung vor Hard‑Stop (`ComplianceError` / `ARCTIS_*` nach Spec).

**Trennung:** Ops‑Dashboards **nicht** im Kunden‑Portal; Kunde sieht nur **Statuspage** + ggf. in‑Product „Störung bekannt“.

---

## 3 — Kostenkontrolle (du als Betreiber)

**Bezug Arctis:** Neben Kunden‑`budget_limit` (Engine) brauchst du **Plattform‑Grenzen**: Render/Fly **max Instances**, **DB‑Connection‑Limits**, **Rate‑Limits** (v1.3: pro Tenant/Pipeline/API‑Key).

**Pragmatisch v1:**

- **Harte Caps** auf Instanzen + Request‑Concurrency; lieber kurz **Queueing** als unkontrollierte Skalierung.
- **Tenant‑weite** max. parallele Runs (Konfiguration in Control‑Plane, nicht im Engine‑Core ändern nötig, solange durchgesetzt wird).
- Prometheus‑basiertes Auto‑Scaling **nur**, wenn du ohnehin K8s betreibst; sonst: **einfache** Autoscale‑Regeln des PaaS + **Alarm** bei Kostensprung.

---

## 4 — Backup & Disaster Recovery (Indie‑tauglich)

**Bezug Arctis:** Persistente **Snapshots/Audit** (v1.3 RTO/RPO) und **Konfiguration** (Pipelines, Versionen) — Recovery‑Ziele aus v1.3 beibehalten.

| Maßnahme | Minimum |
|----------|---------|
| **Managed DB** | Point‑in‑Time Recovery aktivieren; **einmal** dokumentierter Restore‑Test (Staging). |
| **Object Storage** (PDF/Artefakte) | **Cross‑region** Replikation oder regelmäßiger **Snapshot** in zweite Region (Provider‑Feature nutzen). |
| **Runbook** | 1–2 Seiten: „Totalausfall → DNS, DB, Storage, Worker in dieser Reihenfolge“; Ziel **RTO ≤ 4 h** wie in v1.3 für Konfiguration — hier explizit als **Betreiber‑Versprechen** für dich selbst, nicht als neues Kunden‑SLA. |

**Ohne Extra‑Projekt:** jährlicher **Kalender‑Reminder** „Restore testen“ reicht für v1.

---

## 5 — Rechtliche Dokumente (produktnah, nicht nur Template)

**Bezug Arctis:** v1.3 enthält bereits **AVV‑Rahmen** und Rollen — dieses Kapitel verlangt **konkretisieren + Signaturpfad**.

| Dokument | v1‑Anforderung |
|----------|----------------|
| **Datenschutzerklärung & AGB** | Auf **Arctis + Prompt Matrix + Datenfluss** (siehe DSGVO‑Diagramm in v1.3) zugeschnitten; keine generischen SaaS‑Boilerplates ohne Produktbezug. |
| **DPA / AVV** | **Vorausgefüllte** Version + **digitale Zustimmung** im Onboarding, sobald Kunde **personenbezogene** Daten verarbeitet (Alignment mit v1.3 Auftragsverarbeitung). |
| **Haftungsausschluss LLM‑Keys** | Klarstellung: **Kosten** und **Inhalte** der LLM‑Aufrufe liegen bei Kunde/Provider; Arctis stellt nur die **Verarbeitungsplattform** (passt zu Fehlerklassen A–D). |

**Kein** zusätzlicher „Legal‑Workflow“: ein Anwaltstermin + verlinkte Dokumente reichen.

---

## 6 — Support (light)

**Bezug Arctis:** v1.3 Ticket‑Flow & SLA‑Ziele — hier **Werkzeug** festlegen.

- **E‑Mail** `support@…` → **HelpScout**, **Zammad** oder Postfach + Regeln (eine Lösung wählen).
- **SLA v1:** öffentlich **„Best Effort“**; intern: **P1 kritisch ≤ 24 h** erste Reaktion (für Indie realistisch, konsistent mit v1.3 P1‑Zielen wo möglich).
- **Statuspage** (Atlassian, Cachet, Hetzner‑Status …): **geplante Wartung** + Incidents — verlinkt aus AGB/FAQ.

---

## 7 — Onboarding für erste Kunden

**Bezug Arctis:** Onboarding‑Flow & Use‑Case‑Bibliothek (v1.3) — **Assets** ergänzen.

| Asset | Zweck |
|-------|--------|
| **Video 3–5 min** | Tenant → LLM‑Key → erste Pipeline → Test‑Run (`Engine.run`) |
| **Schritt‑Guide** | PDF oder Notion; gleiche Story wie Wizard |
| **Beispiel‑Workflows** | Importierbare JSON/Exports aus der **Use‑Case‑Bibliothek** (Credit, Vendor, …) — reduziert „leere Seite“-Support |

---

## 8 — Testing‑Strategie (über Phasen)

**Bezug Arctis:** v1.3 Operational/Testing‑Policies; Engine‑Tests im Repo bleiben Quelle für **korrektes IR‑Verhalten**.

| Ebene | Werkzeug / Inhalt |
|-------|-------------------|
| **Integration** | Echter LLM‑Pfad **Ollama** (lokal/CI‑optional); HTTP‑Effects gegen **Mock‑Server** — wie im Plan bereits vorgesehen. |
| **E2E** | **Playwright**: Login, Key anlegen, Pipeline speichern, Run auslösen, Audit/Snapshot sichtbar (kritische Pfade nur). |
| **Last** | **Locust** (oder k6) gegen **Control‑Plane API** + später **Matrix‑Runner** (viele parallele Runs mit Rate‑Limit) — Woche 3–4, nicht blockierend für Woche 1. |

**Einsparung:** Kein separates „QA‑Signoff“-Board — **grüne CI** + manuelle **Smoke‑Checkliste** vor Deploy.

---

## 9 — Feature‑Flags (kontrollierte Rollouts)

**Minimal:** Umgebungsvariablen oder **eine JSON‑Datei** in der Control‑Plane („`features.json`“) — z. B. erweiterte Matrix‑Metriken nur für Beta‑`tenant_id`‑Liste.

**Nicht in v1:** Vollständiges Feature‑Flag‑Produkt (LaunchDarkly etc.) — nur wenn Kundenbasis wächst.

---

## 10 — API‑Dokumentation (OpenAPI)

**Bezug Ar1.3:** „Nächste Schritte“ — OpenAPI mit Feldern wie `RunResult` und `TenantContext`.

- **FastAPI** liefert `/docs` out‑of‑the‑box; bei **Django REST** → **drf‑spectacular**.
- **Pflicht:** Schema **1:1** zu den stabilen Feldern der Spec; **Versionierung** `/v1` beibehalten.

Das ermöglicht später **SDK** ohne Spekulations‑Support.

---

## Launch‑Ready Checkliste (eine Seite)

Nutze diese Tabelle als **einziges** Go‑Live‑Gate — alles andere ist „nice to have“.

| # | Thema | Erledigt wenn … |
|---|--------|-----------------|
| 1 | Auth | Dashboard‑Login + Rollen admin/developer; kein Custom‑Password‑Store |
| 2 | API‑Keys | Arctis‑Keys produktiv; Rotation dokumentiert (v1.3 Key Management) |
| 3 | Monitoring | Sentry + Metriken; Alarme Fehlerquote / LLM / Budget aktiv |
| 4 | Ops‑Trennung | Interne Dashboards nicht im Kunden‑UI |
| 5 | Kosten | Max Instanzen + Rate‑Limits + parallele Runs gedeckelt |
| 6 | DR | PITR an; ein Restore getestet; Runbook ≤ 4 h Notiz |
| 7 | Legal | DPA/AVV + AGB + Datenschutz live; LLM‑Haftungsklausel |
| 8 | Support | support@… + Statuspage; interne P1‑Reaktionsziel |
| 9 | Onboarding | Video + Guide + 1–2 Import‑Workflows |
| 10 | Tests | Integration (Ollama/Mock HTTP); Playwright‑Smoke; API‑Load‑Smoke |
| 11 | Flags | Env/JSON für Beta‑Features |
| 12 | OpenAPI | `/docs` oder gehostete Spec, konsistent mit v1.3 |

---

## Bewusst nicht in v1 (Abgrenzung)

| Thema | Hinweis |
|-------|---------|
| **SSO, dedizierte VPC, SOC2** | v2 Enterprise (bereits in v1.3 als Roadmap angesprochen) |
| **Pipeline B (HR)** | nach v1 |
| **Marketplace** | nach v1 (Engine `ModuleRegistry` bleibt vorbereitet) |
| **ML‑basierte Drift‑Erkennung** | nach v1 (Upsell `analytics_pack` später vertiefen) |
| **Feingranulares Org‑Management** | v1: **Tenant‑RBAC** — alle Mitglieder sehen Tenant‑Daten; feinere Rechte später |

---

## Fehlt noch etwas? (Kurzantwort)

Der **technische** Kern (Engine, IR, Tenant‑Isolation, Keys, SLA‑Rahmen) steht in **v1.3**. Für einen **Indie‑Launch** fehlten vor allem **konkret benannte** Werkzeuge und **ein einziges Abnahme‑Gate** — die Checkliste oben schließt das ohne neue „Phasen‑Bürokratie“.

Sinnvolle **zusätzliche** Einzeiler (optional, nicht blockierend):

- **Incident‑Runbook** (1 Seite) mit Link zur Statuspage — erfüllt teils Punkt 6+4.
- **Kosten‑Alarm** am **Hosting‑Provider** (Budget‑Alert), unabhängig von Grafana — doppelte Absicherung für Punkt 3.
- **Security.txt** + verantwortliche E‑Mail — für vertrauliche Meldungen, minimaler Aufwand.

---

## Versionshinweis

Bei Änderungen am **Produkt** (API‑Felder, Policies): **zuerst** `docs/pipeline-a-v1.3.md` anheben, **dann** dieses Launch‑Dokument anpassen. Dieses Dokument ist **kein** Ersatz für die Pipeline‑Spezifikation.
