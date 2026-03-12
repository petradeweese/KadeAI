"""Alpaca-compatible market data adapter boundary for runtime wiring."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.integrations.marketdata.base import MarketDataProvider
from kade.market.alpaca_client import AlpacaClient, AlpacaConfig
from kade.market.structure import Bar, Quote, Trade


class AlpacaMarketDataProvider(MarketDataProvider):
    provider_name = "alpaca"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.api_key = str(cfg.get("api_key", "")).strip()
        self.secret_key = str(cfg.get("secret_key", "")).strip()
        self.base_url = str(cfg.get("base_url", "https://paper-api.alpaca.markets"))
        self.data_url = str(cfg.get("data_url", "https://data.alpaca.markets"))
        self.mock_on_unavailable = bool(cfg.get("mock_on_unavailable", True))
        self.historical_enabled = bool(cfg.get("historical_enabled", True))
        self.client = AlpacaClient(
            AlpacaConfig(
                api_key=self.api_key,
                secret_key=self.secret_key,
                base_url=self.base_url,
                data_url=self.data_url,
            )
        )

    def get_latest_quote(self, symbol: str) -> Quote:
        return self.client.get_latest_quote(symbol)

    def get_latest_trade(self, symbol: str) -> Trade:
        return self.client.get_latest_trade(symbol)

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        return self.client.get_bars(symbol, timeframe, limit)

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        if not self.historical_enabled:
            return []
        return self.client.get_historical_bars(symbol, timeframe, start, end)

    def health_snapshot(self, active: bool) -> ProviderHealth:
        ready = self.enabled and self.historical_enabled and bool(self.api_key and self.secret_key)
        state = "ready" if ready else "degraded"
        return ProviderHealth(
            provider_type="market_data",
            provider_name=self.provider_name,
            state=state,
            active=active,
            metadata={
                "enabled": self.enabled,
                "api_key_present": bool(self.api_key),
                "secret_key_present": bool(self.secret_key),
                "base_url": self.base_url,
                "data_url": self.data_url,
                "supports_streaming": False,
                "supports_historical_bars": True,
                "is_real_provider": True,
                "mock_on_unavailable": self.mock_on_unavailable,
                "historical_enabled": self.historical_enabled,
            },
        )
