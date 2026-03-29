"""Named LLM client registry."""

from __future__ import annotations

from typing import Any

from arctis.llm.clients import OllamaClient


class LLMRegistry:
    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def register(self, name: str, client: Any) -> None:
        self._clients[name] = client

    def get(self, name: str) -> Any:
        return self._clients[name]


llm_registry = LLMRegistry()
llm_registry.register("ollama", OllamaClient())
