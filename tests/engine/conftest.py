"""Fixtures for ``tests/engine`` (engine contract suite)."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from tests.engine.helpers import default_tenant


@pytest.fixture
def engine() -> Engine:
    return Engine()


@pytest.fixture
def tenant() -> TenantContext:
    return default_tenant()
