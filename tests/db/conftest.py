"""Fixtures for Control-Plane DB tests."""

from __future__ import annotations

import pytest
from arctis.db.base import Base
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def _set_sqlite_pragma(dbapi_conn, _connection_record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    event.listen(eng, "connect", _set_sqlite_pragma)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s
