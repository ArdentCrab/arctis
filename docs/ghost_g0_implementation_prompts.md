# Ghost G0 — kopierfertige Implementierungs-Prompts (Finalisierung bis Publish)

**Zweck:** Jeder Abschnitt ist ein **eigenständiger Prompt** für die nächste Session (Agent / Cursor). **Keine neuen Ghost-Features** — nur Release-, CI-, Doku- und Nachweis-Arbeit für das **Arctis**-Monorepo.

**Umsetzungs-Stand (Repo):** G1–G6 sind **einmal** im Repository angelegt (CHANGELOG, `docs/RELEASE.md`, `.github/workflows/ci.yml`, README/CONTRIBUTING, `docs/ghost_staging_e2e.md`, `docs/arctis_package_strategy.md`, Security-Querverweise, `pyproject.toml`-Metadaten). Wiederhole oder passe die Prompts bei neuen Releases an.

**Kanon:** [arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md) §2 (G0), [arctis_ghost_project_plan.md](arctis_ghost_project_plan.md) Leitprinzip HTTP-only.

**Reihenfolge (empfohlen):** G1 → G2 → G3 → G4 → G5 → G6. G4 und G6 können parallel zu Teilen von G3 laufen, wenn Owner getrennt sind.

**Hinweis:** Die **A0**-Epics (Zero-Interface) sind **nicht** Teil dieser Datei — siehe Roadmap §3; eigene Prompt-Serie kann später `ghost_a0_implementation_prompts.md` heißen.

---

## Abhängigkeiten (Kurz)

```text
G1 Release-Disziplin     → Basis für Tagging & Release-Notes
G2 CI                    → schützt main; sollte vor breitem Staging laufen
G3 README / Quickstart   → Nutzer sichtbar; kann früh mit G1 starten
G4 Staging-E2E           → braucht lauffähige API + Secrets (nicht im Repo)
G5 Sicherheitsdoku       → Review-Bündel; parallel zu G3 möglich
G6 PyPI-/Paket-Entscheid → strategisch; README-Sections oft Teil von G3
```

---

## G1 — Release-Disziplin (Version, CHANGELOG, Tags)

```markdown
# Arctis G1 — Release-Disziplin

## Ziel
Führe das Arctis-Repository in einen **nachvollziehbaren Release-Zustand**: eine klare **Versionsnummer**, ein **CHANGELOG**, und Regeln für **Git-Tags** und **Release-Notes** — ohne neue Produktfeatures.

## Kontext
- Paket-Version steht in `pyproject.toml` unter `[project] version`.
- Ghost-CLI ist über `[project.scripts] ghost = "arctis_ghost.cli:main"` gebündelt; Releases können API + Ghost gemeinsam betreffen.

## Anforderungen
- **Versionsschema** festlegen und dokumentieren (SemVer `MAJOR.MINOR.PATCH` oder Team-Standard); bei Vorab-Builds optional `-dev` / `.devN` nach Konvention.
- **`CHANGELOG.md`** im Repo-Root **oder** `docs/CHANGELOG.md` anlegen; mindestens ein Eintrag für den **nächsten** Release mit Sektionen: *Added* / *Changed* / *Fixed* / *Security* (falls zutrifft).
- Pro Release kurz trennen: **API/Backend** vs. **Ghost CLI** (Bullet-Liste reicht).
- **Tagging-Regel:** Git-Tag-Name = Paketversion (z. B. `v0.2.0`) oder dokumentierte Abweichung.
- **Release-Notes** (kurz, für GitHub/GitLab Release oder intern): Breaking Changes explizit (`ghost.yaml`-Felder, Env-Namen, API-Pfade).

## Dateien
- `pyproject.toml` (nur wenn Version angehoben wird)
- `CHANGELOG.md` oder `docs/CHANGELOG.md` (neu oder erweitert)
- Optional: `docs/RELEASE.md` mit Tagging- und Checklistenhinweis

## Akzeptanz
- Eine lesbare Version ist in `pyproject.toml` und im CHANGELOG konsistent referenziert.
- Team weiß, wie der nächste Tag gesetzt wird (Dokument oder RELEASE.md).

## Nicht-Ziele
- Kein automatisches Publishing (PyPI) — das ist G6.
```

---

## G2 — CI-Härtung (Tests, Ruff, Lockfile, optional Audit)

```markdown
# Arctis G2 — CI-Härtung

## Ziel
Absichern von **main** durch wiederholbare Checks: **pytest**, **ruff**, konsistente **Dependency-Erzeugung**, optional **pip-audit** und optional **Typcheck** für `arctis_ghost`.

## Kontext
- `pyproject.toml` enthält `[tool.ruff]` und optional `[project.optional-dependencies] dev/ci`.
- Repo hat `requirements-lock.txt` und Skripte unter `scripts/generate_requirements_lock.*`.

## Anforderungen
- **CI-Pipeline** (GitHub Actions, GitLab CI, oder vergleichbar): mindestens
  - Checkout, Python 3.11+ (gemäß `requires-python`),
  - Install (editable + ci/dev extras oder Lockfile-basiert),
  - `ruff check` auf die in `pyproject.toml` konfigurierten Pfade,
  - `pytest` mit sinnvoller Suite (mindestens `tests/ghost/`; idealerweise gesamte relevante Tests — Scope dokumentieren, wenn zeitlich begrenzt).
- **Lockfile:** CI soll entweder aus `requirements-lock.txt` installieren **oder** dokumentierten Schritt ausführen; bei Drift CI rot oder wöchentlicher Lock-Refresh-Prozess beschreiben.
- **Optional:** `pip-audit` als nicht-blockierender oder blockierender Job (Team-Entscheid).
- **Optional:** `mypy`/`pyright` nur für `arctis_ghost/` mit minimaler `pyproject.toml`-Konfiguration — wenn zu laut, erst Stub `py.typed` + Scope dokumentieren.

## Dateien
- `.github/workflows/*.yml` oder `.gitlab-ci.yml` (neu oder erweitert)
- `pyproject.toml` (nur bei neuen extras/Scripts)
- Kurz-Doku in `docs/` oder `CONTRIBUTING.md`: wie man CI lokal spiegelt

## Akzeptanz
- Ein frischer Clone erfüllt die gleichen Checks wie CI (README/CONTRIBUTING-Befehl).
- Ruff und pytest sind grün für den definierten Scope.

## Nicht-Ziele
- Vollständige Typisierung von `arctis/` Engine in einem Schritt.
```

---

## G3 — Installations- & Onboarding-Story (README, Quickstart, ghost.yaml)

```markdown
# Arctis G3 — Installation & Onboarding

## Ziel
Externe Nutzer und neue Entwickler finden im **Root-README** eine **klare Installationsanleitung**, einen **Ghost-Quickstart** (3–7 Schritte), und Verweise auf die **kanonische CLI-Doku** und die **60-Sekunden-Demo**.

## Kontext
- CLI: `python -m arctis_ghost.cli` oder installiertes Konsolen-Skript `ghost` (siehe `pyproject.toml`).
- Referenz: [ghost_cli_reference.md](ghost_cli_reference.md), [arctis_ghost_demo_60.md](arctis_ghost_demo_60.md).

## Anforderungen
- **README.md** (Root): Abschnitte mindestens
  - Was ist Arctis (ein Absatz),
  - **Installation** (editable + optional dev extras; Windows-Hinweis wo nötig),
  - **Ghost in 5 Minuten:** `ghost init-demo` → `ghost doctor` → Beispiel-`ghost run` (JSON oder Rezept) → optional `pull-artifacts` + `verify`,
  - Link zu `docs/ghost_cli_reference.md` und `docs/arctis_ghost_demo_60.md`,
  - Wenn das Repo **auch** die API startet: separater kurzer Block „Server starten“ mit Verweis auf bestehende Doku/Skripte (keine Duplikation der ganzen Architektur).
- **`ghost.yaml`:** im Quickstart erwähnen: Profil, `api_base_url`, `ARCTIS_API_KEY` über Env — **keine** echten Keys im README.
- Optional: **`CONTRIBUTING.md`** mit denselben Befehlen wie CI (Verweis auf G2).

## Dateien
- `README.md` (überarbeitet)
- Optional: `CONTRIBUTING.md`

## Akzeptanz
- Jemand ohne Vorkenntnis kann Ghost lokal installieren und einen dokumentierten Pfad bis zu einem erfolgreichen `doctor`/`run`-Flow nachvollziehen (gegen Mock oder Staging — siehe G4).

## Nicht-Ziele
- Marketing-Landingpage; Fokus technisch korrekt und knapp.
```

---

## G4 — Staging-E2E (einmal echter End-to-End-Nachweis)

```markdown
# Arctis G4 — Staging-E2E (Ghost)

## Ziel
**Ein dokumentierter** End-to-End-Durchlauf gegen eine **Staging-Arctis-API** (nicht Produktion): von lokaler Config bis zu Artefakten und Verify — als **Nachweis** für Go-Live-Readiness.

## Kontext
- Befehle: `ghost doctor`, `ghost run`, `ghost fetch` / `ghost watch`, `ghost pull-artifacts`, `ghost verify` (siehe [ghost_cli_reference.md](ghost_cli_reference.md)).
- Secrets nur über Env/Secret-Store; nichts ins Repo committen.

## Anforderungen
- Checkliste abarbeiten (Reihenfolge kann leicht variieren, muss aber dokumentiert sein):
  1. `ghost doctor` → OK gegen Staging-`api_base_url`.
  2. `ghost run` mit minimalem Execute-Body → `run_id` erhalten.
  3. `ghost fetch <run_id>` oder `ghost watch <run_id>` bis Terminalzustand klar.
  4. `ghost pull-artifacts <run_id>` → `outgoing/<run_id>/envelope.json` + `skill_reports/` wie erwartet.
  5. `ghost verify <run_id>` → OK (Konsistenz lokales Envelope vs. `GET /runs/{id}`).
- **Hooks:** optional einmal mit Testskript unter kontrolliertem Pfad; keine Produktions-PII in Logs.
- **Dokumentation des Laufs:** `docs/ghost_staging_e2e.md` (neu) oder Abschnitt in `docs/arctis_rollout_anleitung_jetzt_bis_produkt.md` mit **redacted** Beispiel-URLs, keinen Keys.

## Dateien
- Neu: `docs/ghost_staging_e2e.md` (oder Erweiterung bestehender Rollout-Doku)

## Akzeptanz
- Ein nachvollziehbarer schriftlicher Ablauf existiert; mindestens ein Maintainer hat ihn ausgeführt oder reviewed.
- Keine Secrets im Git.

## Nicht-Ziele
- Automatisierung in CI mit lebender Staging-API (optional später); G4 reicht als manueller Nachweis.
```

---

## G5 — Sicherheit & Betrieb (Doku-Bündel + Lücken schließen)

```markdown
# Arctis G5 — Sicherheit & Betrieb (Ghost)

## Ziel
Ein **konsistentes Doku-Bündel** für Betrieb und Security rund um Ghost: API-Keys, Hooks, Pfad-Sandbox, Limits, State — **Lücken** gegenüber [ghost_cli_reference.md](ghost_cli_reference.md), [ghost_hooks_p14.md](ghost_hooks_p14.md), [security_production.md](security_production.md) schließen oder Querverweise bereinigen.

## Kontext
- Ghost erzwingt keine serverseitige Policy; Client-Hooks haben **volle** Nutzerrechte.
- P10: Pfad- und Größenlimits; P14: Hooks mit Timeout.

## Anforderungen
- **Inventar:** Liste der Themen mit „gedeckt durch Dokument X“ oder „Lücke“.
- **Lücken schließen** durch kurze Absätze oder neue Unterseiten (kein Roman):
  - API-Keys: nur `ARCTIS_API_KEY` / Profil-Env; Warnung bei Klartext in `ghost.yaml` (bestehendes Verhalten kurz erklären).
  - Hooks: was stdin/Env enthält; kein Secret-Logging; `--no-hooks` für Audits.
  - Pfade: `resolve_under_cwd`; keine absoluten User-Pfade für Inputs.
  - Limits: Verweis auf `MAX_JSON_BYTES` / CLI-Limits.
  - State: `.ghost/state` sensibel; chmod-Hinweis wo relevant (POSIX).
- **Single entry point:** In `README.md` oder `security_production.md` ein klarer Link-Pfad „Ghost Security → …“.

## Dateien
- `docs/security_production.md`, `docs/ghost_cli_reference.md`, `docs/ghost_hooks_p14.md` (gezielte Edits)
- Optional: `docs/ghost_security_operator.md` (neu, 1–2 Seiten) falls Übersicht sonst zu zerstreut

## Akzeptanz
- Keine widersprüchlichen Aussagen zwischen den drei Kern-Dokumenten zu Keys und Hooks.
- Neue Leser finden in ≤2 Klicks die Hook-Sicherheitswarnung.

## Nicht-Ziele
- Penetrationstest oder formale Zertifizierung.
```

---

## G6 — PyPI- / Paket-Entscheid & README-Spiegelung

```markdown
# Arctis G6 — PyPI-/Paket-Strategie & README-Spiegelung

## Ziel
Eine **explizite Team-Entscheidung** dokumentieren: **Monorepo-Wheel `arctis`**, späteres **Split-Paket `arctis-ghost`**, oder **nur privates Registry/Source-Install** — plus **README-Anpassung**, damit Nutzer verstehen, was im Wheel enthalten ist und wie sie „nur Ghost“ minimal nutzen können.

## Kontext
- Aktuell: ein `[project]` mit Scripts `ghost` und Abhängigkeiten für API+Engine ([pyproject.toml](../pyproject.toml)).
- Roadmap-Optionen: siehe [arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md) §2.6.

## Anforderungen
- **Entscheidungs-Dokument** (kurz): `docs/arctis_package_strategy.md` oder Abschnitt in `README.md` mit Tabelle:
  - Option A: Monorepo publish — Vor-/Nachteile, wer installiert was.
  - Option B: Split später — Trigger (Kundenfeedback, Größe, Sicherheit).
  - Option C: Privat — wie Releases intern verteilt werden.
- **`pyproject.toml` review:** `readme`, `license`, `authors`/`maintainers` falls fehlend; `[project.urls]` für Repo/Doku/Changelog.
- **README:** Abschnitt „Paketinhalt“ (Ghost-CLI vs. Server) — keine falsche Erwartung „nur 5 MB Client“ wenn das Wheel groß ist.
- Optional: **classifiers** und **keywords** für PyPI, wenn öffentlich.

## Dateien
- `docs/arctis_package_strategy.md` (neu) oder erweiterte `README.md`
- `pyproject.toml` (Metadaten-Felder)

## Akzeptanz
- Stakeholder können in einem Dokument die Publish-Strategie nachlesen.
- PyPI-Metadaten sind konsistent mit der getroffenen Entscheidung (oder dokumentiert „noch nicht publiziert“).

## Nicht-Ziele
- Tatsächlicher PyPI-Upload in diesem Prompt — nur Vorbereitung und Strategie; Upload ist Release-Prozess nach G1+G2.
```

---

## Nutzung

1. Den gewünschten Prompt **komplett kopieren** (inkl. Überschrift `# Arctis Gn — …` innerhalb des Markdown-Blocks).
2. In Cursor einfügen und ausführen lassen.
3. Nach Abschluss: Status in CHANGELOG oder Team-Board festhalten; Roadmap [arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md) bei Bedarf mit „G1 erledigt“-Datum ergänzen.

**Referenz:** [arctis_ghost_g0_a0_roadmap.md](arctis_ghost_g0_a0_roadmap.md) §2 (G0-Querschnitt).
