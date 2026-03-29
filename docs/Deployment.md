# Deployment notes

## API base URL (OpenAPI servers)

- **Local:** `http://127.0.0.1:8000` (typical `uvicorn` default).
- **Production:** set your public HTTPS base URL (e.g. `https://api.yourcompany.com`). The checked-in `openapi.json` uses `https://api.example.com` as a placeholder—replace it when publishing client SDKs or external docs.

Interactive schema: `GET /openapi.json` on a running instance must match the repository `openapi.json` after `python scripts/generate_openapi.py`.

## Container image

Build and run (defaults: non-root user, `ENV=prod`, SQLite under `/home/arctis/data`; override `DATABASE_URL` for Postgres):

```bash
docker build -t arctis:latest .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+psycopg://user:pass@host:5432/arctis" \
  -e ENV=prod \
  arctis:latest
```

Apply migrations against that database before traffic: `alembic upgrade head` (see Alembic in this repo). Do not use `create_all()` in production.

## Disaster recovery

See **[DR.md](DR.md)** (backups, restore order, DR test checklist, RPO/RTO).

## Database schema (production)

Production and staging databases **must** be migrated with Alembic:

```bash
export DATABASE_URL="postgresql+psycopg://..."
alembic upgrade head
```

Do **not** rely on `Base.metadata.create_all()` to provision the main application schema in production. That path is reserved for tests and small in-memory helpers (for example policy seeding in development scripts).

After deploy, the schema should match the SQLAlchemy models under `arctis/db/models.py` and related `Base` metadata (policy, routing, audit tables), as enforced by the migration chain ending at the current `head` revision.
