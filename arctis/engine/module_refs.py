"""Module ``using`` ref → stable identity strings (pipeline hashing, registry)."""

from __future__ import annotations

from typing import Any

from arctis.compiler import IRPipeline


def module_refs_for_ir(engine: Any, ir: IRPipeline) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in ir.nodes.values():
        if n.type == "module" and isinstance(n.config, dict):
            u = n.config.get("using")
            if u:
                ref = str(u)
                out[ref] = engine.module_registry.module_identity_for_ref(ref)
    return out
