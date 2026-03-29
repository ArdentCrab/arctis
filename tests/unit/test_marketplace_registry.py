"""ModuleRegistry: signatures, tamper detection (Engine Spec v1.5 §3.13)."""

import hashlib

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.engine.marketplace import ModuleRegistry
from arctis.engine.runtime import Engine
from arctis.errors import SecurityError
from tests.conftest import TenantContext


def _expected_sig(name: str, version: str, code: str) -> str:
    p = name + "\0" + version + "\0" + code
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


def test_load_module_stores_copy_and_signature() -> None:
    r = ModuleRegistry()
    src = {"name": "m", "version": "1", "code": "print(1)"}
    r.load_module(src)
    assert src["code"] == "print(1)"
    entry = r._modules["m"]
    assert entry["signature"] == _expected_sig("m", "1", "print(1)")
    assert entry["module"] is not src
    assert entry["module"]["code"] == "print(1)"


def test_verify_signature_key_error_when_missing() -> None:
    r = ModuleRegistry()
    with pytest.raises(KeyError):
        r.verify_signature("nope")


def test_unsigned_raises_before_signature_check() -> None:
    r = ModuleRegistry()
    r.load_module(
        {"name": "u", "version": "v1", "code": "x", "signed": False},
    )
    with pytest.raises(SecurityError, match="unsigned module"):
        r.verify_signature("u")


def test_tamper_invalidates_signature() -> None:
    r = ModuleRegistry()
    r.load_module({"name": "safe.module@v1", "version": "v1", "code": "orig"})
    r.tamper_module("safe.module@v1", "evil")
    assert r._modules["safe.module@v1"]["module"]["code"] == "evil"
    with pytest.raises(SecurityError, match="module signature mismatch"):
        r.verify_signature("safe.module@v1")


def test_load_accepts_bytes_code() -> None:
    r = ModuleRegistry()
    r.load_module({"name": "b", "version": "0", "code": b"abc"})
    assert r._modules["b"]["module"]["code"] == "abc"
    r.verify_signature("b")


def test_engine_run_verifies_module_ir_node() -> None:
    eng = Engine()
    eng.load_module({"name": "mod.ref@v1", "version": "v1", "code": "ok"})
    ir = IRPipeline(
        "p",
        nodes={
            "step1": IRNode(
                name="step1",
                type="module",
                config={"using": "mod.ref@v1"},
                next=[],
            ),
        },
        entrypoints=["step1"],
    )
    eng.run(ir, TenantContext())


def test_engine_module_unregistered_raises() -> None:
    eng = Engine()
    ir = IRPipeline(
        "p",
        nodes={
            "step1": IRNode(
                name="step1",
                type="module",
                config={"using": "missing@v1"},
                next=[],
            ),
        },
        entrypoints=["step1"],
    )
    with pytest.raises(SecurityError, match="module not registered"):
        eng.run(ir, TenantContext())
