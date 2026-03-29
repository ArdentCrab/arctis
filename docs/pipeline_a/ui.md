# Pipeline A UI (mock)

## Location

`ui/pipeline_a/` — Vite, React 18, React Router, TypeScript (strict), Vitest + Testing Library.

## Behavior

- **Mock control plane** — `src/mock/controlPlaneStore.ts` + `src/mock/mockControlPlane.ts` simulate pipelines, workflows, snapshots, and masked keys. Data resets in tests via `resetStoreForTests()`.
- **No server** — all actions are synchronous in the browser; “Run” returns a static `RunResult`-shaped object.

## Routes

| Path | Screen |
|------|--------|
| `/` | Wizard (create pipeline mock) |
| `/editor` | Pipeline editor |
| `/workflows` | Workflow list / detail / mock run |
| `/audit` | Snapshot list and detail tabs |
| `/keys` | LLM + Arctis key management (masked) |

## Commands

```bash
cd ui/pipeline_a
npm install
npm run dev      # dev server
npm run build    # production build
npm run test     # vitest
npm run lint     # eslint (flat config: eslint.config.js)
```

## Conventions

- Shared styles: `src/components/shared.module.css`, shell: `src/pages/home.module.css`.
- Prefer existing CSS variables / dark theme tokens when adding components.
