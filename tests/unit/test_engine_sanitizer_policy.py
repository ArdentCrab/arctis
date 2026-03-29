from __future__ import annotations

from types import SimpleNamespace

from arctis.engine.modules.base import ModuleRunContext
from arctis.engine.modules.sanitizer import InputSanitizerExecutor


def test_input_sanitizer_executor_uses_policy_when_present() -> None:
    ex = InputSanitizerExecutor()
    ctx = ModuleRunContext(
        tenant_context=SimpleNamespace(sanitizer_policy={"entity_types": ["PERSON"], "default_mode": "label"}),
        ir=SimpleNamespace(name="pipeline_a"),
        step_outputs={},
        node_config={"using": "arctis.pipeline_a.input_sanitizer@v1"},
        governance_meta={},
    )
    out = ex.execute({"prompt": "Alice"}, ctx, [])
    assert out["policy"] is not None
    assert "[Person]" in out["payload"]["prompt"]
