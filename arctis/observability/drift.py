"""Drift indicators for confidence/sanitizer anomalies."""

from __future__ import annotations

from typing import Any


def compute_drift_indicators(output: dict[str, Any] | None) -> dict[str, Any]:
    text = str(output or {}).lower()
    confidence_mentions = text.count("confidence")
    sanitizer_mentions = sum(text.count(k) for k in ("ssn", "iban", "credit_card", "passport", "vat_eori"))
    return {
        "confidence_shift_indicator": float(1.0 if confidence_mentions > 0 else 0.0),
        "sanitizer_anomaly_indicator": float(1.0 if sanitizer_mentions > 10 else 0.0),
    }

