"""Mark every test module under ``tests/integration`` with ``@pytest.mark.integration`` for CI."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = config.rootpath / "tests" / "integration"
    for item in items:
        try:
            p = item.path
        except AttributeError:
            continue
        if root in p.parents or p.parent == root:
            item.add_marker(pytest.mark.integration)
