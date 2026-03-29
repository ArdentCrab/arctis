# Deployment checklist

## Infrastructure (A1.1)

- [ ] `ENV=prod` (oder gleichwertiges produktionsnahes Verhalten für Staging, siehe [`docs/Deployment.md`](docs/Deployment.md))
- [ ] `DATABASE_URL` gesetzt (Postgres o. Ä.; nicht SQLite auf ephemeral Disk in Prod)
- [ ] `alembic upgrade head` gegen diese Datenbank ausgeführt (vor Live-Traffic)
- [ ] `ALLOWED_ORIGINS` auf echte Frontend-Origins (komma-separiert)
- [ ] `ARCTIS_AUDIT_STORE` gewählt (`jsonl` \| `db` \| `none`); bei `jsonl`: `ARCTIS_AUDIT_JSONL_DIR` beschreibbar und gemountet

## Weitere Punkte

- [ ] SENTRY_DSN set (backend + dashboard)
- [ ] PROMETHEUS_ENABLED=true
- [ ] Stripe keys set
- [ ] Billing webhook configured
- [ ] ARCTIS_ENCRYPTION_KEY set
- [ ] CONTROL_PLANE_API_KEY set
- [ ] Auth0 callback URLs configured
- [ ] Alembic upgrade head applied
- [ ] Playwright smoke tests green
- [ ] Locust load test stable (<5% errors)
- [ ] DR test OK
- [ ] Statuspage updated
