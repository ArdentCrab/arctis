"""Lightweight Prometheus-style monitoring registry."""

from __future__ import annotations

from collections import defaultdict
from time import perf_counter
from typing import Any


class MonitoringRegistry:
    def __init__(self) -> None:
        self.counters: dict[str, float] = defaultdict(float)
        self.histograms: dict[str, list[float]] = defaultdict(list)
        self.events: list[dict[str, Any]] = []

    def inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] += float(value)

    def inc_labeled(self, name: str, value: float = 1.0, **labels: str) -> None:
        if not labels:
            self.inc(name, value)
            return
        lab = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        metric = f"{name}{{{lab}}}"
        self.inc(metric, value)

    def observe(self, name: str, value: float) -> None:
        self.histograms[name].append(float(value))

    def event(self, kind: str, payload: dict[str, Any]) -> None:
        self.events.append({"kind": kind, "payload": dict(payload)})

    def export_prometheus_text(self) -> str:
        lines: list[str] = []
        for k, v in sorted(self.counters.items()):
            lines.append(f"{k} {v}")
        for k, vals in sorted(self.histograms.items()):
            if not vals:
                continue
            lines.append(f"{k}_count {len(vals)}")
            lines.append(f"{k}_sum {sum(vals)}")
        return "\n".join(lines) + "\n"

    def timer(self) -> "_Timer":
        return _Timer(self)


class _Timer:
    def __init__(self, registry: MonitoringRegistry) -> None:
        self.registry = registry
        self.start = perf_counter()

    def close(self) -> None:
        self.registry.observe("latency_histogram", (perf_counter() - self.start) * 1000.0)


registry = MonitoringRegistry()

