"""Sanitizer 3.0 policy model and preset support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_ENTITY_TYPES = {
    "EMAIL",
    "PHONE",
    "CREDIT_CARD",
    "IBAN",
    "PASSPORT",
    "SSN",
    "VAT_EORI",
    "PERSON",
    "LOCATION",
    "ORG",
    "ACCOUNT_ID",
    "GENERIC_ID",
}

VALID_MODES = {"mask", "label", "rewrite"}
VALID_SENSITIVITY = {"strict", "balanced", "permissive"}

_PRESETS: dict[str, dict[str, Any]] = {
    "banking": {
        "entity_types": ["PERSON", "ACCOUNT_ID", "CREDIT_CARD", "IBAN", "VAT_EORI"],
        "default_mode": "mask",
        "mode_by_entity": {"PERSON": "label"},
        "sensitivity": "strict",
    },
    "healthcare": {
        "entity_types": ["PERSON", "LOCATION", "GENERIC_ID", "SSN", "PHONE", "EMAIL"],
        "default_mode": "label",
        "mode_by_entity": {"SSN": "mask", "GENERIC_ID": "mask"},
        "sensitivity": "strict",
    },
    "support": {
        "entity_types": ["EMAIL", "PHONE", "ACCOUNT_ID", "PERSON"],
        "default_mode": "mask",
        "mode_by_entity": {},
        "sensitivity": "balanced",
    },
    "legal": {
        "entity_types": ["PERSON", "ORG", "LOCATION", "GENERIC_ID"],
        "default_mode": "label",
        "mode_by_entity": {"GENERIC_ID": "mask"},
        "sensitivity": "balanced",
    },
}


@dataclass(frozen=True)
class SanitizerPolicy:
    entity_types: tuple[str, ...]
    mode_by_entity: dict[str, str]
    default_mode: str = "mask"
    sensitivity: str = "balanced"
    preset: str | None = None

    @classmethod
    def default(cls) -> "SanitizerPolicy":
        return cls(
            entity_types=(
                "EMAIL",
                "PHONE",
                "CREDIT_CARD",
                "IBAN",
                "PASSPORT",
                "SSN",
                "VAT_EORI",
            ),
            mode_by_entity={},
            default_mode="mask",
            sensitivity="balanced",
            preset=None,
        )

    @classmethod
    def from_preset(cls, name: str) -> "SanitizerPolicy":
        raw = _PRESETS.get(str(name).strip().lower())
        if raw is None:
            raise ValueError(f"unknown sanitizer preset: {name!r}")
        entity_types = tuple(str(x).upper() for x in raw["entity_types"])
        return cls(
            entity_types=entity_types,
            mode_by_entity={str(k).upper(): str(v).lower() for k, v in raw.get("mode_by_entity", {}).items()},
            default_mode=str(raw.get("default_mode", "mask")).lower(),
            sensitivity=str(raw.get("sensitivity", "balanced")).lower(),
            preset=str(name).strip().lower(),
        )

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "SanitizerPolicy":
        if raw is None:
            return cls.default()
        if not isinstance(raw, dict):
            raise ValueError("sanitizer policy must be a dict")

        # Backward-compatible adapter for legacy sanitizerConfig-like payloads.
        if "rules" in raw and "entity_types" not in raw:
            entity_types = [str(x).upper() for x in raw.get("rules", []) if isinstance(x, str)]
            raw = {
                "entity_types": entity_types,
                "default_mode": "mask",
                "mode_by_entity": {},
                "sensitivity": "balanced",
                "preset": raw.get("preset"),
            }

        preset = raw.get("preset")
        base = cls.default()
        if isinstance(preset, str) and preset.strip():
            base = cls.from_preset(preset.strip().lower())

        entity_types_raw = raw.get("entity_types", list(base.entity_types))
        if not isinstance(entity_types_raw, list):
            raise ValueError("entity_types must be a list[str]")
        entity_types: list[str] = []
        for item in entity_types_raw:
            if not isinstance(item, str):
                raise ValueError("entity_types must contain only strings")
            ent = item.strip().upper()
            if ent not in VALID_ENTITY_TYPES:
                raise ValueError(f"unsupported entity type: {ent}")
            if ent not in entity_types:
                entity_types.append(ent)

        default_mode = str(raw.get("default_mode", base.default_mode)).strip().lower()
        if default_mode not in VALID_MODES:
            raise ValueError("default_mode must be one of: mask, label, rewrite")

        sensitivity = str(raw.get("sensitivity", base.sensitivity)).strip().lower()
        if sensitivity not in VALID_SENSITIVITY:
            raise ValueError("sensitivity must be one of: strict, balanced, permissive")

        mode_by_entity = dict(base.mode_by_entity)
        extra_modes = raw.get("mode_by_entity", {})
        if not isinstance(extra_modes, dict):
            raise ValueError("mode_by_entity must be an object")
        for k, v in extra_modes.items():
            ent = str(k).strip().upper()
            if ent not in VALID_ENTITY_TYPES:
                raise ValueError(f"unsupported mode_by_entity key: {ent}")
            mode = str(v).strip().lower()
            if mode not in VALID_MODES:
                raise ValueError(f"unsupported mode for {ent}: {mode}")
            mode_by_entity[ent] = mode

        mode_by_entity = {k: v for k, v in mode_by_entity.items() if k in entity_types}
        return cls(
            entity_types=tuple(entity_types),
            mode_by_entity=mode_by_entity,
            default_mode=default_mode,
            sensitivity=sensitivity,
            preset=(str(preset).strip().lower() if isinstance(preset, str) and preset.strip() else base.preset),
        )

    def mode_for(self, entity_type: str) -> str:
        return self.mode_by_entity.get(str(entity_type).upper(), self.default_mode)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_types": list(self.entity_types),
            "mode_by_entity": dict(self.mode_by_entity),
            "default_mode": self.default_mode,
            "sensitivity": self.sensitivity,
            "preset": self.preset,
        }
