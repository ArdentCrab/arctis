# Workflows

## Module

- **`arctis/control_plane/workflows.py`** — `WorkflowStore`: create workflow (name, pipeline id, version, input template, metadata, tags), list, get, `run_workflow` with `TenantContext` and `PipelineStore`.

## Semantics

A workflow binds:

- Pipeline id and semver **pipeline version**
- Default **input template** (dict merged or passed through per implementation)
- Optional **metadata** and **tags** for routing/UI

`run_workflow` loads the IR from the pipeline store, merges runtime input, and executes via the same path as direct pipeline execution.

## Demo examples

`DemoSandbox.load_example_workflows()` registers three named workflows with fixed templates (`approve_small_amount`, `manual_review_medium_amount`, `reject_large_amount`). See `arctis/demo/sandbox.py` for exact payloads.

## Mock UI

The Pipeline A UI lists workflows from `ui/pipeline_a/src/mock/controlPlaneStore.ts` (seed data). Example names mirror the Python demo for consistency when comparing screenshots or manual checks.
