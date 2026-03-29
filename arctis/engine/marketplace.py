"""Marketplace module registry & supply-chain checks (Spec v1.5 §5). Phase 3.13."""

from __future__ import annotations

import hashlib
from typing import Any

from arctis.errors import SecurityError


def _module_signature(name: str, version: str, code: str) -> str:
    """SHA-256 of UTF-8(name + NUL + version + NUL + code) — Spec v1.5 §3.13."""
    payload = str(name) + "\0" + str(version) + "\0" + str(code)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, dict[str, Any]] = {}
        self._executor_classes: dict[str, type] = {}

    def register_executor_class(self, module_ref: str, executor_cls: type) -> None:
        """Associate a ``using`` ref with a built-in executor class (optional; unsigned modules skip)."""
        self._executor_classes[str(module_ref)] = executor_cls

    def get_executor_class(self, module_ref: str) -> type | None:
        return self._executor_classes.get(str(module_ref))

    def load_module(self, module_dict: dict[str, Any]) -> None:
        if not isinstance(module_dict, dict):
            raise TypeError("module_dict must be a dict")
        for key in ("name", "version", "code"):
            if key not in module_dict:
                raise ValueError(f"module_dict missing required field: {key}")
        name = str(module_dict["name"])
        version = str(module_dict["version"])
        code = module_dict["code"]
        if isinstance(code, bytes):
            code_str = code.decode("utf-8")
        else:
            code_str = str(code)
        mod = dict(module_dict)
        mod["name"] = name
        mod["version"] = version
        mod["code"] = code_str
        signature = _module_signature(name, version, code_str)
        signed = bool(module_dict.get("signed", True))
        self._modules[name] = {
            "module": mod,
            "signature": signature,
            "signed": signed,
        }

    def verify_signature(self, module_name: str) -> None:
        if module_name not in self._modules:
            raise KeyError(module_name)
        entry = self._modules[module_name]
        if not entry.get("signed", True):
            raise SecurityError("unsigned module")
        mod = entry["module"]
        expected = entry["signature"]
        code = mod["code"]
        code_s = code.decode("utf-8") if isinstance(code, bytes) else str(code)
        actual = _module_signature(str(mod["name"]), str(mod["version"]), code_s)
        if actual != expected:
            raise SecurityError("module signature mismatch")

    def tamper_module(self, module_name: str, new_code: str) -> None:
        if module_name not in self._modules:
            raise KeyError(module_name)
        entry = self._modules[module_name]
        entry["module"]["code"] = str(new_code)

    def module_identity_for_ref(self, module_ref: str) -> str:
        """Stable string for pipeline hashing (signature when registered, else marker)."""
        ref = str(module_ref)
        entry = self._modules.get(ref)
        if entry is None:
            return f"unregistered:{ref}"
        sig = entry.get("signature")
        if isinstance(sig, str) and sig:
            return sig
        mod = entry.get("module") or {}
        return f"{mod.get('name', ref)}@{mod.get('version', '')}"
