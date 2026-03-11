"""Alpaca market data client wrapper and local mock implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .structure import Bar, Quote, Trade


@dataclass
class AlpacaConfig:
    api_key: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"
    data_url: str = "https://data.alpaca.markets"


class AlpacaClient:
    """Thin wrapper interface for Alpaca market data APIs.

    This class intentionally keeps transport implementation minimal in Phase 1.
    Replace `NotImplementedError` sections with SDK/http integration in Phase 2.
    """

    def __init__(self, config: AlpacaConfig) -> None:
        self.config = config

    def get_latest_quote(self, symbol: str) -> Quote:
        raise NotImplementedError("Alpaca API integration will be added in Phase 2.")

    def get_latest_trade(self, symbol: str) -> Trade:
        raise NotImplementedError("Alpaca API integration will be added in Phase 2.")

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        raise NotImplementedError("Alpaca API integration will be added in Phase 2.")


class MockAlpacaClient:
    """Deterministic mock market client for local dev/testing."""

    def get_latest_quote(self, symbol: str) -> Quote:
        return Quote(symbol=symbol, bid_price=100.0, ask_price=100.05)

    def get_latest_trade(self, symbol: str) -> Trade:
        return Trade(symbol=symbol, price=100.02, size=50, timestamp=datetime.now(timezone.utc))

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        now = datetime.now(timezone.utc)
        bars: list[Bar] = []
        for i in range(limit):
            close = 100 + (i * 0.05)
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=now - timedelta(minutes=limit - i),
                    open=close - 0.1,
                    high=close + 0.2,
                    low=close - 0.2,
                    close=close,
                    volume=1000 + (i * 10),
                )
            )
        return bars
