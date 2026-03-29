# Pipeline A — developer docs

This folder describes how to **use and extend** Pipeline A in the Arctis repo. It does not restate the full product spec; see `docs/pipeline-a-v1.3.md` for normative requirements.

| Doc | Purpose |
|-----|---------|
| [architecture.md](./architecture.md) | Code layout, IR, engine, and how pieces connect |
| [control_plane.md](./control_plane.md) | Pipelines, versions, execution, stores |
| [workflows.md](./workflows.md) | Workflow store, binding to pipelines, runs |
| [ui.md](./ui.md) | React mock UI under `ui/pipeline_a/` |
| [demo_sandbox.md](./demo_sandbox.md) | `DemoSandbox`, reset script, snapshot labels |

**Quick paths**

- Run Python tests: from repo root, `python -m pytest tests/integration tests/unit` (or `make test` / `npm run test`).
- Run the mock UI: `cd ui/pipeline_a && npm install && npm run dev`.
- Reset in-process demo data (Python): `python scripts/dev_reset_demo.py` (prints snapshot label → id map).
