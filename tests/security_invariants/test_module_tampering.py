"""Marketplace module signing and tampering detection (Test Suite v1.1; Security v1.3 §4.2, §4.3)."""

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.errors import SecurityError

pytestmark = pytest.mark.security

_ORIGINAL = b"arctis:signed:module:v1:payload"
_MALICIOUS = b"arctis:signed:module:v1:evil"


def test_module_tampering_detected(engine, tenant_context) -> None:
    """Signed module must fail verification after tampering."""
    engine.load_module("safe.module@v1", signed=True, content=_ORIGINAL)
    engine.tamper_module("safe.module@v1", new_content=_MALICIOUS)
    engine.set_ai_region("US")
    engine.service_region = "US"
    ir = IRPipeline(
        name="t",
        nodes={
            "m": IRNode(name="m", type="module", config={"using": "safe.module@v1"}, next=[]),
        },
        entrypoints=["m"],
    )
    with pytest.raises(SecurityError, match="signature mismatch|unsigned"):
        engine.run(ir, tenant_context)


def test_unsigned_module_rejected(engine, tenant_context) -> None:
    """Unsigned modules must not pass verification."""
    engine.load_module("unsigned.module@v1", signed=False)
    engine.set_ai_region("US")
    engine.service_region = "US"
    ir = IRPipeline(
        name="t",
        nodes={
            "m": IRNode(name="m", type="module", config={"using": "unsigned.module@v1"}, next=[]),
        },
        entrypoints=["m"],
    )
    with pytest.raises(SecurityError, match="unsigned module"):
        engine.run(ir, tenant_context)
