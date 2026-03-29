# Arctis Ghost — nach P14: G0 (Finalisierung) & A0 (Zero-Interface)

**Zweck:** Klare Trennung zwischen **abgeschlossener Ghost-Implementierung** (P1–P14 / E1–E6) und allem, was **danach** bis **Launch** bzw. **A0** kommt.  
**Kanonische Vorläufer:** [arctis_ghost_prompt_series.md](arctis_ghost_prompt_series.md), [ghost_implementation_prompts.md](ghost_implementation_prompts.md), [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) §14–§16.

---

## 1. Abschluss der P- und E-Serie (Ist-Stand)

| Ebene | Umfang | Status |
|--------|--------|--------|
| **P1–P8** | Doctor, Writer, State, init-demo, Rezepte, Demo-Polish, OpenAPI/DX, PLG/Branding | Im Repo umgesetzt (siehe Tests unter `tests/ghost/` und Doku `docs/ghost_*.md`) |
| **P9–P14** | §15 Epics **H–K** + Extensions: Explain, Sandbox, Heartbeat, Profile/Auto-Recipe/Verify, `meta`, Lifecycle-Hooks | **Erledigt**; `ghost_implementation_prompts.md` auf **P1–P14 erledigt** |
| **E1–E6** | Entspricht P9–P14 in der 24er-Serie (Block E) | **Vollständig** |

**Es gibt keine weiteren Ghost-Prompts P15+.** Neue Feature-Arbeit heißt nicht mehr „nächster P-Prompt“, sondern **G0** (Querschnitt) oder **A0** (Produktlinie Zero-Interface).

**Leitprinzip (unverändert):** Ghost bleibt **HTTP-only** ohne `import arctis.engine`; Governance bleibt **API-seitig**. G0 und A0 dürfen das nicht unterlaufen.

---

## 2. G0 — Querschnitt bis Publish (kein Feature-Epic)

G0 macht aus „implementiert“ **release- und betriebsfähig**. Keine neuen User-Stories — nur Qualität, Nachweis und Packaging.

**Kopierfertige Agent-Prompts (G1–G6):** [ghost_g0_implementation_prompts.md](ghost_g0_implementation_prompts.md).

### G0.1 Release-Disziplin

| Aufgabe | Arctis-spezifisch |
|---------|-------------------|
| Versionierung | `pyproject.toml` → `[project] version`; Schema `MAJOR.MINOR.PATCH` (+ optional `-dev` / CalVer nach Team-Regel) |
| CHANGELOG | Root `CHANGELOG.md` oder `docs/CHANGELOG.md`; Einträge pro Release mit API- vs. Ghost-CLI-Hinweis |
| Git-Tagging | Tag = gleiche Version wie Paket; Release-Notes verlinken Demo-60 / Matrix wenn sichtbar |
| Release-Notes | Kurz: Breaking Changes (API, `ghost.yaml`-Schema), neue CLI-Flags, Sicherheitshinweise |

### G0.2 CI-Härtung

| Aufgabe | Arctis-spezifisch |
|---------|-------------------|
| Tests | `pytest` mindestens `tests/ghost/` + vorhandene API/Engine-Suites; Ziel: **grün auf main** |
| Ruff | `pyproject.toml` → `[tool.ruff]`; `src` umfasst `arctis`, `arctis_ghost`, `tests` |
| Lockfile | Repo nutzt u. a. `requirements-lock.txt` + Skripte unter `scripts/generate_requirements_lock.*` — CI: reproduzierbare Installs oder dokumentierter Pip-Tools-Workflow |
| Supply chain | Optional: `pip-audit` / Dependabot; bei FastAPI/uvicorn/DB-Treibern besonders sinnvoll |
| Typcheck | Optional: `mypy` oder `pyright` auf `arctis_ghost` zuerst (kleine Oberfläche) |

### G0.3 Installations- & Onboarding-Story

| Aufgabe | Arctis-spezifisch |
|---------|-------------------|
| README (Root) | Install (`pip install -e ".[dev]"` o. Ä.), Start API (falls Teil desselben Pakets), **`ghost`**-Einstieg |
| `ghost.yaml` | Verweis auf [ghost_cli_reference.md](ghost_cli_reference.md), Profil/Env-Liste |
| Quickstart | 3–5 Schritte: `ghost init-demo` → `ghost doctor` → `ghost run` / Rezept → optional `pull-artifacts` + `verify` |
| Demo-Story | [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) als kanonisches 60s-Storyboard |

### G0.4 Staging-E2E (einmal „echt“)

| Schritt | Zweck |
|---------|--------|
| `ghost doctor` | Erreichbarkeit `/health`, optional authentifizierter Smoke-Call |
| `ghost run` | Echter Execute gegen Staging-`api_base_url` |
| `ghost fetch` / `watch` | Run-Lebenszyklus sichtbar |
| `ghost pull-artifacts` | Writer-Pfad `outgoing/<run_id>/` wie in Produktion |
| `ghost verify` | Lokaler Abgleich Envelope ↔ `GET /runs/{id}` |
| Hooks (optional) | Nur mit Testskript; kein Produktionsgeheimnis in Logs |

**Akzeptanz:** Ein dokumentierter Durchlauf (Screenshot/Log-Redaction) reicht für internes Go-Live; für Kunden-Launch ggf. wiederholbar als Skript.

### G0.5 Sicherheit & Betrieb (Doku-Bündel)

Bereits teils in [ghost_cli_reference.md](ghost_cli_reference.md), [ghost_hooks_p14.md](ghost_hooks_p14.md), [security_production.md](security_production.md). G0 prüft **Vollständigkeit**:

- API-Keys: nur Env / Secrets-Store, nicht in YAML committen  
- Hooks: Vollzugriff Nutzerkontext; Timeout; keine Policy-Duplikation  
- Pfad-Sandbox: `resolve_under_cwd`, keine absoluten User-Pfade für Inputs  
- Limits: JSON-/Dateigrößen (P10)  
- State: `.ghost/state` — sensitiv behandeln  

### G0.6 PyPI- / Paket-Entscheid (strategisch)

| Option | Konsequenz |
|--------|------------|
| **Monorepo-Paket `arctis`** (aktuell) | Ein Wheel mit API + Engine + `ghost`-Entry-Point; klare README-Sektion „nur Ghost nutzen“ vs. „Full Stack“ |
| **Split-Paket `arctis-ghost`** (später) | Extra-Pflege, saubere Abhängigkeiten `requests`/`pyyaml` ohne FastAPI — nur wenn Markt das verlangt |
| **Nicht öffentlich** | Nur privates Registry / Source-Install; trotzdem G0.1–G0.5 sinnvoll |

**Empfehlung:** Zuerst **ein** Release aus dem bestehenden `pyproject.toml` definieren; Split ist **nach** G0 messen, nicht vorher blockieren.

---

## 3. A0 — „Ghost Ultra Edition“ / Zero-Interface (Launch-Produktlinie)

A0 ist **kein** Teil der P-Serie. Es ist die **nächste Produktgeneration** auf dem Ghost-Fundament: weniger oder keine sichtbare CLI für den Endnutzer — **Ordner, Dateien, Ereignisse** als Oberfläche.

**Launch-Regel (Team-Entscheid):**  
Entweder **Launch nach G0** (CLI-first Produkt) **oder** **Launch erst mit A0** (Zero-Interface als USP). Dieses Dokument setzt die zweite Linie als **explizites Ziel** voraus — anpassen, wenn ihr CLI-first launchen wollt.

### Abgrenzung zu §15 / P9–P14

| Bereich | P-Serie (erledigt) | A0 (neu) |
|---------|-------------------|----------|
| Auslöser | Expliziter `ghost`-Aufruf | Dateisystem, Hot-Folder, Clipboard, Symlinks |
| Feedback | Terminal + Artefakte | Sidecar-Status, Live-Feedback, „Stamps“ |
| Governance | unverändert API-only | A0 **darf** keine zweite Policy-Engine sein — nur Orchestrierung um bestehende CLI/API |

### A0-Epics (Arbeitsnamen, Reihenfolge empfohlen)

| ID | Name | Kurzinhalt | Baut auf |
|----|------|------------|----------|
| **A1** | Hot-Folder | Eingehende Dateien → (debounced) Run → optional Auto-`pull-artifacts` + `verify` | `ghost run`, `watch`, Writer, Verify |
| **A2** | Sidecar-Feedback | Kleiner Begleitprozess / Datei-Spiegel: Status, Fehler, Evidence-Kurzinfo ohne volle CLI | Heartbeat-/Status-Muster, `outgoing/` |
| **A3** | Visual Audit Stamps | Ordner-/Datei-Markierungen (z. B. Namenskonvention, `.arctis-stamp`-Metadaten) — **lokal dokumentarisch** | Branding/Envelope-Denke (P8), kein kryptographischer Ersatz |
| **A4** | Symlink-Governance | Konvention: Symlinks = gewähltes Rezept/Profil/Policy-**Label** (Leserichtung nur; Server bleibt Wahrheit) | Profiles, Rezepte |
| **A5** | Clipboard-Triggers | Inhalt → temporärer Input → Run (OS-abhängig, opt-in) | P10 Sandbox/Limits **zwingend** |
| **A6** | Zero-Interface-Flows | Zusammenspiel: kein Pflicht-Terminal; Start/Stopp über Ordner/Flags wie §15.11 Remote-Datei-Idee | A1–A5, `ghost`-Bibliothek intern wiederverwendet |

### Technische Realität (Arctis-spezifisch)

- **Implementierung** vermutlich neues Paket oder Modulbaum (z. B. `arctis_ghost_zero/` oder Dienst unter `scripts/`), der **`arctis_ghost`-APIs** aufruft — nicht die Engine.  
- **Plattform:** Windows/macOS/Linux unterscheiden sich bei Hot-Folder, Symlinks, Clipboard — Epics einzeln priorisieren (z. B. A1 zuerst nur POSIX oder nur Windows nach Markt).  
- **Abnahme:** Pro Epic: Szenario-Test + Sicherheits-Review (kein Credential-Leak in Sidecar-Logs).

### Bezug zum Projektplan §9 / Horizonte

A0 überlappt thematisch mit **Zero-Interface-Betrieb** in [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) §1 und **H1–H4** („Beyond MVP“) in §9 — ist aber **konkreter benannt** als Lieferketten-Epics A1–A6. Bei Konflikt gewinnt: **API-Governance unangetastet**, A0 nur Client-Orchestrierung.

---

## 4. Empfohlene nächste Schritte (operativ)

1. **G0-Checkliste** oben abarbeiten; Owner pro Zeile (Release / CI / Docs / Security).  
2. **Launch-Entscheid** dokumentieren: nur G0 vs. G0 + A0-Mindestpaket (z. B. nur A1).  
3. **A0:** Epic A1 in ein Issue/Spec zerlegen (Watcher, Idempotenz mit State, Fehlerpfade).  
4. **Demos:** [arctis_ghost_demo_matrix.md](arctis_ghost_demo_matrix.md) um eine Zeile „Zero-Interface (A0)“ ergänzen, wenn Story verkaufsrelevant — mit ehrlichem Label **Roadmap**, bis A1 shippable ist.

---

## 5. Verknüpfte Dokumente

| Dokument | Rolle |
|----------|--------|
| [ghost_implementation_prompts.md](ghost_implementation_prompts.md) | Historische P-Prompts; Status P1–P14 erledigt |
| [ghost_cli_reference.md](ghost_cli_reference.md) | Referenz für G0-E2E und Betrieb |
| [arctis_rollout_anleitung_jetzt_bis_produkt.md](arctis_rollout_anleitung_jetzt_bis_produkt.md) | Gesamt-Rollout Engine + Ghost |
| [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md) | 60s-Story |
| [ghost_hooks_p14.md](ghost_hooks_p14.md) | Hook-Sicherheit (G0.5) |
| [ghost_staging_e2e.md](ghost_staging_e2e.md) | Staging-E2E-Checkliste (G0.4) |
| [arctis_package_strategy.md](arctis_package_strategy.md) | Paket-/PyPI-Strategie (G0.6) |
| [RELEASE.md](RELEASE.md) | Tagging & Release-Ablauf (G0.1) |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Lokale CI-Kommandos (G0.2/G0.3) |

---

*Revision: G0/A0 als Arctis-spezifische Phase nach Abschluss P14; Launch-Gate bewusst als Team-Parameter (G0-only vs. G0+A0) formuliert. G0-Artefakte (CHANGELOG, CI, README, Staging-Checkliste, Package-Strategy) im Repo umgesetzt.*
