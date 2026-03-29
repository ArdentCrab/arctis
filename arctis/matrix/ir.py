"""Prompt Matrix IR (configuration types)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MatrixCase(BaseModel):
    id: str
    input: dict[str, Any] = Field(default_factory=dict)


class MatrixVariant(BaseModel):
    name: str
    model: str
    region: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class MatrixRunConfig(BaseModel):
    pipeline_id: uuid.UUID
    cases: list[MatrixCase]
    variants: list[MatrixVariant]
    runs_per_case: int = Field(ge=1)
    tenant_api_key: str
    control_plane_url: str

    @field_validator("cases")
    @classmethod
    def _cases_nonempty(cls, v: list[MatrixCase]) -> list[MatrixCase]:
        if not v:
            msg = "cases must be non-empty"
            raise ValueError(msg)
        return v

    @field_validator("variants")
    @classmethod
    def _variants_nonempty(cls, v: list[MatrixVariant]) -> list[MatrixVariant]:
        if not v:
            msg = "variants must be non-empty"
            raise ValueError(msg)
        return v
