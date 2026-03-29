# Architecture (Pipeline A)

## Layers

1. **IR** — `arctis/pipeline_a.py` builds a `IRPipeline` (nodes, edges, module ids) for the standard Pipeline A graph. `arctis/compiler.py` defines `IRPipeline` / `IRNode` and related structures used by the engine.

2. **Engine** — `arctis/engine/` executes compiled graphs: context, effects, snapshots, AI hooks (dry-run / deterministic paths in tests). The engine does not know HTTP or tenancy beyond `TenantContext`.

3. **Control plane** — `arctis/control_plane/pipelines.py` and `workflows.py` hold in-memory stores and orchestrate `execute_pipeline` / workflow runs against a `PipelineStore` + `WorkflowStore`.

4. **Demo** — `arctis/demo/sandbox.py` wires stores, registers example pipeline versions and workflows, runs dry executions, and records snapshot ids under string labels (see [demo_sandbox.md](./demo_sandbox.md)).

5. **UI (mock)** — `ui/pipeline_a/` is a Vite + React app with an in-memory mock control plane. No backend; useful for layout and Spec v1.3 UX flows.

## Data flow (execute)

`PipelineStore` resolves a pipeline id + optional version → `IRPipeline` → engine run → `RunResult` with traces, effects, snapshot references.

Workflows reference a pipeline id/version and an input template; running resolves the IR and executes with merged payload.

## Where to change what

| Change | Location |
|--------|----------|
| Graph shape / module order | `arctis/pipeline_a.py`, compiler types |
| Execution semantics | `arctis/engine/*` |
| Store API / execute entrypoints | `arctis/control_plane/*` |
| Demo seed data | `arctis/demo/sandbox.py` |
| Browser UI only | `ui/pipeline_a/src/*` |
