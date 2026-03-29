from __future__ import annotations

from arctis.matrix.analytics_engine import MatrixAnalyticsEngine
from arctis.matrix.recommendation_engine import MatrixRecommendationEngine


def test_matrix_analytics_and_recommendations() -> None:
    rows = [
        {"variant": "a", "status": "success", "cost": 1.0, "confidence": 0.8, "sanitizer_hits": 1},
        {"variant": "a", "status": "success", "cost": 1.2, "confidence": 0.9, "sanitizer_hits": 2},
        {"variant": "b", "status": "error", "cost": 0.5, "confidence": 0.4, "sanitizer_hits": 0},
    ]
    analytics = MatrixAnalyticsEngine().compute(rows)
    recs = MatrixRecommendationEngine().recommend(rows)
    assert "stability_score" in analytics
    assert "error_rate" in analytics
    assert recs["best_variant"] in {"a", "b"}
    assert recs["cheapest_variant"] in {"a", "b"}

