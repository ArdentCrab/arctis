"""Dry-run: effects are simulated, not applied."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline

pytestmark = pytest.mark.compliance


@pytest.fixture
def effect_ir() -> IRPipeline:
    return IRPipeline(
        name="dry_fx",
        nodes={
            "e": IRNode(
                name="e",
                type="effect",
                config={"type": "write", "key": "k", "value": 1},
                next=[],
            ),
        },
        entrypoints=["e"],
    )


def test_dry_run_records_mock_effect(engine, tenant_context_dry_run, effect_ir: IRPipeline) -> None:
    result = engine.run(effect_ir, tenant_context_dry_run)
    assert result.effects
    assert result.effects[0].get("mock") is True
    assert result.effects[0].get("reason") == "dry_run"
