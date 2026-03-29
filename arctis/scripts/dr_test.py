"""
PostgreSQL disaster-recovery drill: create marker rows, pg_dump, drop DB, restore, verify.

Requires PostgreSQL DATABASE_URL and client tools on PATH or via PG_DUMP_PATH / PSQL_PATH.

Env:
  DATABASE_URL — SQLAlchemy URL (postgresql+psycopg://... or postgresql://...)
  PG_DUMP_PATH — default: pg_dump
  PSQL_PATH — default: psql
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from arctis.db.models import Pipeline, PipelineVersion, Tenant


def _libpq_connection_string(url) -> str:
    """pg_dump/psql expect postgresql://, not postgresql+psycopg://."""
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def main() -> int:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("DATABASE_URL is required", file=sys.stderr)
        return 1

    pg_dump_bin = os.environ.get("PG_DUMP_PATH", "pg_dump")
    psql_bin = os.environ.get("PSQL_PATH", "psql")

    url = make_url(raw)
    if not url.drivername.startswith("postgresql"):
        print("DR test requires a PostgreSQL DATABASE_URL", file=sys.stderr)
        return 1

    db_name = url.database
    if not db_name:
        print("DATABASE_URL must include a database name", file=sys.stderr)
        return 1

    admin_url = url.set(database="postgres")
    conn_str = _libpq_connection_string(url)
    marker = uuid.uuid4().hex[:12]
    tenant_name = f"dr_tenant_{marker}"
    pipeline_name = f"dr_pipeline_{marker}"

    engine = create_engine(raw)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        tenant = Tenant(name=tenant_name)
        session.add(tenant)
        session.flush()
        pipe = Pipeline(tenant_id=tenant.id, name=pipeline_name)
        session.add(pipe)
        session.flush()
        ver = PipelineVersion(
            pipeline_id=pipe.id,
            version="dr-1",
            definition={"steps": [], "dr_marker": marker},
        )
        session.add(ver)
        session.commit()

    engine.dispose()

    with tempfile.TemporaryDirectory() as tmp:
        dump_path = Path(tmp) / "arctis_dr.sql"
        subprocess.run(
            [pg_dump_bin, conn_str, "-f", str(dump_path), "--format=plain"],
            check=True,
        )

        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :d AND pid <> pg_backend_pid()"
                ),
                {"d": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        admin_engine.dispose()

        subprocess.run(
            [psql_bin, conn_str, "-v", "ON_ERROR_STOP=1", "-f", str(dump_path)],
            check=True,
        )

    engine2 = create_engine(raw)
    SessionLocal2 = sessionmaker(bind=engine2)
    with SessionLocal2() as session:
        found = session.scalars(select(Pipeline).where(Pipeline.name == pipeline_name)).first()
        if found is None:
            print("DR verify failed: pipeline not found after restore", file=sys.stderr)
            return 1

    engine2.dispose()
    print("DR OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
