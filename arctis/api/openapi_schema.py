"""Pydantic models used for OpenAPI request/response documentation (runs, evidence, customer execute)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CustomerExecuteSkillInvocationSchema(BaseModel):
    """One entry in the optional ``skills`` array on customer execute."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(
        ...,
        description=(
            "Registered skill id. Unknown ids yield **422** with ``unknown_skill``. "
            "Common advise-only ids include ``prompt_matrix``, ``routing_explain``, ``cost_token_snapshot``, "
            "``input_shape``, ``pipeline_config_matrix``, ``evidence_subset``, ``reviewer_explain``."
        ),
    )
    params: dict[str, Any] | None = Field(
        None,
        description="Optional skill-specific parameters (e.g. ``prompt_matrix`` → ``{\"mode\": \"advise\"}``).",
    )


class CustomerExecuteBodySchema(BaseModel):
    """JSON body for ``POST /customer/workflows/{workflow_id}/execute``."""

    model_config = ConfigDict(extra="ignore")

    input: dict[str, Any] = Field(
        ...,
        description="Customer input merged with the workflow template before validation and engine run.",
    )
    skills: list[CustomerExecuteSkillInvocationSchema] | None = Field(
        None,
        description=(
            "Optional skills to run around the engine execution; results appear under "
            "``execution_summary.skill_reports`` on **GET /runs/{run_id}** (and in evidence)."
        ),
    )


class SkillReportItemSchema(BaseModel):
    """One skill report as stored under ``execution_summary.skill_reports[<skill_id>]``."""

    model_config = ConfigDict(extra="allow")

    schema_version: str | None = Field(None, description="Report format version (e.g. ``1.0``).")
    payload: dict[str, Any] | None = Field(None, description="Skill-specific structured output.")
    provenance: dict[str, Any] | None = Field(
        None,
        description="Metadata such as ``skill_id``, ``mode: advise``, timestamps.",
    )


class TokenUsageSchema(BaseModel):
    """Token usage derived from engine cost info (E6)."""

    model_config = ConfigDict(extra="ignore")

    prompt: int | None = None
    completion: int | None = None
    total: int | None = None


class ExecutionSummarySchema(BaseModel):
    """Persisted execution metadata: cost, tokens, evidence, steps, mock flag, skill_reports."""

    model_config = ConfigDict(extra="allow")

    cost: float | None = Field(
        None,
        description="Gesamtkosten in EUR.",
    )
    evidence: dict[str, Any] | None = Field(
        None,
        description=(
            "E5 Evidence-Envelope (input_evidence, engine_evidence, cost_evidence, …). "
            "Bei Customer Execute enthält das Envelope zusätzlich **skill_reports** (Spiegel von "
            "``execution_summary.skill_reports``, unverändert). Vollständiges Bundle über GET /runs/{run_id}."
        ),
    )
    token_usage: TokenUsageSchema | None = None
    steps: list[Any] | None = Field(
        None,
        description="Engine step trace (sofern im Lauf erfasst).",
    )
    mock: bool | None = Field(
        None,
        description="True wenn der Lauf im E4-Mock-Modus ausgeführt wurde.",
    )
    skill_reports: dict[str, SkillReportItemSchema] | None = Field(
        None,
        description=(
            "Map skill_id → Skill-Report (schema_version, payload, provenance). "
            "E5: Teil des Evidence-Bundles; identische Daten liegen auch unter "
            "``execution_summary.evidence.skill_reports``. Abruf über GET /runs/{run_id}."
        ),
    )


class RunDetailResponse(BaseModel):
    """Single run including full execution_summary (cost, tokens, steps, evidence, skill_reports)."""

    model_config = ConfigDict(extra="ignore")

    run_id: UUID
    status: str
    input: dict[str, Any]
    output: Any | None = None
    pipeline_version_id: UUID
    workflow_id: UUID | None = None
    execution_summary: ExecutionSummarySchema | None = Field(
        None,
        description=(
            "Persistiertes Summary inkl. cost, token_usage, steps, evidence, mock, skill_reports. "
            "Nach Customer Execute (POST …/execute) mit Header X-Run-Id / Location hier abrufen."
        ),
    )


class RunEvidenceEnvelopeResponse(BaseModel):
    """Read-only slice of execution_summary for evidence viewers (E5)."""

    model_config = ConfigDict(extra="ignore")

    run_id: UUID
    evidence: dict[str, Any] | None = None


class PipelineRunCreatedResponse(BaseModel):
    """Body returned by POST /pipelines/{pipeline_id}/run (policy enrichment may add fields)."""

    model_config = ConfigDict(extra="allow")

    run_id: UUID
    status: str
    output: Any
    workflow_owner_user_id: UUID
    executed_by_user_id: UUID


class SnapshotReplayCreatedResponse(BaseModel):
    """Body returned by POST /snapshots/{snapshot_id}/replay."""

    model_config = ConfigDict(extra="ignore")

    run_id: UUID
    status: str
    output: Any
