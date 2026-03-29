"""Unit tests for arctis.analytics.routing (Phase 12)."""

from __future__ import annotations

from arctis.analytics.routing import (
    compute_confidence_histogram,
    compute_keyword_hits,
    compute_route_distribution,
    detect_routing_drift,
)


def _row(route: str | None, ts: int, **extra) -> dict:
    audit = {"ts": ts, "route": route, **extra}
    return {"row": {"type": "audit", "audit": audit}}


def test_compute_route_distribution() -> None:
    rows = [
        _row("approve", 1),
        _row("reject", 2),
        _row("manual_review", 3),
        _row(None, 4),
        _row("unknown_route", 5),
    ]
    d = compute_route_distribution(rows)
    assert d["approve"] == 1
    assert d["reject"] == 1
    assert d["manual_review"] == 1
    assert d["other"] == 2


def test_compute_keyword_hits() -> None:
    rows = [
        {
            "row": {
                "audit": {
                    "routing_keyword_hits": {
                        "manual_review_keywords": 2,
                        "reject_keywords": 1,
                        "approve_keywords": 0,
                    }
                }
            }
        }
    ]
    h = compute_keyword_hits(rows)
    assert h["manual_review_keywords"] == 2
    assert h["reject_keywords"] == 1
    assert h["approve_keywords"] == 0


def test_compute_confidence_histogram_bins() -> None:
    rows = []
    for i in range(10):
        rows.append(_row("approve", i, confidence=i / 10.0))
    hist = compute_confidence_histogram(rows, bins=5)
    assert hist["sample_count"] == 10
    assert len(hist["bins"]) == 5


def test_detect_routing_drift_manual_review_spike() -> None:
    rows = []
    for i in range(4):
        rows.append(_row("approve", 10 + i))
    for i in range(4):
        rows.append(_row("manual_review", 100 + i))
    sig = detect_routing_drift(rows, relative_increase_threshold=0.2)
    assert any(s["type"] == "increase_manual_review" for s in sig)


def test_detect_routing_drift_reject_spike() -> None:
    rows = []
    for i in range(4):
        rows.append(_row("approve", i))
    for i in range(4):
        rows.append(_row("reject", 50 + i))
    sig = detect_routing_drift(rows, relative_increase_threshold=0.2)
    assert any(s["type"] == "increase_reject" for s in sig)


def test_detect_routing_drift_too_few_rows() -> None:
    rows = [_row("approve", 1), _row("approve", 2)]
    assert detect_routing_drift(rows) == []
