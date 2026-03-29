"""Optional smoke: build the production Dockerfile and assert /health responds.

Skipped when the Docker CLI is not available (e.g. some local Windows setups without Docker).
CI runs the same check in `.github/workflows/ci.yml` (docker job).
"""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE_TAG = "arctis:test-pytest"
HOST_PORT = 18081


def _docker_cli() -> str | None:
    return shutil.which("docker")


@pytest.mark.skipif(_docker_cli() is None, reason="Docker CLI not available")
def test_dockerfile_builds_and_container_health() -> None:
    docker = _docker_cli()
    assert docker is not None

    subprocess.run(
        [docker, "build", "-t", IMAGE_TAG, str(ROOT)],
        check=True,
        timeout=900,
    )

    cmd = [
        docker,
        "run",
        "-d",
        "-p",
        f"{HOST_PORT}:8000",
        "-e",
        "ENV=prod",
        "-e",
        "DATABASE_URL=sqlite+pysqlite:////tmp/arctis_pytest.db",
        IMAGE_TAG,
    ]
    cid = subprocess.check_output(cmd, text=True).strip()
    try:
        url = f"http://127.0.0.1:{HOST_PORT}/health"
        deadline = time.monotonic() + 60.0
        last_err: BaseException | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    assert resp.status == 200
                    body = resp.read()
                    assert b"ok" in body.lower()
                return
            except (urllib.error.URLError, ConnectionResetError, BrokenPipeError) as e:
                last_err = e
                time.sleep(1.0)
        raise AssertionError(f"/health did not become ready: {last_err!r}")
    finally:
        subprocess.run([docker, "rm", "-f", cid], check=False, capture_output=True)
