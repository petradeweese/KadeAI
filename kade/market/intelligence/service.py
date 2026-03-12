"""Market intelligence aggregation service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from kade.market.intelligence.context import CrossSymbolContextEngine
from kade.market.intelligence.earnings import EarningsNormalizer
from kade.market.intelligence.models import MarketCalendarDay, MarketClockSnapshot, MarketContextSnapshot
from kade.market.intelligence.movers import MoversNormalizer
from kade.market.intelligence.news import NewsNormalizer
from kade.market.intelligence.regime import MarketRegimeEngine
from kade.market.intelligence.utilities import as_utc_iso, infer_session_label
from kade.market.structure import TickerState
from kade.utils.time import utc_now_iso


class AlpacaMarketIntelligenceSource:
    """Thin inspectable transport wrapper for Alpaca intelligence endpoints."""

    def __init__(self, config: dict[str, object]) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.api_key = str(config.get("api_key", "")).strip()
        self.secret_key = str(config.get("secret_key", "")).strip()
        self.base_url = str(config.get("base_url", "https://paper-api.alpaca.markets")).rstrip("/")
        self.data_url = str(config.get("data_url", "https://data.alpaca.markets")).rstrip("/")

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key and self.secret_key)

    def market_clock(self) -> dict[str, object]:
        return self._get_json(f"{self.base_url}/v2/clock")

    def market_calendar(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        payload = self._get_json(f"{self.base_url}/v2/calendar?{urlencode({'start': start_date, 'end': end_date})}")
        return list(payload if isinstance(payload, list) else [])

    def news(self, symbols: list[str], limit: int) -> list[dict[str, object]]:
        query = {"limit": str(limit)}
        if symbols:
            query["symbols"] = ",".join(symbols)
        payload = self._get_json(f"{self.data_url}/v1beta1/news?{urlencode(query)}")
        return list(payload.get("news", [])) if isinstance(payload, dict) else []

    def screener_movers(self) -> dict[str, list[dict[str, object]]]:
        payload = self._get_json(f"{self.data_url}/v1beta1/screener/stocks/movers")
        if not isinstance(payload, dict):
            return {"gainers": [], "losers": []}
        return {
            "gainers": list(payload.get("gainers", [])),
            "losers": list(payload.get("losers", [])),
            "most_actives": list(payload.get("most_actives", [])),
        }

    def _get_json(self, url: str) -> dict[str, object] | list[object]:
        if not self.available:
            return {}
        request = Request(
            url,
            headers={"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret_key},
            method="GET",
        )
        with urlopen(request, timeout=20) as response:  # nosec - fixed host from config
            return json.loads(response.read().decode("utf-8"))


class MarketIntelligenceService:
    def __init__(self, config: dict[str, object]) -> None:
        self.cfg = config
        self.source_flags = dict(config.get("sources", {}))
        self.source = AlpacaMarketIntelligenceSource(dict(config.get("alpaca", {})))
        self.news = NewsNormalizer(dict(config.get("news", {})))
        self.movers = MoversNormalizer(dict(config.get("movers", {})) )
        self.earnings = EarningsNormalizer(dict(config.get("earnings", {})))
        self.regime = MarketRegimeEngine(dict(config.get("regime", {})))
        self.cross = CrossSymbolContextEngine(dict(config.get("cross_symbol", {})))

    def build_snapshot(self, *, ticker_states: dict[str, TickerState], latest_breadth: dict[str, object], watchlist: list[str]) -> MarketContextSnapshot:
        generated_at = utc_now_iso()

        clock = self._clock_snapshot(generated_at)
        calendar = self._calendar_snapshot(generated_at)
        raw_news = self._safe_fetch_news(watchlist)
        normalized_news, news_summary = self.news.normalize(raw_news, source="alpaca_or_fallback", generated_at=generated_at)

        raw_movers, raw_active = self._safe_fetch_movers_and_active(ticker_states)
        top_movers = self.movers.movers(raw_movers, source="alpaca_or_derived", generated_at=generated_at)
        most_active = self.movers.most_active(raw_active, source="alpaca_or_derived", generated_at=generated_at)

        earnings = self.earnings.normalize([], source="placeholder", generated_at=generated_at)
        regime = self.regime.evaluate(
            generated_at=generated_at,
            market_clock_open=clock.is_open,
            breadth_bias=str(latest_breadth.get("bias", "unknown")),
            spy_trend_pct=self._trend_pct(ticker_states.get("SPY")),
            qqq_trend_pct=self._trend_pct(ticker_states.get("QQQ")),
            volume_bias=self._volume_bias(ticker_states),
            intraday_range_state=self._intraday_range_state(ticker_states),
            has_major_news=any(item.catalyst_type in {"macro", "regulatory", "earnings"} for item in normalized_news[:3]),
        )

        benchmark_trends = {"QQQ": self._trend_pct(ticker_states.get("QQQ")), "SPY": self._trend_pct(ticker_states.get("SPY"))}
        cross_context = {
            symbol: self.cross.evaluate(
                symbol=symbol,
                symbol_trend_pct=self._trend_pct(state),
                benchmark_trends=benchmark_trends,
                breadth_bias=str(latest_breadth.get("bias", "unknown")),
                generated_at=generated_at,
            )
            for symbol, state in ticker_states.items()
            if symbol not in {"SPY", "QQQ"}
        }

        return MarketContextSnapshot(
            generated_at=generated_at,
            source="market_intelligence_service",
            market_clock=clock,
            market_calendar=calendar,
            regime=regime,
            key_news=normalized_news,
            top_movers=top_movers,
            most_active=most_active,
            earnings=earnings,
            cross_symbol_context=cross_context,
            debug={"news_summary": news_summary.to_payload(), "source_available": self.source.available},
        )

    def _clock_snapshot(self, generated_at: str) -> MarketClockSnapshot:
        default = MarketClockSnapshot(timestamp=generated_at, source="fallback", is_open=False, next_open=None, next_close=None, session_label="unknown")
        if not self.source_flags.get("clock", True):
            return default
        try:
            payload = self.source.market_clock()
            open_iso = as_utc_iso(payload.get("next_open"))
            close_iso = as_utc_iso(payload.get("next_close"))
            return MarketClockSnapshot(
                timestamp=generated_at,
                source="alpaca",
                is_open=bool(payload.get("is_open", False)),
                next_open=open_iso,
                next_close=close_iso,
                session_label=infer_session_label(bool(payload.get("is_open", False)), generated_at, open_iso, close_iso),
                debug={"timestamp": payload.get("timestamp")},
            )
        except Exception as exc:
            default.debug = {"error": str(exc)}
            return default

    def _calendar_snapshot(self, generated_at: str) -> list[MarketCalendarDay]:
        if not self.source_flags.get("calendar", True):
            return []
        try:
            now = datetime.now(timezone.utc).date()
            payload = self.source.market_calendar(start_date=now.isoformat(), end_date=(now + timedelta(days=1)).isoformat())
            days = []
            for item in payload[:2]:
                days.append(
                    MarketCalendarDay(
                        date=str(item.get("date") or now.isoformat()),
                        source="alpaca",
                        open_time=as_utc_iso(item.get("open")),
                        close_time=as_utc_iso(item.get("close")),
                        session_label="regular",
                    )
                )
            return days
        except Exception:
            return []

    def _safe_fetch_news(self, watchlist: list[str]) -> list[dict[str, object]]:
        if not self.source_flags.get("news", True):
            return []
        try:
            return self.source.news(symbols=watchlist[:8], limit=int(dict(self.cfg.get("news", {})).get("max_items", 12)))
        except Exception:
            return []

    def _safe_fetch_movers_and_active(self, ticker_states: dict[str, TickerState]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        if self.source_flags.get("movers", True):
            try:
                payload = self.source.screener_movers()
                gainers = [self._map_mover_item(item, "gainer") for item in payload.get("gainers", [])]
                losers = [self._map_mover_item(item, "loser") for item in payload.get("losers", [])]
                actives = [self._map_active_item(item) for item in payload.get("most_actives", [])]
                if gainers or losers or actives:
                    return gainers + losers, actives
            except Exception:
                pass
        return self._derive_movers_and_active(ticker_states)

    def _derive_movers_and_active(self, ticker_states: dict[str, TickerState]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        movers: list[dict[str, object]] = []
        active: list[dict[str, object]] = []
        for symbol, state in ticker_states.items():
            trend_map = {"bullish": 0.45, "bearish": -0.45, "neutral": 0.02}
            confidence_map = {"high": 1.0, "moderate": 0.7, "low": 0.35}
            slope = trend_map.get(str(state.trend), 0.0) * confidence_map.get(str(state.confidence_label), 0.5)
            pseudo_volume = 1000000.0 if state.volume_state in {"expanding", "heavy"} else 350000.0
            movers.append({"symbol": symbol, "change_pct": slope, "price": state.last_price, "volume": pseudo_volume, "mover_type": "derived"})
            active.append({"symbol": symbol, "volume": pseudo_volume, "price": state.last_price, "trade_count": None})
        movers = sorted(movers, key=lambda item: abs(float(item.get("change_pct", 0.0))), reverse=True)
        active = sorted(active, key=lambda item: float(item.get("volume", 0.0)), reverse=True)
        return movers, active

    @staticmethod
    def _map_mover_item(item: dict[str, object], mover_type: str) -> dict[str, object]:
        return {
            "symbol": item.get("symbol"),
            "change_pct": float(item.get("percent_change", item.get("change_pct", 0.0))),
            "price": item.get("price", item.get("last_price")),
            "volume": item.get("volume"),
            "mover_type": mover_type,
        }

    @staticmethod
    def _map_active_item(item: dict[str, object]) -> dict[str, object]:
        return {
            "symbol": item.get("symbol"),
            "volume": item.get("volume", 0),
            "trade_count": item.get("trade_count"),
            "price": item.get("price", item.get("last_price")),
        }

    @staticmethod
    def _trend_pct(state: TickerState | None) -> float | None:
        if state is None or state.last_price is None or state.vwap in {None, 0}:
            return None
        return round(((state.last_price - state.vwap) / state.vwap) * 100.0, 4)

    @staticmethod
    def _volume_bias(states: dict[str, TickerState]) -> str:
        values = [state.volume_state for state in states.values()]
        if not values:
            return "unknown"
        if values.count("expanding") >= max(1, len(values) // 2):
            return "expanding"
        if values.count("heavy") >= max(1, len(values) // 3):
            return "elevated"
        return "normal"

    @staticmethod
    def _intraday_range_state(states: dict[str, TickerState]) -> str:
        structures = [state.structure for state in states.values()]
        if structures.count("range_or_mixed") >= max(1, len(structures) // 2):
            return "compressed"
        return "expanded"
