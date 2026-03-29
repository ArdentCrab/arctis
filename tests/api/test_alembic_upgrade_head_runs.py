"""Fresh DB: ``alembic upgrade head`` must materialize the full ORM schema (p18+)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

# Register every mapped table on Base before comparing metadata.
import arctis.audit.db_models  # noqa: F401
import arctis.db.models  # noqa: F401
import arctis.policy.db_models  # noqa: F401
import arctis.routing.models  # noqa: F401

from arctis.db.base import Base


@pytest.fixture()
def alembic_ini_path() -> Path:
    return Path(__file__).resolve().parents[2] / "alembic.ini"


def test_alembic_upgrade_head_matches_orm_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alembic_ini_path: Path
) -> None:
    db_file = tmp_path / "empty.db"
    url = f"sqlite+pysqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)

    cfg = Config(str(alembic_ini_path))
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        insp = inspect(engine)
        reflected = set(insp.get_table_names())

        assert "workflow_versions" in reflected
        assert "idempotency_keys" in reflected
        assert "prompt_matrices" in reflected

        uc_names = {u["name"] for u in insp.get_unique_constraints("idempotency_keys")}
        assert "uq_idempotency_keys_tenant_key" in uc_names

        wv_fk_targets = {fk["referred_table"] for fk in insp.get_foreign_keys("workflow_versions")}
        assert "workflows" in wv_fk_targets
        assert "pipeline_versions" in wv_fk_targets

        wv_cols = {c["name"] for c in insp.get_columns("workflow_versions")}
        assert wv_cols == {
            "id",
            "workflow_id",
            "version",
            "pipeline_version_id",
            "is_current",
            "upgrade_metadata",
            "input_template",
            "mock_mode",
            "created_at",
        }

        pm_cols = {c["name"] for c in insp.get_columns("prompt_matrices")}
        assert pm_cols == {
            "id",
            "owner_user_id",
            "prompt_a",
            "prompt_b",
            "created_at",
            "versions",
        }

        pv_cols = {c["name"] for c in insp.get_columns("pipeline_versions")}
        assert "sanitizer_policy" in pv_cols
        assert "reviewer_policy" in pv_cols
        assert "governance" in pv_cols
        assert "mock_mode" in pv_cols

        for tname, table in Base.metadata.tables.items():
            assert tname in reflected, f"table {tname!r} missing after upgrade"
            db_cols = {c["name"] for c in insp.get_columns(tname)}
            orm_cols = {c.name for c in table.columns}
            assert db_cols == orm_cols, (
                f"column mismatch on {tname!r}: only_in_db={db_cols - orm_cols!r} "
                f"only_in_orm={orm_cols - db_cols!r}"
            )
    finally:
        engine.dispose()
