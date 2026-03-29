# Launch readiness & Gates (A1.6)

Letzte Hürden vor einem **Go-Live** oder einem **Staging-Gate**: automatisierter Check, Smoke-/Lasttests und organisatorische Punkte (Statuspage, Support).  
Technische Referenz: [`arctis/scripts/launch_check.py`](../arctis/scripts/launch_check.py).

---

## 1. `launch_check` (Staging grün)

Vom **Repository-Root**:

```bash
python -m arctis.scripts.launch_check
```

Das Skript ist **fail-fast** (bei Fehler sofort `exit 1`). Am Ende bei Erfolg: **`PASS — Launch readiness check succeeded`**.

### Schritte (1/11 … 11/11)

| # | Prüfung |
|---|---------|
| 1 | Datenbank erreichbar (`DATABASE_URL`) |
| 2 | Alembic: `alembic current --check-heads` |
| 3 | `SENTRY_DSN` gesetzt |
| 4 | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| 5 | `ARCTIS_ENCRYPTION_KEY` (gültiger Fernet-String) |
| 6 | `CONTROL_PLANE_API_KEY` |
| 7 | **Auth0** (volles Set) **oder** **Supabase** (volles Set) — siehe [`Authentication.md`](Authentication.md) |
| 8 | API: `GET /health`, `GET /pipelines` mit `X-API-Key` (`CONTROL_PLANE_URL`) |
| 9 | **Playwright:** `npm run test:e2e` im Verzeichnis **`dashboard/`** |
| 10 | **Locust:** Headless-Lauf 10 s, [`arctis/loadtests/locustfile.py`](../arctis/loadtests/locustfile.py); benötigt u. a. `TEST_PIPELINE_ID`, `TEST_API_KEY` oder `CONTROL_PLANE_API_KEY`, `LOCUST_HOST` oder `CONTROL_PLANE_URL` |
| 11 | Zusammenfassung |

**Erforderliche Umgebungsvariablen** sind im Docstring von `launch_check.py` aufgelistet; ergänzend für Locust: **`TEST_PIPELINE_ID`** (UUID einer Pipeline im Ziel-Tenant).

---

## 2. Playwright (Smoke)

- Erwartet ein **`dashboard/`**-Projekt mit **`npm run test:e2e`**.  
- **Repo-Hinweis:** Das mitgelieferte `dashboard/` ist aktuell **minimal** (statische Dateien). Solange dort **kein** `package.json` mit Script `test:e2e` existiert, **scheitert Schritt 9** von `launch_check`. Behebung: E2E-Suite anlegen oder Skript anpassen (Team-Entscheidung) — nicht Teil der reinen Doku.

---

## 3. Locust (Lasttest, kurz)

- Standard: **10 s**, **2** User, **headless** (siehe `launch_check`).  
- **Fehlerquote &lt; 5 %:** Operatives Ziel aus dem Launch-Plan; `launch_check` prüft nur den **Exit-Code** von Locust. Für ein strenges Gate die Locust-Ausgabe oder CI-Logs **manuell** bewerten.

---

## 4. Statuspage & Support-Inbox (organisatorisch)

| Punkt | Hinweis |
|--------|---------|
| **Statuspage** | Öffentliche oder interne Verfügbarkeitsseite (z. B. Statuspage.io, internes Wiki) — Inhalt und URL im Betriebsteam pflegen, nicht im Repo. |
| **Support-Inbox** | Erreichbare Adresse/Queue für Kunden (z. B. `support@…`) — in Marketing und Onboarding-Dokumenten verlinken. |

---

## 5. Gate A1 (hart) — Querverweise

- [`DEPLOYMENT_CHECKLIST.md`](../DEPLOYMENT_CHECKLIST.md) — Abschnitt **Launch gates (A1.6)**  
- [`Deployment.md`](Deployment.md) — Überblick A1.x  
- [`agent_prompt_plan_launch_a0_a4.md`](agent_prompt_plan_launch_a0_a4.md) — Phase A1 im Launch-Plan  
