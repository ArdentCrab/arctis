"""Marketplace modules: signature verification before execution."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.errors import SecurityError

pytestmark = pytest.mark.compliance


def test_unsigned_module_rejected_on_run(engine, tenant_context) -> None:
    engine.load_module("unsigned.tool@v1", signed=False)
    ir = IRPipeline(
        name="mp",
        nodes={
            "m": IRNode(name="m", type="module", config={"using": "unsigned.tool@v1"}, next=[]),
        },
        entrypoints=["m"],
    )
    with pytest.raises(SecurityError, match="unsigned module"):
        engine.run(ir, tenant_context)


def test_signed_module_passes_verification(engine, tenant_context) -> None:
    engine.load_module(
        {
            "name": "signed.tool@v1",
            "version": "v1",
            "code": "pass",
            "signed": True,
        }
    )
    ir = IRPipeline(
        name="mp2",
        nodes={
            "m": IRNode(name="m", type="module", config={"using": "signed.tool@v1"}, next=[]),
        },
        entrypoints=["m"],
    )
    engine.run(ir, tenant_context)
