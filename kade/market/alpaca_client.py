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

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        raise NotImplementedError("Alpaca historical API integration will be added in a later phase.")


class MockAlpacaClient:
    """Deterministic mock market client for local dev/testing."""

    def get_latest_quote(self, symbol: str) -> Quote:
        return Quote(symbol=symbol, bid_price=100.0, ask_price=100.05)

    def get_latest_trade(self, symbol: str) -> Trade:
        return Trade(symbol=symbol, price=100.02, size=50, timestamp=datetime.now(timezone.utc))

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        now = datetime.now(timezone.utc)
        return self.get_historical_bars(symbol=symbol, timeframe=timeframe, start=now - timedelta(minutes=limit), end=now)[-limit:]

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        if timeframe != "1m":
            raise ValueError("MockAlpacaClient historical bars currently support only 1m timeframe")
        start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        bars: list[Bar] = []
        cursor = start_utc.replace(second=0, microsecond=0)
        index = 0
        while cursor <= end_utc:
            close = 100 + (index * 0.05)
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=cursor,
                    open=close - 0.1,
                    high=close + 0.2,
                    low=close - 0.2,
                    close=close,
                    volume=1000 + (index * 10),
                )
            )
            cursor += timedelta(minutes=1)
            index += 1
        return bars
