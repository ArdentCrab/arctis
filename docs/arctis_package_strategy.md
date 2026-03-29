# Arctis — Paket- und Publish-Strategie

**Stand:** Team-Entscheidung festhalten; technische Umsetzung erfolgt im Release-Prozess ([`RELEASE.md`](RELEASE.md)).

## Aktueller Zustand

- Ein **Monorepo-Paket** `arctis` in [`pyproject.toml`](../pyproject.toml).
- Enthält u. a. **FastAPI-API**, **Engine-/Runtime-Code** unter `arctis/`, und **`arctis_ghost`** mit dem Konsolen-Entry-Point **`ghost`**.
- Ein gebautes Wheel enthält damit **mehr als nur** die Ghost-CLI — Installationsgröße und Abhängigkeiten (DB, uvicorn, …) sind für „nur Ghost“ nicht minimal.

## Optionen

| Option | Beschreibung | Wann sinnvoll |
|--------|----------------|---------------|
| **A — Monorepo publish** | Ein Paket `arctis` auf PyPI (oder privates Registry); Nutzer installieren alles. | Einheitlicher Release; Betreiber deployen API + Tools aus demselben Repo. |
| **B — Split `arctis-ghost`** | Später separates Paket nur mit `requests`, `pyyaml`, `arctis_ghost` — ohne FastAPI/DB. | Kunden wollen einen kleinen CLI-Only-Client ohne Server-Stack. |
| **C — Nur Source / privat** | Kein öffentliches PyPI; interne Registry oder `pip install git+…`. | Closed Source, Enterprise-Distribution. |

## Empfehlung (Arbeitsstand)

1. **Zuerst A oder C** wählen und **einen** Release-Prozess etablieren ([CHANGELOG](../CHANGELOG.md), Tags, CI).  
2. **B** erst evaluieren, wenn messbarer Bedarf (Support, Größe, Sicherheits-Audit) besteht — zusätzlicher Pflegeaufwand.

## README-Erwartung

- Root-[`README.md`](../README.md) macht klar: **Wheel-Inhalt** (API + Ghost) vs. „nur Ghost nutzen“ (dann ggf. Option B oder dokumentierter Minimal-Install aus Monorepo).

## PyPI-Metadaten

- `pyproject.toml` sollte `readme`, sinnvolle **keywords**/classifiers und sobald bekannt **Repository-URL** tragen — siehe aktuelle `[project]`-Felder.
