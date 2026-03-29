# Demo sandbox (`DemoSandbox`)

## Purpose

`arctis/demo/sandbox.py` provides **`DemoSandbox`**: a single object that loads example pipelines, workflows, and dry-run executions without external services. It uses public control-plane APIs only.

## Key symbols

- **`DEMO_FAKE_LLM_KEY`** — Placeholder string for docs/tests (`__DEMO_FAKE_LLM_KEY__`). Not a real secret.
- **`DemoSandbox.reset()`** — Clears stores, reloads example pipelines (two versions), workflows, and three dry-run snapshots.
- **`self.snapshots`** — Map **label → snapshot id string** (e.g. `demo_seed_1` → id from `RunResult`). Ids may repeat across engine instances in demo; labels are stable for scripts.

## Reset script

From repository root:

```bash
python scripts/dev_reset_demo.py
```

Prints snapshot labels and ids after `DemoSandbox().reset()`. Use for CI smoke checks or local verification.

## UI alignment

The mock UI shows a **Demo Mode** indicator on the audit viewer and lists example workflow names consistent with `load_example_workflows()`. Key management shows a **masked** row for the fake demo LLM key (display only).
