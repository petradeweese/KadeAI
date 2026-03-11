"""Shared provider readiness/health payload helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProviderHealth:
    provider_type: str
    provider_name: str
    state: str
    active: bool
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_type": self.provider_type,
            "provider_name": self.provider_name,
            "state": self.state,
            "active": self.active,
            "metadata": self.metadata,
        }

