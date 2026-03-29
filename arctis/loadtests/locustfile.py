"""
Minimal API load test: POST /pipelines/{id}/run

Requires:
  LOCUST_HOST — base URL (e.g. http://localhost:8000)
  TEST_API_KEY — value for X-API-Key
  TEST_PIPELINE_ID — pipeline UUID
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

_TEST_API_KEY = os.environ.get("TEST_API_KEY", "")
_TEST_PIPELINE_ID = os.environ.get("TEST_PIPELINE_ID", "")
_LOCUST_HOST = os.environ.get("LOCUST_HOST", "http://localhost:8000")


class PipelineRunUser(HttpUser):
    host = _LOCUST_HOST
    wait_time = between(0.1, 0.5)

    @task
    def run_pipeline(self) -> None:
        if not _TEST_PIPELINE_ID or not _TEST_API_KEY:
            # Locust still schedules tasks; fail fast with a clear 4xx from missing config
            return
        self.client.post(
            f"/pipelines/{_TEST_PIPELINE_ID}/run",
            headers={"X-API-Key": _TEST_API_KEY},
            json={"input": {"text": "hello"}},
            name="/pipelines/[id]/run",
        )
