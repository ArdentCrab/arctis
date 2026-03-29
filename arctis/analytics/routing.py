"""Routing analytics from persisted audit envelopes (Phase 12)."""

from __future__ import annotations

import math
from typing import Any


def _inner_audit(envelope: dict[str, Any]) -> dict[str, Any]:
    row = envelope.get("row")
    if not isinstance(row, dict):
        return {}
    inner = row.get("audit")
    return inner if isinstance(inner, dict) else {}


def _audit_ts(envelope: dict[str, Any]) -> int:
    inner = _inner_audit(envelope)
    ts = inner.get("ts")
    try:
        return int(ts) if ts is not None else 0
    except (TypeError, ValueError):
        return 0


def compute_route_distribution(audit_rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {"approve": 0, "reject": 0, "manual_review": 0, "other": 0}
    for env in audit_rows:
        inner = _inner_audit(env)
        r = inner.get("route")
        if r is None:
            out["other"] += 1
            continue
        key = str(r).strip().lower()
        if key in out:
            out[key] += 1
        else:
            out["other"] += 1
    return out


def compute_keyword_hits(audit_rows: list[dict[str, Any]]) -> dict[str, int]:
    """
    Aggregate explicit per-category keyword hit counts when audits include
    ``routing_keyword_hits`` (future engine emission). Otherwise returns zeros.
    """
    cats = ("manual_review_keywords", "reject_keywords", "approve_keywords")
    totals = {c: 0 for c in cats}
    for env in audit_rows:
        inner = _inner_audit(env)
        raw = inner.get("routing_keyword_hits")
        if not isinstance(raw, dict):
            continue
        for c in cats:
            try:
                totals[c] += int(raw.get(c, 0) or 0)
            except (TypeError, ValueError):
                pass
    return totals


def _float_confidence(inner: dict[str, Any]) -> float | None:
    for key in ("confidence", "llm_confidence", "model_confidence"):
        c = inner.get(key)
        if c is None:
            continue
        try:
            return float(c)
        except (TypeError, ValueError):
            continue
    return None


def compute_confidence_histogram(
    audit_rows: list[dict[str, Any]],
    *,
    bins: int = 5,
) -> dict[str, Any]:
    vals = []
    for env in audit_rows:
        v = _float_confidence(_inner_audit(env))
        if v is not None and math.isfinite(v):
            vals.append(max(0.0, min(1.0, v)))
    if not vals:
        return {"bins": [], "sample_count": 0}
    edges = [i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for v in vals:
        idx = min(bins - 1, int(v * bins))
        counts[idx] += 1
    labels = [f"{edges[i]:.2f}-{edges[i + 1]:.2f}" for i in range(bins)]
    return {
        "bins": [{"range": labels[i], "count": counts[i]} for i in range(bins)],
        "sample_count": len(vals),
    }


def detect_routing_drift(
    audit_rows: list[dict[str, Any]],
    *,
    baseline_window: int | None = None,
    current_window: int | None = None,
    relative_increase_threshold: float = 0.25,
) -> list[dict[str, Any]]:
    """
    Compare route distributions between an earlier baseline slice and a recent slice.

    Default: first half vs second half of rows ordered by audit ``ts``.
    """
    ordered = sorted(audit_rows, key=_audit_ts)
    n = len(ordered)
    if n < 4:
        return []

    if baseline_window is not None and current_window is not None and baseline_window + current_window <= n:
        base = ordered[:baseline_window]
        cur = ordered[-current_window:]
    else:
        mid = n // 2
        base = ordered[:mid]
        cur = ordered[mid:]

    d1 = compute_route_distribution(base)
    d2 = compute_route_distribution(cur)
    t1 = sum(d1.values()) or 1
    t2 = sum(d2.values()) or 1

    signals: list[dict[str, Any]] = []
    for label in ("manual_review", "reject"):
        r1 = d1.get(label, 0) / t1
        r2 = d2.get(label, 0) / t2
        if r2 - r1 > relative_increase_threshold:
            signals.append(
                {
                    "type": f"increase_{label}",
                    "baseline_rate": round(r1, 4),
                    "current_rate": round(r2, 4),
                    "delta": round(r2 - r1, 4),
                }
            )

    hist = compute_confidence_histogram(cur)
    samples = hist.get("sample_count", 0)
    if samples >= 5:
        low = sum(b["count"] for b in hist.get("bins", [])[:2])
        if low / samples > 0.6:
            signals.append(
                {
                    "type": "threshold_sensitivity",
                    "detail": "high_share_of_low_confidence_audits",
                    "low_confidence_share": round(low / samples, 4),
                }
            )

    return signals
