"""AI transform guardrails (Spec v1.5 §2.4, Security v1.3). Phase 3.8."""

from __future__ import annotations

import hashlib
from typing import Any

from arctis.errors import ComplianceError, SecurityError


class AITransform:
    def set_llm_client(self, client: Any) -> None:
        self.llm_client = client

    def validate_schema(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError("AI config must be a dict")
        if "input" not in config:
            raise ValueError("AI config missing required field: input")
        if "prompt" not in config:
            raise ValueError("AI config missing required field: prompt")
        if not isinstance(config["prompt"], str):
            raise ValueError("AI config prompt must be a string")

    def enforce_boundaries(
        self,
        config: dict[str, Any],
        tenant_context: Any,
        ai_region: str,
        forbidden_secrets: list[str],
    ) -> None:
        res = str(getattr(tenant_context, "data_residency", "")).casefold()
        reg = str(ai_region).casefold()
        if res != reg:
            raise ComplianceError("AI data residency violation")
        prompt = config["prompt"]
        for secret in forbidden_secrets:
            if secret and secret in prompt:
                raise SecurityError("forbidden secret in prompt")

    def run_transform(self, config: dict[str, Any]) -> dict[str, Any]:
        _zero_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        client = getattr(self, "llm_client", None)
        if client is not None:
            prompt = config["prompt"]
            raw_out = client.generate(prompt)
            result = raw_out if isinstance(raw_out, dict) else {}
            raw_u = result.get("usage")
            if not isinstance(raw_u, dict):
                raw_u = {}
            usage = {
                "prompt_tokens": int(raw_u.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(raw_u.get("completion_tokens", 0) or 0),
            }
            return {
                "text": str(result.get("text", "")).strip(),
                "usage": usage,
            }
        raw = (str(config["input"]) + "\0" + config["prompt"]).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        return {
            "result": f"deterministic:{digest}",
            "mode": "deterministic",
            "deterministic_digest": digest,
            "usage": dict(_zero_usage),
        }
