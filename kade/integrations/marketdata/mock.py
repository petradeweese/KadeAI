"""Deterministic mock market data provider."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.integrations.marketdata.base import MarketDataProvider
from kade.market.alpaca_client import MockAlpacaClient
from kade.market.structure import Bar, Quote, Trade


class MockMarketDataProvider(MarketDataProvider):
    provider_name = "mock_alpaca"

    def __init__(self) -> None:
        self.client = MockAlpacaClient()

    def get_latest_quote(self, symbol: str) -> Quote:
        return self.client.get_latest_quote(symbol)

    def get_latest_trade(self, symbol: str) -> Trade:
        return self.client.get_latest_trade(symbol)

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        return self.client.get_bars(symbol, timeframe, limit)

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        return self.client.get_historical_bars(symbol, timeframe, start, end)

    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth(
            provider_type="market_data",
            provider_name=self.provider_name,
            state="mock",
            active=active,
            metadata={
                "backend": "deterministic",
                "supports_streaming": False,
                "supports_historical_bars": True,
                "is_real_provider": False,
            },
        )
