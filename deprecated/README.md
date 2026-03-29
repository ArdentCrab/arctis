# Deprecated (Phase 2 cleanup)

This folder is reserved for **archived** Spec-layer code that was removed from the main package when it was stub-only or non-executable.

**Current state:** Pipeline A no longer ships separate Python files for sanitizer / schema / router “modules”; the canonical graph lives in `arctis/pipeline_a/__init__.py` (real `ai` / `effect` / `saga` steps only). Signature-only `module` stubs were not moved here because they were never standalone modules—only IR placeholders.

Reintroduce real implementations as normal package modules under `arctis/` (or a dedicated product package) when they execute real logic, then wire them via `module` steps and `ModuleRegistry`.
