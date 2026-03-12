from kade.dashboard.app import create_app_status
from kade.market.intelligence.context import CrossSymbolContextEngine
from kade.market.intelligence.news import NewsNormalizer
from kade.market.intelligence.regime import MarketRegimeEngine
from kade.market.intelligence.service import MarketIntelligenceService
from kade.market.structure import TickerState
from kade.runtime.timeline import RuntimeTimeline


def _cfg() -> dict[str, object]:
    return {
        "sources": {"clock": False, "calendar": False, "news": False, "movers": False, "earnings": True},
        "alpaca": {"enabled": False, "api_key": "", "secret_key": ""},
        "news": {
            "max_items": 10,
            "classification_keywords": {
                "earnings": ["earnings", "guidance"],
                "analyst": ["upgrade", "downgrade"],
                "macro": ["cpi", "fomc"],
                "sector": ["semiconductor"],
                "product_company": ["launch"],
                "guidance": ["outlook"],
                "regulatory": ["sec", "fda"],
            },
        },
        "movers": {"top_movers_limit": 5, "most_active_limit": 5},
        "regime": {"trend_threshold_pct": 0.35, "chop_threshold_pct": 0.12, "volatile_threshold_pct": 1.2},
        "cross_symbol": {"benchmarks": ["QQQ", "SPY"], "conflict_threshold_pct": 0.25, "sector_proxy_by_symbol": {"NVDA": "SMH"}},
        "earnings": {"earnings_limit": 4},
        "history_retention": 3,
    }


def _state(symbol: str, *, last: float, vwap: float, trend: str, structure: str = "range_or_mixed", volume_state: str = "normal", confidence_label: str = "moderate") -> TickerState:
    return TickerState(symbol=symbol, last_price=last, vwap=vwap, trend=trend, structure=structure, volume_state=volume_state, confidence_label=confidence_label)


def test_regime_engine_deterministic_trend_classification() -> None:
    engine = MarketRegimeEngine({"trend_threshold_pct": 0.35, "chop_threshold_pct": 0.12, "volatile_threshold_pct": 1.2})
    first = engine.evaluate(
        generated_at="2026-01-01T14:30:00+00:00",
        market_clock_open=True,
        breadth_bias="risk_on",
        spy_trend_pct=0.55,
        qqq_trend_pct=0.62,
        volume_bias="expanding",
        intraday_range_state="expanded",
        has_major_news=False,
    )
    second = engine.evaluate(
        generated_at="2026-01-01T14:30:00+00:00",
        market_clock_open=True,
        breadth_bias="risk_on",
        spy_trend_pct=0.55,
        qqq_trend_pct=0.62,
        volume_bias="expanding",
        intraday_range_state="expanded",
        has_major_news=False,
    )

    assert first.regime_label == "trend"
    assert first.regime_confidence == second.regime_confidence
    assert first.reasons == second.reasons


def test_cross_symbol_alignment_and_conflict() -> None:
    engine = CrossSymbolContextEngine({"benchmarks": ["QQQ", "SPY"], "conflict_threshold_pct": 0.25, "sector_proxy_by_symbol": {"NVDA": "SMH"}})
    aligned = engine.evaluate(
        symbol="NVDA",
        symbol_trend_pct=0.5,
        benchmark_trends={"QQQ": 0.45, "SPY": 0.4},
        breadth_bias="risk_on",
        generated_at="2026-01-01T14:30:00+00:00",
    )
    conflict = engine.evaluate(
        symbol="NVDA",
        symbol_trend_pct=-0.5,
        benchmark_trends={"QQQ": 0.35, "SPY": 0.3},
        breadth_bias="risk_on",
        generated_at="2026-01-01T14:30:00+00:00",
    )

    assert aligned.alignment_label == "aligned"
    assert conflict.alignment_label == "conflict"
    assert conflict.sector_proxy == "SMH"


def test_news_catalyst_tagging_and_dedup() -> None:
    normalizer = NewsNormalizer(_cfg()["news"])
    items, summary = normalizer.normalize(
        [
            {"timestamp": "2026-01-01T14:30:00+00:00", "headline": "NVDA earnings beat and raises guidance", "summary": "Strong quarter", "symbols": ["NVDA"]},
            {"timestamp": "2026-01-01T14:30:00+00:00", "headline": "NVDA earnings beat and raises guidance", "summary": "Duplicate", "symbols": ["NVDA"]},
            {"timestamp": "2026-01-01T14:31:00+00:00", "headline": "CPI surprise points to macro pressure", "summary": "Macro pressure", "symbols": []},
        ],
        source="test",
        generated_at="2026-01-01T14:35:00+00:00",
    )

    assert len(items) == 2
    assert items[0].catalyst_type == "earnings"
    assert items[1].catalyst_type == "macro"
    assert summary.headline_count == 2


def test_service_fallback_and_runtime_payload_shape() -> None:
    service = MarketIntelligenceService(_cfg())
    snapshot = service.build_snapshot(
        ticker_states={
            "QQQ": _state("QQQ", last=500.0, vwap=498.0, trend="bullish", structure="trend", volume_state="expanding", confidence_label="high"),
            "SPY": _state("SPY", last=610.0, vwap=608.0, trend="bullish", structure="trend", volume_state="expanding", confidence_label="high"),
            "NVDA": _state("NVDA", last=950.0, vwap=948.0, trend="bullish", structure="trend", volume_state="heavy", confidence_label="high"),
        },
        latest_breadth={"bias": "risk_on"},
        watchlist=["QQQ", "SPY", "NVDA"],
    ).to_payload()

    assert snapshot["market_clock"]["source"] == "fallback"
    assert snapshot["regime"]["regime_label"] in {"trend", "range", "volatile", "chop", "news_event"}
    assert "NVDA" in snapshot["cross_symbol_context"]


def test_operator_console_market_intelligence_shape() -> None:
    payload = create_app_status(
        market_intelligence_payload={
            "generated_at": "2026-01-01T14:35:00+00:00",
            "market_clock": {"is_open": True},
            "market_calendar": [{"date": "2026-01-01"}],
            "regime": {"regime_label": "trend"},
            "key_news": [{"headline": "test"}],
            "top_movers": [{"symbol": "NVDA"}],
            "most_active": [{"symbol": "TSLA"}],
            "cross_symbol_context": {"NVDA": {"alignment_label": "aligned"}},
        }
    )

    block = payload["operator_console"]["market_intelligence"]
    assert block["regime"]["regime_label"] == "trend"
    assert block["top_movers"][0]["symbol"] == "NVDA"


def test_timeline_market_intelligence_events() -> None:
    timeline = RuntimeTimeline(retention=5)
    timeline.add_event("market_intelligence_updated", "2026-01-01T14:35:00+00:00", {"regime_label": "trend", "confidence": 0.81, "headline_count": 2, "movers_count": 3})
    timeline.add_event("regime_changed", "2026-01-01T14:36:00+00:00", {"from": "range", "to": "trend"})
    timeline.add_event("major_catalyst_detected", "2026-01-01T14:37:00+00:00", {"count": 1, "catalysts": ["macro"]})

    events = timeline.snapshot()["events"]
    assert [item["event_type"] for item in events][-3:] == [
        "market_intelligence_updated",
        "regime_changed",
        "major_catalyst_detected",
    ]
