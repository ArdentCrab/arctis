#!/usr/bin/env python3
"""
Bootstrap a dev API key in SQLite (schema-aligned).

api_keys: id CHAR(32), tenant_id, key_hash, created_at, expires_at, active
Plaintext for clients: ARCTIS_DEV_123 (stored as SHA256 hex in key_hash).
Ids are uuid5(NAMESPACE_URL, ...) as 32-char hex (see tasks).
"""

from __future__ import annotations

import re
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Import same hashing as Control Plane middleware (run from repo root: PYTHONPATH=.).
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from arctis.api.middleware import hash_api_key_sha256  # noqa: E402

PLAIN_KEY = "ARCTIS_DEV_123"
KEY_ROW_ID = uuid.uuid5(uuid.NAMESPACE_URL, "key-initial")
TENANT_ROW_ID = uuid.uuid5(uuid.NAMESPACE_URL, "initial-tenant")


def _parse_sqlite_url(url: str) -> Path | None:
    m = re.match(r"sqlite\+pysqlite:///\.?/?(.+\.db)", url.replace("\\", "/"))
    if m:
        return Path(m.group(1))
    m2 = re.match(r"sqlite:///(.+\.db)", url.replace("\\", "/"))
    if m2:
        return Path(m2.group(1))
    return None


def resolve_db_path(repo_root: Path) -> Path:
    env_url = None
    env_file = repo_root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                env_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if env_url:
        p = _parse_sqlite_url(env_url)
        if p and not p.is_absolute():
            p = repo_root / p
        if p and p.exists():
            return p
    for name in ("alembic_dev.db", "arctis_dev.db"):
        p = repo_root / name
        if p.exists():
            return p
    return repo_root / "alembic_dev.db"


def _tenant_column_names(cur: sqlite3.Cursor) -> set[str]:
    return {row[1] for row in cur.execute("PRAGMA table_info(tenants)").fetchall()}


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = resolve_db_path(repo_root)
    if not db_path.exists():
        print(
            f"No SQLite database found at {db_path}; run Alembic migrations first.",
            file=sys.stderr,
        )
        return 1

    digest = hash_api_key_sha256(PLAIN_KEY)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    kid = KEY_ROW_ID.hex
    tid_new = TENANT_ROW_ID.hex

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT id FROM tenants LIMIT 1").fetchone()
        tenant_cols = _tenant_column_names(cur)

        if row is None:
            if {"id", "name", "created_at", "active"} <= tenant_cols:
                cur.execute(
                    """
                    INSERT INTO tenants (id, name, created_at, active)
                    VALUES (?, ?, ?, ?)
                    """,
                    (tid_new, "initial-dev", now, 1),
                )
            elif {"id", "name", "created_at"} <= tenant_cols:
                # Alembic schema: billing_status has default; no `active` on tenants.
                cur.execute(
                    "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
                    (tid_new, "initial-dev", now),
                )
            else:
                print("Unexpected tenants table layout; cannot insert.", file=sys.stderr)
                return 1
            tid = tid_new
        else:
            tid = row[0]
            if isinstance(tid, str) and len(tid) == 32:
                pass
            else:
                tid = str(tid).replace("-", "")

        cur.execute(
            """
            INSERT INTO api_keys (id, tenant_id, key_hash, created_at, expires_at, active)
            VALUES (?, ?, ?, ?, NULL, ?)
            ON CONFLICT(id) DO UPDATE SET
              tenant_id = excluded.tenant_id,
              key_hash = excluded.key_hash,
              created_at = excluded.created_at,
              expires_at = excluded.expires_at,
              active = excluded.active
            """,
            (kid, tid, digest, now, 1),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Initial API key created: {PLAIN_KEY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
