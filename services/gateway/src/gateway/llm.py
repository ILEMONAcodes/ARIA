"""LLM clients behind one interface. The real provider client is built in phase C."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]], params: dict[str, Any]) -> LLMResult: ...


class FakeLLM:
    """Deterministic client for tests and local development."""

    def complete(self, messages: list[dict[str, str]], params: dict[str, Any]) -> LLMResult:
        last = messages[-1]["content"] if messages else ""
        text = f"[fake] {last[:80]}"
        return LLMResult(text=text, input_tokens=sum(len(m["content"]) // 4 + 1 for m in messages), output_tokens=len(text) // 4 + 1)


class ProviderLLM:
    """Real Gemma 4 API client. TODO (phase C): call the chosen provider with the API key
    from GATEWAY_PROVIDER_API_KEY, honour params.reasoning and params.json_schema,
    map provider errors to 502 and timeouts to 504."""

    def complete(self, messages: list[dict[str, str]], params: dict[str, Any]) -> LLMResult:
        raise NotImplementedError("Implement the provider call in phase C")
