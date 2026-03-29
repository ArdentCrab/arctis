#!/usr/bin/env python3
"""
E2E: migrate DB, bootstrap API key, seed pipeline, start uvicorn, POST /pipelines/{id}/run x10.

Run from repo root:
  python scripts/run_e2e_pipeline_http.py

Uses DATABASE_URL from env or .env; defaults to ./alembic_dev.db.
FastAPI expects a real UUID path segment (no ``pipe-`` prefix).

Interactive dev (hot reload), run separately in a terminal::
  set PYTHONPATH=.
  python -m uvicorn arctis.api.main:app --reload --host 127.0.0.1 --port 8000

This script binds a free TCP port and omits ``--reload`` so the child process stops cleanly.
"""
from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPO = ROOT
API_KEY = "ARCTIS_DEV_123"
# Valid UUID for FastAPI (``pipe-...`` is not a UUID).
PIPELINE_ID = uuid.UUID("1c2e6aa0-6578-47fa-ba78-468988b6fc52")
HOST = "127.0.0.1"


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, 0))
    port = int(s.getsockname()[1])
    s.close()
    return port

# Schema uses ``runs`` (not ``pipeline_runs``).
REQUIRED_TABLES = frozenset({"tenants", "api_keys", "pipelines", "pipeline_versions", "runs"})

# One AI step ⇒ one entrypoint; with no LLM client the engine uses deterministic AI output.
_MINIMAL_PIPELINE_DEFINITION: dict = {
    "name": "e2e-pipeline",
    "steps": [
        {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
    ],
}


def _load_dotenv_database_url() -> None:
    if os.environ.get("DATABASE_URL"):
        return
    env_file = REPO / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                return
    db = (REPO / "alembic_dev.db").resolve()
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db.as_posix()}"


def _ensure_fernet() -> None:
    if not os.environ.get("ARCTIS_ENCRYPTION_KEY", "").strip():
        from cryptography.fernet import Fernet

        os.environ["ARCTIS_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")


def _sqlite_path_from_url(url: str) -> Path | None:
    for pattern in (
        r"sqlite\+pysqlite:///+(.+)",
        r"sqlite:///+(.+)",
    ):
        m = re.match(pattern, url.replace("\\", "/"))
        if m:
            p = Path(m.group(1))
            return p if p.is_absolute() else (REPO / p)
    return None


def _tables_present(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        return REQUIRED_TABLES <= names
    finally:
        conn.close()


def _run_alembic() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO,
        check=True,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )


def main() -> int:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _load_dotenv_database_url()
    _ensure_fernet()

    db_path = _sqlite_path_from_url(os.environ["DATABASE_URL"])
    if db_path is None:
        print("DATABASE_URL is not a sqlite file URL; cannot auto-migrate.", file=sys.stderr)
        return 1

    if not _tables_present(db_path):
        print("Running Alembic migrations…")
        _run_alembic()

    if not _tables_present(db_path):
        print("Required tables still missing after migrate.", file=sys.stderr)
        return 1

    from arctis.config import get_settings

    get_settings.cache_clear()

    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "bootstrap_initial_api_key.py")],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    if r.returncode != 0:
        return 1

    get_settings.cache_clear()

    from arctis.api.deps import reset_engine_singleton
    from arctis.app import create_app
    from arctis.db import reset_engine
    from arctis.db.models import ApiKey, Pipeline, PipelineVersion

    reset_engine()
    reset_engine_singleton()
    create_app()

    from arctis.api.middleware import hash_api_key_sha256
    from arctis.db import SessionLocal
    from sqlalchemy import select

    assert SessionLocal is not None

    digest = hash_api_key_sha256(API_KEY)
    with SessionLocal() as s:
        ak = s.scalars(select(ApiKey).where(ApiKey.key_hash == digest)).first()
        if ak is None or not ak.active:
            print("API key row missing or inactive after bootstrap.", file=sys.stderr)
            return 1
        tid = ak.tenant_id
        p = s.get(Pipeline, PIPELINE_ID)
        if p is None:
            s.add(Pipeline(id=PIPELINE_ID, tenant_id=tid, name="e2e-pipeline"))
            s.add(
                PipelineVersion(
                    id=uuid.uuid4(),
                    pipeline_id=PIPELINE_ID,
                    version="1.0.0",
                    definition=dict(_MINIMAL_PIPELINE_DEFINITION),
                )
            )
            s.commit()
        elif p.tenant_id != tid:
            print("Pipeline UUID exists for another tenant.", file=sys.stderr)
            return 1
        else:
            pv = s.scalars(
                select(PipelineVersion)
                .where(PipelineVersion.pipeline_id == PIPELINE_ID)
                .order_by(PipelineVersion.created_at.desc())
            ).first()
            if pv is not None:
                pv.definition = dict(_MINIMAL_PIPELINE_DEFINITION)
                s.commit()

    # Release SQLite file locks before the child uvicorn opens the same DB.
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()

    port = _pick_free_port()
    base = f"http://{HOST}:{port}"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    # Same DB + secrets as this process (avoids hitting another server on a fixed port).
    env["DATABASE_URL"] = os.environ["DATABASE_URL"]
    env["ARCTIS_ENCRYPTION_KEY"] = os.environ.get("ARCTIS_ENCRYPTION_KEY", "")
    # Deterministic AI path (no remote LLM) for stable E2E in Cursor.
    env["OPENAI_API_KEY"] = ""
    env["ARCTIS_USE_OLLAMA"] = "false"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "arctis.api.main:app",
            "--host",
            HOST,
            "--port",
            str(port),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    try:
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{base}/health", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
            if proc.poll() is not None:
                err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
                print(f"Uvicorn exited early: {err}", file=sys.stderr)
                return 1
        else:
            print("Server did not become healthy in time.", file=sys.stderr)
            return 1

        with httpx.Client(timeout=120.0) as client:
            for n in range(1, 11):
                resp = client.post(
                    f"{base}/pipelines/{PIPELINE_ID}/run",
                    headers={"x-api-key": API_KEY},
                    json={"input": {"x": "Hallo Welt"}},
                )
                if resp.status_code != 201:
                    print(f"Run {n}: HTTP {resp.status_code} {resp.text}", file=sys.stderr)
                    return 1
                data = resp.json()
                out = data.get("output")
                print(f"Run {n}: {out}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
