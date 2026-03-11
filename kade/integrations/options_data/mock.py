"""Deterministic mock option-chain provider."""

from __future__ import annotations

from kade.integrations.health import ProviderHealth
from kade.integrations.options_data.base import OptionsDataProvider
from kade.options.mock_chain import build_mock_chain
from kade.options.models import OptionContract


class MockOptionsDataProvider(OptionsDataProvider):
    provider_name = "mock_chain"

    def get_option_chain(self, symbol: str, last_price: float | None = None) -> list[OptionContract]:
        return build_mock_chain(symbol, last_price)

    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth(
            provider_type="options_data",
            provider_name=self.provider_name,
            state="mock",
            active=active,
            metadata={
                "backend": "deterministic",
                "supports_greeks": True,
                "supports_expiration_filter": True,
                "is_real_provider": False,
            },
        )
