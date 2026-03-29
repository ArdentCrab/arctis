"""Versioned effects & idempotency (Spec v1.5). Phase 3.7."""

from __future__ import annotations

from typing import Any

from arctis.errors import SecurityError

_ALLOWED_EFFECT_TYPES = frozenset({"write", "delete", "upsert"})


class EffectEngine:
    def __init__(self) -> None:
        self._effects: dict[str, dict[str, Any]] = {}

    def validate_effect(self, effect: dict[str, Any]) -> None:
        if not isinstance(effect, dict):
            raise SecurityError("effect must be a dict")
        for field in ("type", "key", "value"):
            if field not in effect:
                raise SecurityError(f"effect missing required field: {field}")
        typ = effect["type"]
        key = effect["key"]
        if not isinstance(typ, str) or not isinstance(key, str):
            raise SecurityError("effect type and key must be strings")
        if not key.strip():
            raise SecurityError("effect key must be non-empty")
        if typ not in _ALLOWED_EFFECT_TYPES:
            raise SecurityError("effect type not allowed")

    def is_idempotent(self, effect: dict[str, Any]) -> bool:
        key = effect["key"]
        if key not in self._effects:
            return True
        stored = self._effects[key]
        return stored["type"] == effect["type"] and stored["value"] == effect["value"]

    def apply_effect(self, effect: dict[str, Any]) -> dict[str, Any]:
        self.validate_effect(effect)
        if not self.is_idempotent(effect):
            raise SecurityError("non-idempotent effect")
        key = effect["key"]
        typ = effect["type"]
        val = effect["value"]
        if key not in self._effects:
            self._effects[key] = {"type": typ, "value": val, "version": 1}
        rec = self._effects[key]
        return {
            "key": key,
            "type": rec["type"],
            "value": rec["value"],
            "version": rec["version"],
            "idempotent": True,
        }
