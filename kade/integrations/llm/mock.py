"""Deterministic mock LLM provider."""

from __future__ import annotations

from kade.integrations.health import ProviderHealth
from kade.integrations.llm.base import LLMGeneration, LLMProvider


class MockLLMProvider(LLMProvider):
    provider_name = "mock"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.model = str(cfg.get("model", "mock-narrative"))

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMGeneration:
        content = prompt.strip().replace("\n", " ")
        if len(content) > 180:
            content = content[:177].rstrip() + "..."
        return LLMGeneration(
            provider_name=self.provider_name,
            model=self.model,
            success=self.enabled,
            content=f"Mock narrative summary: {content}" if content else "Mock narrative summary unavailable.",
            finish_reason="stop",
            raw_response={
                "system_prompt_present": bool(system_prompt),
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth(
            provider_type="llm",
            provider_name=self.provider_name,
            state="mock" if self.enabled else "disabled",
            active=active,
            metadata={"enabled": self.enabled, "model": self.model, "deterministic": True},
        )
