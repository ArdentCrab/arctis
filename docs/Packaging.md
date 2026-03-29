# Packaging & Delivery (Phase A2)

Kunden können Arctis **ohne** vollen Git-Zugriff nutzen — **Docker-Image**, **Wheel (`pip install`)** oder **eure gehostete API** (SaaS-Betrieb).  
Diese Seite entspricht **A2.1–A2.3**; das **Onboarding-Kit** liegt unter [`customer/README.md`](customer/README.md) (A2.4).

**Version:** siehe [`pyproject.toml`](../pyproject.toml) (`version = …`, aktuell **0.1.1**). Image- und Wheel-Tags daran ausrichten.

---

## A2.1 — Docker

**Offizielles Image (GHCR)** nach Release-Tag — `org`/`repo` entsprechen dem GitHub-Repository (hier: `arctis-engine/arctis` → Registry-Pfad kleingeschrieben):

```bash
docker pull ghcr.io/arctis-engine/arctis:0.1.1
# optional, wenn ihr :latest für stabile Tags pflegt (siehe Workflow):
docker pull ghcr.io/arctis-engine/arctis:latest
```

Lokal bauen:

```bash
docker build -t arctis:0.1.1 .
```

- **Tag:** `arctis:<version>` an die **Paketversion** koppeln (z. B. `0.1.1` aus `pyproject.toml`). CI publiziert zusätzlich **`latest`** nach Policy in [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml).  
- **Referenz:** [`Dockerfile`](../Dockerfile) — Multi-Stage, non-root, `ENV=prod`, Healthcheck auf `GET /health`.  
- **Nach dem Start:** `DATABASE_URL` auf Postgres setzen (Prod), **`alembic upgrade head`** gegen diese DB — siehe [`Deployment.md`](Deployment.md).  
- **Run:** siehe [`Deployment.md`](Deployment.md) Abschnitt Container image.

---

## A2.2 — Wheel (`dist/`)

Voraussetzung: `pip install build` (einmalig).

```bash
python -m build --wheel -o dist
```

- Ergebnis: **`dist/arctis-<version>-py3-none-any.whl`** (Version aus `pyproject.toml`).  
- Installation: `pip install dist/arctis-0.1.1-py3-none-any.whl` oder Publish auf privates/öffentliches Index.  
- **`dist/`** ist in [`.gitignore`](../.gitignore) — Artefakte nicht committen.  
- **Strategie** (Monorepo vs. späterer Ghost-Split): [`arctis_package_strategy.md`](arctis_package_strategy.md), Releases: [`RELEASE.md`](RELEASE.md).

---

## A2.3 — SaaS-Modell (was das Produkt heute hergibt)

| Thema | Im Produkt (Stand Repo) | Nicht als Feature versprechen |
|--------|---------------------------|-------------------------------|
| **Tenant** | Jeder API-Key ist an eine **`tenant_id`** gebunden ([`ApiKey`](../arctis/db/models.py)); Daten isoliert pro Tenant. | Self-Service **Tenant-Signup** ohne eure Prozesse — **Backlog**, nicht im Open-Source-Flow. |
| **API-URL** | Kunden setzen die **Basis-URL** eurer gehosteten Instanz (z. B. `https://api.example.com`). Ghost: `api_base_url` in `ghost.yaml`. | „Globales Arctis-SaaS“ als feste URL — nur wenn **ihr** sie betreibt und dokumentiert. |
| **API-Key** | Ausstellung über eure Betriebsprozesse / Admin-Pfade; Key = `X-API-Key`. | Automatischer Key-Shop ohne eure Implementierung. |
| **Limits** | **Rate-Limits** und Budgets über DB-Konfiguration (`tenant_rate_limits`, `api_key_rate_limits`, Budget-Felder) — siehe API und [`security_production.md`](security_production.md). | Garantierte **Pricing-Stufen** (Free/Pro) ohne eure Billing-Implementierung — nur dokumentieren, was wirklich ausgerollt ist. |

Alles darüber hinaus: im **Backlog** / Roadmap kennzeichnen, nicht als Lieferumfang **A2** ausweisen.

---

## Gate A2 (hart)

Ein **Kunde ohne Repo-Klon** kann starten, wenn ihr mindestens **einen** Weg anbietet und dokumentiert:

- **Docker** (Image ziehen oder Registry), **oder**  
- **Wheel / `pip install`** aus eurem Index, **oder**  
- **Gehostete API** (SaaS) mit Zugangsdaten und [`customer/README.md`](customer/README.md).

Die drei Wege sind in dieser Datei und im **Customer-Onboarding-Kit** verlinkt.
