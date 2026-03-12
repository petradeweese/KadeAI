"""Base interface for swappable LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

from kade.integrations.health import ProviderHealth


@dataclass
class LLMGeneration:
    provider_name: str
    model: str
    success: bool
    content: str
    finish_reason: str
    error: str | None = None
    raw_response: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class LLMProvider(ABC):
    provider_name: str

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMGeneration:
        ...

    @abstractmethod
    def health_snapshot(self, active: bool) -> ProviderHealth:
        ...
