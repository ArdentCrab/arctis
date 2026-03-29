#!/usr/bin/env bash
# Regenerate requirements-lock.txt (hashed, full transitive closure for .[ci]).
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install --upgrade pip pip-tools
python -m piptools compile --generate-hashes --extra ci -o requirements-lock.txt pyproject.toml
