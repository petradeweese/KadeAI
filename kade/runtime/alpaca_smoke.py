"""Structured Alpaca smoke-test runner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kade.integrations.marketdata.base import MarketDataProvider
from kade.market.intelligence.service import AlpacaMarketIntelligenceSource


class AlpacaSmokeTester:
    def __init__(self, market_data: MarketDataProvider, intelligence_source: AlpacaMarketIntelligenceSource) -> None:
        self.market_data = market_data
        self.intelligence_source = intelligence_source

    def run(self, symbol: str = "SPY") -> dict[str, object]:
        if not self.intelligence_source.available:
            return {
                "provider": "alpaca",
                "state": "disabled" if not self.intelligence_source.enabled else "degraded",
                "symbol": symbol,
                "checks": {},
                "summary": {"passed": 0, "failed": 0},
            }

        now = datetime.now(timezone.utc)
        checks = {
            "market_clock": self._check_market_clock(),
            "calendar": self._check_calendar(now),
            "historical_bars_1m": self._check_historical_bars(symbol, now),
            "news": self._check_news(symbol),
            "movers": self._check_movers(),
        }
        failed = [name for name, payload in checks.items() if payload.get("state") != "ready"]
        return {
            "provider": "alpaca",
            "state": "ready" if not failed else "degraded",
            "symbol": symbol,
            "checks": checks,
            "summary": {"passed": len(checks) - len(failed), "failed": len(failed), "failed_checks": failed},
        }

    def _check_market_clock(self) -> dict[str, object]:
        try:
            payload = self.intelligence_source.market_clock()
            return {
                "state": "ready",
                "is_open": bool(payload.get("is_open", False)),
                "next_open": payload.get("next_open"),
                "next_close": payload.get("next_close"),
            }
        except Exception as exc:
            return {"state": "degraded", "error": str(exc)}

    def _check_calendar(self, now: datetime) -> dict[str, object]:
        try:
            rows = self.intelligence_source.market_calendar(now.date().isoformat(), (now.date() + timedelta(days=1)).isoformat())
            return {
                "state": "ready",
                "count": len(rows),
                "dates": [item.get("date") for item in rows[:2] if isinstance(item, dict)],
            }
        except Exception as exc:
            return {"state": "degraded", "error": str(exc)}

    def _check_historical_bars(self, symbol: str, now: datetime) -> dict[str, object]:
        try:
            bars = self.market_data.get_historical_bars(symbol, "1m", now - timedelta(minutes=10), now)
            return {
                "state": "ready",
                "count": len(bars),
                "first_timestamp": bars[0].timestamp.isoformat() if bars else None,
                "last_timestamp": bars[-1].timestamp.isoformat() if bars else None,
            }
        except Exception as exc:
            return {"state": "degraded", "error": str(exc)}

    def _check_news(self, symbol: str) -> dict[str, object]:
        try:
            items = self.intelligence_source.news([symbol], limit=5)
            return {
                "state": "ready",
                "count": len(items),
                "headlines": [item.get("headline") for item in items[:3] if isinstance(item, dict)],
            }
        except Exception as exc:
            return {"state": "degraded", "error": str(exc)}

    def _check_movers(self) -> dict[str, object]:
        try:
            payload = self.intelligence_source.screener_movers()
            return {
                "state": "ready",
                "gainers_count": len(list(payload.get("gainers", []))),
                "losers_count": len(list(payload.get("losers", []))),
                "most_active_count": len(list(payload.get("most_actives", []))),
            }
        except Exception as exc:
            return {"state": "degraded", "error": str(exc)}
