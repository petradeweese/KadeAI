from datetime import datetime, timedelta, timezone

from kade.dashboard.app import create_app_status
from kade.market.structure import Bar, TickerState
from kade.runtime.interaction import InteractionRuntimeState
from kade.tests.test_phase8_interaction import _interaction
from kade.visuals import VisualExplainabilityRequest, VisualExplainabilityService


def _bars(symbol: str = "NVDA", count: int = 120) -> list[Bar]:
    start = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    out: list[Bar] = []
    px = 200.0
    for i in range(count):
        px += 0.05 if i % 2 == 0 else -0.02
        out.append(
            Bar(
                symbol=symbol,
                timestamp=start + timedelta(minutes=i),
                open=px - 0.1,
                high=px + 0.2,
                low=px - 0.2,
                close=px,
                volume=1000 + i,
            )
        )
    return out


def _service() -> VisualExplainabilityService:
    return VisualExplainabilityService(
        {
            "default_timeframes": ["1m", "5m", "15m"],
            "bar_window_sizes": {"1m": 40, "5m": 30, "15m": 20},
            "overlays": {"vwap": True, "trend_guide": True, "plan_lines": True, "tracking_markers": True},
            "history_retention": 20,
        }
    )


def test_visual_snapshot_is_deterministic_for_same_inputs() -> None:
    svc = _service()
    req = VisualExplainabilityRequest(symbol="NVDA", view_type="opinion", timeframes=("1m", "5m", "15m"))
    state = TickerState(symbol="NVDA", vwap=199.5, trend="down")
    first = svc.build_visual_explanation(
        request=req,
        bars_1m=_bars(),
        state=state,
        opinion={"stance": "agree", "summary": "context aligned", "market_alignment": "aligned", "qqq_alignment": "aligned"},
        trade_plan={},
        tracking={},
        gameplan={},
        market_intelligence={"regime": {"regime_label": "risk_off", "regime_confidence": "high", "reasons": ["QQQ below VWAP"]}},
        review={},
    )
    second = svc.build_visual_explanation(
        request=req,
        bars_1m=_bars(),
        state=state,
        opinion={"stance": "agree", "summary": "context aligned", "market_alignment": "aligned", "qqq_alignment": "aligned"},
        trade_plan={},
        tracking={},
        gameplan={},
        market_intelligence={"regime": {"regime_label": "risk_off", "regime_confidence": "high", "reasons": ["QQQ below VWAP"]}},
        review={},
    )

    assert [len(chart["bars"]) for chart in first["charts"]] == [40, 24, 8]
    assert [chart["timeframe"] for chart in first["charts"]] == ["1m", "5m", "15m"]
    assert first["debug"]["bars_input"] == second["debug"]["bars_input"]
    assert first["charts"][1]["bars"] == second["charts"][1]["bars"]


def test_plan_and_tracking_overlays_are_generated() -> None:
    svc = _service()
    snapshot = svc.build_visual_explanation(
        request=VisualExplainabilityRequest(symbol="NVDA", view_type="tracking", timeframes=("5m",)),
        bars_1m=_bars(),
        state=TickerState(symbol="NVDA", vwap=200.1, trend="up"),
        opinion={},
        trade_plan={
            "entry_plan": {"trigger_condition": "Break above 201.25"},
            "invalidation_plan": {"invalidation_condition": "Fail back below 199.8"},
            "target_plan": {"primary_target": "202.5", "secondary_target": "204.0"},
        },
        tracking={"status_after": "stale", "trigger_state": "ready", "invalidation_state": "safe", "staleness_state": "stale", "summary": "stale"},
        gameplan={},
        market_intelligence={"regime": {}},
        review={},
    )
    overlay_types = [item["overlay_type"] for item in snapshot["charts"][0]["overlays"]]

    assert "trigger_line" in overlay_types
    assert "invalidation_line" in overlay_types
    assert overlay_types.count("target_line") == 2
    assert "state_marker" in overlay_types


def test_missing_bars_fallback_annotations_present() -> None:
    svc = _service()
    snapshot = svc.build_visual_explanation(
        request=VisualExplainabilityRequest(symbol="NVDA", view_type="plan", timeframes=("1m", "5m")),
        bars_1m=[],
        state=None,
        opinion={},
        trade_plan={},
        tracking={},
        gameplan={},
        market_intelligence={"regime": {}},
        review={},
    )

    assert snapshot["charts"][0]["bars"] == []
    assert snapshot["charts"][0]["annotations"][0]["type"] == "warning"


def test_operator_console_contains_visual_explainability_shape() -> None:
    payload = create_app_status(
        voice_payload={
            "visual_explainability": {
                "latest": {"symbol": "NVDA", "view_type": "plan", "charts": [{"timeframe": "5m", "bars": [], "overlays": []}], "side_panels": [], "generated_at": "2026-01-01T00:00:00+00:00"},
                "history": [{"symbol": "NVDA"}],
            }
        }
    )
    panel = payload["operator_console"]["visual_explainability"]

    assert panel["active_symbol"] == "NVDA"
    assert panel["active_view"] == "plan"
    assert panel["history"][0]["symbol"] == "NVDA"


def test_runtime_visual_request_emits_timeline_and_updates_payload() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    interaction = _interaction(state)
    interaction.visual_explanation_handler = lambda payload: {
        "symbol": str(payload.get("symbol", "NVDA")),
        "view_type": str(payload.get("view_type", "plan")),
        "charts": [{"timeframe": "5m", "bars": [{"close": 1}], "overlays": [{"overlay_type": "vwap_line"}]}],
        "side_panels": [],
        "generated_at": "2026-01-01T00:00:00+00:00",
    }

    response = interaction.submit_visual_explanation_request({"symbol": "NVDA", "view_type": "plan"})
    timeline_events = [event["event_type"] for event in interaction.timeline.snapshot()["events"]]
    payload = interaction.dashboard_payload()

    assert response["intent"] == "visual_explanation"
    assert "visual_explanation_generated" in timeline_events
    assert "chart_context_changed" in timeline_events
    assert payload["visual_explainability"]["latest"]["symbol"] == "NVDA"


def test_operator_backend_chart_overlays_use_stable_shape() -> None:
    from kade.ui.api import OperatorBackend

    backend = OperatorBackend(llm_enabled=False)
    backend.chat("Should I consider a put on NVDA within an hour?")
    backend.command("trade_plan symbol=NVDA")
    chart = backend.chart_data(symbol="NVDA", timeframe="5m")

    assert chart["symbol"] == "NVDA"
    assert chart["timeframe"] == "5m"
    assert all("type" in overlay and "label" in overlay and "source" in overlay for overlay in chart["overlays"])
    assert {item["type"] for item in chart["overlays"]}.issuperset({"entry", "invalidation", "target", "vwap"})


def test_operator_backend_chart_fallback_when_provider_unavailable() -> None:
    from kade.ui.api import OperatorBackend

    class _BrokenProvider:
        provider_name = "broken"

        def get_bars(self, symbol: str, timeframe: str, limit: int = 200):
            return []

    backend = OperatorBackend(llm_enabled=False)
    backend._historical_provider = _BrokenProvider()
    payload = backend.chart_data(symbol="NVDA", timeframe="5m")

    assert payload["fallback"]["available"] is False
    assert payload["fallback"]["reason"] == "bars_unavailable"
    assert payload["bars"] == []


def test_horizon_minutes_biases_initial_chart_timeframe() -> None:
    from kade.ui.api import OperatorBackend

    backend = OperatorBackend(llm_enabled=False)
    result = backend.chat("Should I consider a put on NVDA within an hour?")

    assert result["layout_state"]["active_timeframe"] == "5m"
