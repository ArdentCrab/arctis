# Regenerate requirements-lock.txt (hashed lockfile for pyproject.toml [ci] extra).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m pip install --upgrade pip pip-tools
python -m piptools compile --generate-hashes --extra ci -o requirements-lock.txt pyproject.toml
