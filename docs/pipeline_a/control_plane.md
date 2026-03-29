# Control plane (pipelines)

## Modules

- **`arctis/control_plane/pipelines.py`** — `PipelineStore`: create pipeline, add version, list, get IR for a version. `execute_pipeline(...)` runs the engine with tenant context, payload, and optional pipeline version.

## Usage (Python)

1. Construct `PipelineStore()` (in-memory for tests and demo).
2. Register an IR: `create_pipeline(name, ir, version)` or add versions with `add_version`.
3. Build `TenantContext` (tenant id, residency, limits, `dry_run` as needed).
4. Call `execute_pipeline(pipeline_id, tenant_context, payload, store=..., pipeline_version="x.y.z")`.

## Versioning

Multiple semver versions can exist per pipeline. Callers pass `pipeline_version` when executing; the store resolves the correct `IRPipeline`.

## Clearing state

`PipelineStore.clear()` drops all pipelines. Demo and tests call this when resetting.

## Relationship to workflows

Workflows use the same `PipelineStore` to resolve pipeline + version when running (see [workflows.md](./workflows.md)).
