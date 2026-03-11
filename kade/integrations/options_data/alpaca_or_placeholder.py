"""Real-provider boundary placeholder for future option-chain backends."""

from __future__ import annotations

from kade.integrations.health import ProviderHealth
from kade.integrations.options_data.base import OptionsDataProvider
from kade.options.models import OptionContract


class AlpacaOptionsDataProvider(OptionsDataProvider):
    provider_name = "alpaca_options"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.api_key = str(cfg.get("api_key", "")).strip()
        self.secret_key = str(cfg.get("secret_key", "")).strip()
        self.mock_on_unavailable = bool(cfg.get("mock_on_unavailable", True))
        self.supported = bool(cfg.get("supported", False))

    def get_option_chain(self, symbol: str, last_price: float | None = None) -> list[OptionContract]:
        raise NotImplementedError("Real option-chain transport not implemented yet. Use mock fallback.")

    def health_snapshot(self, active: bool) -> ProviderHealth:
        missing_credentials = not (self.api_key and self.secret_key)
        if not self.enabled:
            state = "disabled"
        elif not self.supported:
            state = "degraded"
        elif missing_credentials:
            state = "degraded"
        else:
            state = "ready"
        return ProviderHealth(
            provider_type="options_data",
            provider_name=self.provider_name,
            state=state,
            active=active,
            metadata={
                "enabled": self.enabled,
                "supported": self.supported,
                "api_key_present": bool(self.api_key),
                "secret_key_present": bool(self.secret_key),
                "supports_chain_fetch": self.supported,
                "is_real_provider": True,
                "mock_on_unavailable": self.mock_on_unavailable,
            },
        )
