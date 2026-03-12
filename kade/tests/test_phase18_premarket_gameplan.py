from kade.dashboard.app import create_app_status
from kade.gameplan.service import PremarketGameplanService
from kade.market.intelligence.models import (
    CrossSymbolContext,
    EarningsEvent,
    MarketClockSnapshot,
    MarketContextSnapshot,
    NewsItem,
    RegimeSnapshot,
    SymbolActivity,
    SymbolMover,
)
from kade.runtime.interaction import InteractionOrchestrator, InteractionRuntimeState
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import VoiceSessionState
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter
from kade.integrations.stt import WhisperSTTProvider
from kade.integrations.tts import KokoroTTSProvider
from kade.integrations.wakeword import PorcupineWakeWordDetector


def _cfg() -> dict[str, object]:
    return {
        "posture_thresholds": {"trend_favorable_confidence": 0.75, "volatile_event_macro_count": 2, "catalyst_heavy_earnings_count": 3},
        "catalyst_priorities": {"market_wide": 3, "sector": 2, "symbol": 2},
        "watchlist_weights": {
            "alignment": 2.0,
            "conflict_penalty": 2.0,
            "symbol_catalyst": 1.5,
            "mover": 1.0,
            "activity": 1.0,
            "regime_alignment_bonus": 1.0,
            "chop_mover_penalty": 1.0,
        },
        "output_limits": {"key_catalysts": 8, "earnings_today": 8, "movers_to_watch": 8, "most_active": 8, "watchlist_priorities": 12},
        "history_retention": 10,
    }


def _snapshot(*, regime: str = "trend", confidence: float = 0.81, macro_items: int = 1) -> MarketContextSnapshot:
    news = [
        NewsItem(
            timestamp="2026-01-01T12:30:00+00:00",
            source="test",
            headline=f"Macro headline {i}",
            summary="Macro risk",
            symbols=[],
            url=None,
            catalyst_type="macro",
            relevance_label="high",
        )
        for i in range(macro_items)
    ]
    news += [
        NewsItem(
            timestamp="2026-01-01T12:31:00+00:00",
            source="test",
            headline="NVDA product launch",
            summary="Symbol catalyst",
            symbols=["NVDA"],
            url=None,
            catalyst_type="product_company",
            relevance_label="high",
        )
    ]
    return MarketContextSnapshot(
        generated_at="2026-01-01T12:35:00+00:00",
        source="test",
        market_clock=MarketClockSnapshot(
            timestamp="2026-01-01T12:35:00+00:00",
            source="test",
            is_open=False,
            next_open=None,
            next_close=None,
            session_label="pre_market",
        ),
        market_calendar=[],
        regime=RegimeSnapshot(
            timestamp="2026-01-01T12:35:00+00:00",
            source="test",
            regime_label=regime,
            regime_confidence=confidence,
            reasons=["test"],
        ),
        key_news=news,
        top_movers=[
            SymbolMover(
                timestamp="2026-01-01T12:35:00+00:00",
                source="test",
                symbol="NVDA",
                move_pct=2.2,
                last_price=100.0,
                volume=1_000_000,
                direction="up",
                mover_type="gainer",
            ),
            SymbolMover(
                timestamp="2026-01-01T12:35:00+00:00",
                source="test",
                symbol="AMD",
                move_pct=1.8,
                last_price=90.0,
                volume=900_000,
                direction="up",
                mover_type="gainer",
            ),
        ],
        most_active=[
            SymbolActivity(timestamp="2026-01-01T12:35:00+00:00", source="test", symbol="NVDA", volume=2_000_000, trade_count=1000, last_price=100.0),
            SymbolActivity(timestamp="2026-01-01T12:35:00+00:00", source="test", symbol="TSLA", volume=2_200_000, trade_count=1200, last_price=200.0),
        ],
        earnings=[
            EarningsEvent(timestamp="2026-01-01T12:35:00+00:00", source="test", symbol="NVDA", event_date="2026-01-01", timing="after_close")
        ],
        cross_symbol_context={
            "NVDA": CrossSymbolContext(
                timestamp="2026-01-01T12:35:00+00:00",
                source="test",
                symbol="NVDA",
                benchmark_symbols=["QQQ", "SPY"],
                sector_proxy="SMH",
                alignment_label="aligned",
                reasons=["aligned"],
            ),
            "TSLA": CrossSymbolContext(
                timestamp="2026-01-01T12:35:00+00:00",
                source="test",
                symbol="TSLA",
                benchmark_symbols=["QQQ", "SPY"],
                sector_proxy=None,
                alignment_label="conflict",
                reasons=["conflict"],
            ),
        },
    )


def test_market_posture_and_repeatability() -> None:
    service = PremarketGameplanService(_cfg())
    snapshot = _snapshot(regime="trend", confidence=0.84, macro_items=1)
    first = service.refresh_daily_gameplan(snapshot=snapshot, watchlist=["NVDA", "TSLA"])
    second = service.refresh_daily_gameplan(snapshot=snapshot, watchlist=["NVDA", "TSLA"])

    assert first["market_posture"]["posture_label"] == "trend_favorable"
    assert first == second


def test_catalyst_prioritization_and_watchlist_ranking() -> None:
    service = PremarketGameplanService(_cfg())
    payload = service.refresh_daily_gameplan(snapshot=_snapshot(macro_items=2), watchlist=["NVDA", "TSLA", "AMD"])

    assert payload["market_posture"]["posture_label"] == "volatile_event"
    assert payload["key_catalysts"][0]["priority"] in {"priority_high", "priority_medium"}
    assert payload["watchlist_priorities"][0]["symbol"] == "NVDA"


def test_sparse_input_fallback_and_runtime_shape() -> None:
    service = PremarketGameplanService(_cfg())
    snapshot = _snapshot(regime="range", confidence=0.4, macro_items=0)
    snapshot.key_news = []
    snapshot.top_movers = []
    snapshot.most_active = []
    payload = service.refresh_daily_gameplan(snapshot=snapshot, watchlist=[])

    assert payload["summary"]["posture"] in {"chop_risk", "mixed"}
    assert isinstance(payload["agenda_notes"], list)
    assert "watchlist_priorities" in payload


def test_operator_console_premarket_gameplan_shape() -> None:
    app = create_app_status(
        premarket_gameplan_payload={
            "generated_at": "2026-01-01T12:35:00+00:00",
            "summary": {"headline": "Market posture is cautious trend."},
            "market_posture": {"posture_label": "cautious_trend"},
            "key_catalysts": [{"headline": "CPI"}],
            "earnings_today": [{"symbol": "NVDA"}],
            "movers_to_watch": [{"symbol": "NVDA"}],
            "watchlist_priorities": [{"symbol": "NVDA", "priority": "priority_high"}],
            "risks": [{"label": "event_risk"}],
            "opportunities": ["Trend continuation setups"],
        }
    )

    panel = app["operator_console"]["premarket_gameplan"]
    assert panel["summary"]["headline"]
    assert panel["watchlist_priorities"][0]["symbol"] == "NVDA"


def _interaction() -> InteractionOrchestrator:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    voice = VoiceOrchestrator(
        wakeword_detector=PorcupineWakeWordDetector({"keyword": "Kade", "enabled": False}),
        router=VoiceCommandRouter(handlers={"fallback": lambda mode, transcript: {"summary": transcript}}),
        formatter=SpokenResponseFormatter(),
        tts_provider=KokoroTTSProvider({"mock_synthesis": True, "artifact_dir": ".kade_storage/test_tts_gp"}),
        state=VoiceSessionState(wake_word="Kade"),
        enable_tts=False,
    )
    interaction = InteractionOrchestrator(
        voice_orchestrator=voice,
        stt_provider=WhisperSTTProvider({"enabled": False, "runtime_mode": "deterministic_text"}),
        state=state,
        premarket_gameplan_handler=lambda payload: {
            "summary": {"headline": "Market posture is mixed."},
            "market_posture": {"posture_label": "mixed"},
            "regime_label": "trend",
            "key_catalysts": [{"headline": "CPI"}],
            "watchlist_priorities": [{"symbol": "NVDA", "priority": "priority_high"}],
        },
    )
    return interaction


def test_timeline_event_generation_for_premarket_gameplan() -> None:
    interaction = _interaction()
    interaction.submit_premarket_gameplan_request({"watchlist": ["NVDA"]})

    events = interaction.timeline.snapshot()["events"]
    assert any(event["event_type"] == "premarket_gameplan_generated" for event in events)
    assert interaction.dashboard_payload()["premarket_gameplan"]["market_posture"]["posture_label"] == "mixed"
