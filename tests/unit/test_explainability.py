from __future__ import annotations

from arctis.explainability.engine import build_explainability


def test_explainability_shapes() -> None:
    out = build_explainability(
        input_payload={"text": "my ssn is 123-45-6789"},
        output={"route": "manual_review", "confidence": 0.2},
        pipeline_version="1.0.0",
    )
    assert "input_highlights" in out
    assert "contrastive_explanations" in out
    assert "feature_importance" in out
    assert "sanitizer_trace" in out

