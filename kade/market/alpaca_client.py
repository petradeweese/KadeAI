"""Alpaca market data client wrapper and local mock implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .structure import Bar, Quote, Trade


@dataclass
class AlpacaConfig:
    api_key: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"
    data_url: str = "https://data.alpaca.markets"


class AlpacaClient:
    """Thin wrapper interface for Alpaca market data APIs.

    This class intentionally uses stdlib HTTP transport to keep behavior inspectable.
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
        if timeframe != "1m":
            raise ValueError("Alpaca historical bars currently support only 1m timeframe")
        if not (self.config.api_key and self.config.secret_key):
            raise RuntimeError("Alpaca credentials are required for historical transport")

        bars: list[Bar] = []
        page_token: str | None = None
        start_utc = self._utc(start)
        end_utc = self._utc(end)
        while True:
            params = {
                "symbols": symbol.upper(),
                "timeframe": "1Min",
                "start": start_utc.isoformat(),
                "end": end_utc.isoformat(),
                "sort": "asc",
                "limit": "10000",
                "adjustment": "raw",
                "feed": "iex",
            }
            if page_token:
                params["page_token"] = page_token
            url = f"{self.config.data_url.rstrip('/')}/v2/stocks/bars?{urlencode(params)}"
            request = Request(
                url,
                headers={
                    "APCA-API-KEY-ID": self.config.api_key,
                    "APCA-API-SECRET-KEY": self.config.secret_key,
                },
                method="GET",
            )
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            items = payload.get("bars", {}).get(symbol.upper(), [])
            for item in items:
                bars.append(
                    Bar(
                        symbol=symbol.upper(),
                        timestamp=self._parse_ts(item["t"]),
                        open=float(item["o"]),
                        high=float(item["h"]),
                        low=float(item["l"]),
                        close=float(item["c"]),
                        volume=float(item["v"]),
                    )
                )
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return sorted(bars, key=lambda item: item.timestamp)

    @staticmethod
    def _utc(ts: datetime) -> datetime:
        return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    @staticmethod
    def _parse_ts(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        return AlpacaClient._utc(datetime.fromisoformat(normalized))


class MockAlpacaClient:
    """Deterministic mock market client for local dev/testing."""

    def get_latest_quote(self, symbol: str) -> Quote:
        return Quote(symbol=symbol, bid_price=100.0, ask_price=100.05)

    def get_latest_trade(self, symbol: str) -> Trade:
        return Trade(symbol=symbol, price=100.02, size=50, timestamp=datetime.now(timezone.utc))

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        now = datetime.now(timezone.utc)
        interval = self._interval_minutes(timeframe)
        start = now - timedelta(minutes=max(limit, 1) * interval)
        return self.get_historical_bars(symbol=symbol, timeframe=timeframe, start=start, end=now)[-limit:]

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        interval = self._interval_minutes(timeframe)
        start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        bars_1m: list[Bar] = []
        cursor = start_utc.replace(second=0, microsecond=0)
        index = 0
        while cursor <= end_utc:
            close = 100 + (index * 0.05)
            bars_1m.append(
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
        if interval == 1:
            return bars_1m

        resampled: list[Bar] = []
        for idx in range(0, len(bars_1m), interval):
            chunk = bars_1m[idx : idx + interval]
            if len(chunk) < interval:
                break
            resampled.append(
                Bar(
                    symbol=symbol,
                    timestamp=chunk[0].timestamp,
                    open=chunk[0].open,
                    high=max(bar.high for bar in chunk),
                    low=min(bar.low for bar in chunk),
                    close=chunk[-1].close,
                    volume=sum(bar.volume for bar in chunk),
                )
            )
        return resampled

    @staticmethod
    def _interval_minutes(timeframe: str) -> int:
        if timeframe == "1m":
            return 1
        if timeframe == "5m":
            return 5
        if timeframe == "15m":
            return 15
        raise ValueError(f"Unsupported mock timeframe: {timeframe}")
