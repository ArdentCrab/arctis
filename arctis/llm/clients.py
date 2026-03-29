"""LLM client implementations."""

from __future__ import annotations

import time
from typing import Any

import httpx


class OpenAIClient:
    """Minimal chat-completions client (OpenAI-compatible ``/v1/chat/completions``)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        last_err: Exception | None = None
        data: dict[str, Any] = {}
        for attempt in range(3):
            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                break
            except (httpx.HTTPError, ValueError) as e:
                last_err = e
                if attempt < 2:
                    time.sleep(0.35 * (2**attempt))
        else:
            assert last_err is not None
            raise last_err
        choice = data.get("choices") or []
        text = ""
        if choice and isinstance(choice[0], dict):
            msg = choice[0].get("message") or {}
            text = str(msg.get("content", "") or "")
        u = data.get("usage") or {}
        return {
            "text": text,
            "usage": {
                "prompt_tokens": int(u.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(u.get("completion_tokens", 0) or 0),
            },
        }


class OllamaClient:
    def __init__(self, model: str = "deepseek-r1:7b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def generate(self, prompt: str) -> dict[str, Any]:
        import requests

        resp = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "text": data.get("response", ""),
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
        }
