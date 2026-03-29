from __future__ import annotations

from arctis.observability.monitoring import MonitoringRegistry


def test_labeled_counter_uses_prometheus_key_shape() -> None:
    reg = MonitoringRegistry()
    reg.inc_labeled("sanitizer_hits_total", 2, entity_type="PERSON")
    text = reg.export_prometheus_text()
    assert 'sanitizer_hits_total{entity_type="PERSON"} 2.0' in text
