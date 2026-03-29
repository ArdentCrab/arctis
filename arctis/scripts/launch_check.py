#!/usr/bin/env python3
"""
Arctis v1 launch readiness check.

Runs critical pre-production checks: database, Alembic, secrets, identity env,
API smoke (GET /health, GET /pipelines), Playwright E2E, and a short Locust run.

Required environment (fail-fast as each step runs):
  DATABASE_URL
  SENTRY_DSN
  STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
  ARCTIS_ENCRYPTION_KEY (valid Fernet key)
  CONTROL_PLANE_API_KEY
  Either full Auth0 set OR Supabase set (see check_identity)
  CONTROL_PLANE_URL (API base, no trailing slash required)
  TEST_PIPELINE_ID (for Locust)

Optional:
  TEST_API_KEY — defaults to CONTROL_PLANE_API_KEY for Locust
  LOCUST_HOST — defaults to CONTROL_PLANE_URL for Locust

Run from repository root:
  PYTHONPATH=. python -m arctis.scripts.launch_check
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import requests
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "dashboard"
LOCUSTFILE = REPO_ROOT / "arctis" / "loadtests" / "locustfile.py"

AUTH0_REQUIRED = (
    "AUTH0_SECRET",
    "AUTH0_BASE_URL",
    "AUTH0_ISSUER_BASE_URL",
    "AUTH0_CLIENT_ID",
    "AUTH0_CLIENT_SECRET",
)

SUPABASE_REQUIRED = (
    "NEXT_PUBLIC_SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
)


def _line(msg: str) -> None:
    print(msg)


def _header(title: str) -> None:
    _line("")
    _line("=" * 64)
    _line(f" {title}")
    _line("=" * 64)


def require_nonempty(name: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        _header("FAIL")
        _line(f"Missing or empty environment variable: {name}")
        sys.exit(1)
    return str(raw).strip()


def check_database() -> None:
    _line("[1/11] Database connectivity (DATABASE_URL)")
    url = require_nonempty("DATABASE_URL")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine.dispose()
    _line("  OK: database connection successful")


def check_alembic() -> None:
    _line("[2/11] Alembic migrations (current vs heads)")
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "current", "--check-heads"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        _header("FAIL")
        _line("Alembic reports the database is not at all head revision(s).")
        if err:
            _line(err)
        _line("Hint: run `alembic upgrade head` against this DATABASE_URL.")
        sys.exit(1)
    _line("  OK: `alembic current --check-heads` passed")


def check_sentry() -> None:
    _line("[3/11] SENTRY_DSN")
    require_nonempty("SENTRY_DSN")
    _line("  OK: SENTRY_DSN is set")


def check_stripe() -> None:
    _line("[4/11] Stripe keys")
    require_nonempty("STRIPE_SECRET_KEY")
    require_nonempty("STRIPE_WEBHOOK_SECRET")
    _line("  OK: STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET are set")


def check_encryption_key() -> None:
    _line("[5/11] ARCTIS_ENCRYPTION_KEY (Fernet)")
    raw = require_nonempty("ARCTIS_ENCRYPTION_KEY")
    try:
        Fernet(raw.encode("ascii"))
    except Exception as e:
        _header("FAIL")
        _line(f"ARCTIS_ENCRYPTION_KEY is not a valid Fernet key: {e}")
        sys.exit(1)
    _line("  OK: ARCTIS_ENCRYPTION_KEY is valid for Fernet")


def check_control_plane_api_key() -> None:
    _line("[6/11] CONTROL_PLANE_API_KEY")
    require_nonempty("CONTROL_PLANE_API_KEY")
    _line("  OK: CONTROL_PLANE_API_KEY is set")


def check_identity() -> None:
    _line("[7/11] Auth0 or Supabase environment variables")
    auth0_ok = all(
        os.environ.get(k) and str(os.environ.get(k)).strip() for k in AUTH0_REQUIRED
    )
    supabase_ok = all(
        os.environ.get(k) and str(os.environ.get(k)).strip() for k in SUPABASE_REQUIRED
    )
    if auth0_ok:
        _line("  OK: Auth0 variables are set (AUTH0_SECRET, AUTH0_BASE_URL, …)")
        return
    if supabase_ok:
        _line(
            "  OK: Supabase variables are set "
            "(NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)"
        )
        return
    _header("FAIL")
    _line("Set either all Auth0 variables:")
    _line(f"  {', '.join(AUTH0_REQUIRED)}")
    _line("or all Supabase variables:")
    _line(f"  {', '.join(SUPABASE_REQUIRED)}")
    sys.exit(1)


def check_api_smoke() -> None:
    _line("[8/11] API smoke (GET /health, GET /pipelines)")
    base = require_nonempty("CONTROL_PLANE_URL").rstrip("/")
    api_key = require_nonempty("CONTROL_PLANE_API_KEY")
    headers = {"X-API-Key": api_key}
    timeout = 30.0

    h = requests.get(f"{base}/health", timeout=timeout)
    if h.status_code != 200:
        _header("FAIL")
        _line(f"GET /health returned {h.status_code}")
        sys.exit(1)
    try:
        body = h.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or body.get("status") != "ok":
        _header("FAIL")
        _line(f"GET /health body unexpected: {h.text[:500]}")
        sys.exit(1)

    p = requests.get(f"{base}/pipelines", headers=headers, timeout=timeout)
    if p.status_code != 200:
        _header("FAIL")
        _line(f"GET /pipelines returned {p.status_code}: {p.text[:500]}")
        sys.exit(1)
    _line("  OK: GET /health and GET /pipelines succeeded")


def check_playwright() -> None:
    _line("[9/11] Playwright smoke (npm run test:e2e in dashboard/)")
    if not DASHBOARD_DIR.is_dir():
        _header("FAIL")
        _line(f"Dashboard directory not found: {DASHBOARD_DIR}")
        sys.exit(1)
    r = subprocess.run(
        ["npm", "run", "test:e2e"],
        cwd=DASHBOARD_DIR,
        env=os.environ.copy(),
    )
    if r.returncode != 0:
        _header("FAIL")
        _line("Playwright E2E exited with non-zero status.")
        sys.exit(1)
    _line("  OK: Playwright completed successfully")


def check_locust() -> None:
    _line("[10/11] Locust load test (10s, low load)")
    require_nonempty("TEST_PIPELINE_ID")
    env = os.environ.copy()
    if not env.get("TEST_API_KEY") and env.get("CONTROL_PLANE_API_KEY"):
        env["TEST_API_KEY"] = env["CONTROL_PLANE_API_KEY"]
    if not env.get("TEST_API_KEY"):
        _header("FAIL")
        _line("Set TEST_API_KEY or CONTROL_PLANE_API_KEY for Locust.")
        sys.exit(1)
    if not env.get("LOCUST_HOST") and env.get("CONTROL_PLANE_URL"):
        env["LOCUST_HOST"] = env["CONTROL_PLANE_URL"].rstrip("/")

    if not env.get("LOCUST_HOST"):
        _header("FAIL")
        _line("Set LOCUST_HOST or CONTROL_PLANE_URL for Locust.")
        sys.exit(1)

    if not LOCUSTFILE.is_file():
        _header("FAIL")
        _line(f"Locust file not found: {LOCUSTFILE}")
        sys.exit(1)

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(LOCUSTFILE.relative_to(REPO_ROOT)).replace("\\", "/"),
            "--headless",
            "-u",
            "2",
            "-r",
            "1",
            "-t",
            "10s",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    if r.returncode != 0:
        _header("FAIL")
        _line("Locust exited with non-zero status.")
        sys.exit(1)
    _line("  OK: Locust finished (10s headless)")


def print_summary_ok() -> None:
    _line("[11/11] Summary")
    _header("PASS — Launch readiness check succeeded")
    _line("All critical checks completed. Review CI logs for Playwright/Locust details.")


def main() -> None:
    _header("Arctis v1 Launch Readiness Check")
    _line(f"Repository root: {REPO_ROOT}")

    check_database()
    check_alembic()
    check_sentry()
    check_stripe()
    check_encryption_key()
    check_control_plane_api_key()
    check_identity()
    check_api_smoke()
    check_playwright()
    check_locust()
    print_summary_ok()


if __name__ == "__main__":
    main()
