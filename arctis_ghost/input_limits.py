"""CLI input size limits (JSON vs general files)."""

from __future__ import annotations

# Aligned with security checklist: small JSON bodies, larger text/YAML recipe inputs.
MAX_JSON_BYTES = 1 * 1024 * 1024
MAX_CLI_FILE_BYTES = 5 * 1024 * 1024
