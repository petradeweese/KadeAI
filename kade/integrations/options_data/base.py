"""Adapter boundary for swappable option-chain providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kade.integrations.health import ProviderHealth
from kade.options.models import OptionContract


class OptionsDataProvider(ABC):
    provider_name: str

    @abstractmethod
    def get_option_chain(self, symbol: str, last_price: float | None = None) -> list[OptionContract]:
        ...

    @abstractmethod
    def health_snapshot(self, active: bool) -> ProviderHealth:
        ...
