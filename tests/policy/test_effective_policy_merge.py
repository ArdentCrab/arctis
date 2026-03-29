"""Unit tests for :func:`~arctis.policy.models.merge_policies`."""

from __future__ import annotations

from arctis.policy.models import PipelinePolicy, TenantPolicy, merge_policies


def _pipeline() -> PipelinePolicy:
    return PipelinePolicy(
        pipeline_name="pipeline_a",
        pipeline_version="v1.3-internal",
        default_approve_min_confidence=0.7,
        default_reject_min_confidence=0.7,
        default_required_fields=["prompt"],
        default_forbidden_key_substrings=["token", "password"],
        residency_required=True,
        audit_verbosity="standard",
    )


def test_tenant_overrides_routing_thresholds() -> None:
    p = _pipeline()
    t = TenantPolicy(
        tenant_id="t1",
        routing_approve_min_confidence=0.91,
        routing_reject_min_confidence=0.82,
    )
    eff = merge_policies(t, p)
    assert eff.approve_min_confidence == 0.91
    assert eff.reject_min_confidence == 0.82


def test_tenant_union_merges_required_and_forbidden_lists() -> None:
    p = _pipeline()
    t = TenantPolicy(
        tenant_id="t2",
        required_fields=["extra"],
        forbidden_key_substrings=["custom_secret"],
    )
    eff = merge_policies(t, p)
    assert eff.required_fields == ["prompt", "extra"]
    assert "token" in eff.forbidden_key_substrings
    assert "custom_secret" in eff.forbidden_key_substrings


def test_tenant_strict_residency_false_overrides_pipeline_residency_required() -> None:
    p = _pipeline()
    t = TenantPolicy(tenant_id="t3", strict_residency=False)
    eff = merge_policies(t, p)
    assert eff.strict_residency is False


def test_no_tenant_uses_pipeline_defaults() -> None:
    p = _pipeline()
    eff = merge_policies(None, p)
    assert eff.strict_residency is True
    assert eff.approve_min_confidence == 0.7
    assert eff.tenant_id is None
