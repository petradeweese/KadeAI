"""Provider diagnostics helpers for runtime self-check visibility."""

from __future__ import annotations

from logging import Logger

from kade.integrations.health import ProviderHealth
from kade.logging_utils import LogCategory, get_logger, log_event


class ProviderDiagnostics:
    def __init__(self, policy: str = "warn_on_degraded", logger: Logger | None = None) -> None:
        self.policy = policy
        self.logger = logger or get_logger(__name__)

    def evaluate(self, checks: dict[str, ProviderHealth]) -> dict[str, object]:
        summary: dict[str, object] = {"policy": self.policy, "providers": {}}
        degraded: list[str] = []
        unavailable: list[str] = []
        for key, health in checks.items():
            payload = health.as_dict()
            summary["providers"][key] = payload
            state = str(payload.get("state", "unknown"))
            if state in {"degraded"}:
                degraded.append(key)
            if state in {"unavailable"}:
                unavailable.append(key)
            log_event(
                self.logger,
                LogCategory.PROVIDER_EVENT,
                "Provider diagnostic",
                provider_type=key,
                provider_name=payload.get("provider_name"),
                state=state,
                active=payload.get("active"),
            )
        summary["degraded"] = degraded
        summary["unavailable"] = unavailable
        summary["ready"] = not degraded and not unavailable
        return summary
