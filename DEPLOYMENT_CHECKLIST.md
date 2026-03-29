# Deployment checklist

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
