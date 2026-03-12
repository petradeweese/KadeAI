"""Adapter boundary for swappable market data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.market.structure import Bar, Quote, Trade


class MarketDataProvider(ABC):
    provider_name: str

    @abstractmethod
    def get_latest_quote(self, symbol: str) -> Quote:
        ...

    @abstractmethod
    def get_latest_trade(self, symbol: str) -> Trade:
        ...

    @abstractmethod
    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        ...

    @abstractmethod
    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        ...

    @abstractmethod
    def health_snapshot(self, active: bool) -> ProviderHealth:
        ...
