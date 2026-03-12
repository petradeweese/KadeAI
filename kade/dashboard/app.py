"""Dashboard data wiring for Kade status visibility."""

from __future__ import annotations

from kade.market.structure import TickerState


def create_app_status(
    ticker_states: dict[str, TickerState] | None = None,
    debug_values: dict[str, dict[str, float | str | None]] | None = None,
    breadth_context: dict[str, float | str | None] | None = None,
    radar_payload: dict[str, object] | None = None,
    options_payload: dict[str, object] | None = None,
    execution_payload: dict[str, object] | None = None,
    memory_payload: dict[str, object] | None = None,
    plan_payload: dict[str, object] | None = None,
    advisor_payload: dict[str, object] | None = None,
    style_payload: dict[str, object] | None = None,
    voice_payload: dict[str, object] | None = None,
    persistence_payload: dict[str, object] | None = None,
    session_payload: dict[str, object] | None = None,
    history_payload: dict[str, object] | None = None,
    market_intelligence_payload: dict[str, object] | None = None,
    premarket_gameplan_payload: dict[str, object] | None = None,
) -> dict:
    ticker_states = ticker_states or {}
    debug_values = debug_values or {}
    breadth_context = breadth_context or {}
    radar_payload = radar_payload or {"queue": [], "ranked": [], "by_symbol": {}, "events": []}
    options_payload = options_payload or {"by_symbol": {}}
    execution_payload = execution_payload or {"orders": [], "rejections": [], "debug": {}}
    memory_payload = memory_payload or {"recent": [], "intents": [], "responses": [], "notes": []}
    plan_payload = plan_payload or {"active": [], "all": [], "events": []}
    advisor_payload = advisor_payload or {"by_symbol": {}, "top_radar": []}
    style_payload = style_payload or {}
    voice_payload = voice_payload or {}
    persistence_payload = persistence_payload or {}
    session_payload = session_payload or {}
    history_payload = history_payload or {"radar": [], "advisor": [], "execution": []}
    market_intelligence_payload = market_intelligence_payload or {}
    premarket_gameplan_payload = premarket_gameplan_payload or {}

    cards: list[dict] = []
    by_symbol = radar_payload.get("by_symbol", {})
    options_by_symbol = options_payload.get("by_symbol", {})
    advisor_by_symbol = advisor_payload.get("by_symbol", {})
    for symbol in sorted(ticker_states):
        state = ticker_states[symbol]
        cards.append(
            {
                "symbol": symbol,
                "last_price": state.last_price,
                "vwap": state.vwap,
                "trend": state.trend,
                "structure": state.structure,
                "momentum": state.momentum,
                "volume_state": state.volume_state,
                "qqq_confirmation": state.qqq_confirmation,
                "regime": state.regime,
                "trap_risk": state.trap_risk,
                "confidence_label": state.confidence_label,
                "confidence_reason": state.confidence_reason,
                "radar_state": by_symbol.get(symbol, {}).get("state", "no_setup"),
                "radar_rank": by_symbol.get(symbol, {}).get("rank"),
                "radar_debug": by_symbol.get(symbol, {}).get("debug", {}),
                "updated_at": state.updated_at.isoformat() if state.updated_at else None,
                "debug": debug_values.get(symbol, {}),
                "option_candidates": options_by_symbol.get(symbol, {}).get("candidates", [])[:3],
                "selected_option_plan": options_by_symbol.get(symbol, {}).get("selected_plan"),
                "advisor_stance": advisor_by_symbol.get(symbol, {}).get("stance"),
                "advisor_summary": advisor_by_symbol.get(symbol, {}).get("summary"),
                "advisor_debug": advisor_by_symbol.get(symbol, {}).get("debug", {}),
            }
        )

    voice_payload = voice_payload or {}
    provider_diag = voice_payload.get("provider_diagnostics", {})
    provider_selection = voice_payload.get("provider_selection", {})
    provider_map = dict(provider_diag.get("providers", {}))

    top_radar_signals = voice_payload.get("latest_radar_signals") or radar_payload.get("queue", [])[:5]
    latest_execution = (voice_payload.get("execution_monitor", {}).get("lifecycle_history") or execution_payload.get("orders", []))[-1:]

    def _panel(data: object, empty: dict[str, object]) -> dict[str, object]:
        if isinstance(data, dict) and data:
            return {"available": True, **empty, **data}
        return {"available": False, **empty}

    radar_quality = {
        "top_quality": [s for s in top_radar_signals if float(s.get("confidence", 0.0)) >= 70],
        "weak_or_noisy": [s for s in top_radar_signals if float(s.get("confidence", 0.0)) < 55],
        "caution_heavy": [s for s in top_radar_signals if len(list(s.get("cautionary_reasons", []))) >= 2 or s.get("trap_risk") == "high"],
    }

    return {
        "status": "running",
        "card_count": len(cards),
        "breadth_context": breadth_context,
        "style_profile": style_payload,
        "memory": memory_payload,
        "plans": plan_payload,
        "advisor": advisor_payload,
        "radar": {
            "queue": radar_payload.get("queue", []),
            "top_ranked": radar_payload.get("ranked", [])[:3],
            "events": radar_payload.get("events", []),
        },
        "execution": execution_payload,
        "voice": voice_payload,
        "operator_console": {
            "runtime": {
                "runtime_mode": voice_payload.get("runtime_mode"),
                "interaction_mode": voice_payload.get("runtime_mode"),
                "command_input_mode": voice_payload.get("command_input_mode"),
            },
            "providers": {
                "provider_diagnostics": provider_diag,
                "market_data_provider": {
                    "provider": provider_selection.get("market_data"),
                    **dict(provider_map.get("market_data", {})),
                    "mode": "mock" if "mock" in str(provider_selection.get("market_data", "")) else "real",
                },
                "options_data_provider": {
                    "provider": provider_selection.get("options_data"),
                    **dict(provider_map.get("options_data", {})),
                    "mode": "mock" if "mock" in str(provider_selection.get("options_data", "")) else "real",
                },
                "stt_provider": {"provider": provider_selection.get("stt"), **dict(provider_map.get("stt", {}))},
                "tts_provider": {"provider": provider_selection.get("tts"), **dict(provider_map.get("tts", {}))},
                "wakeword_provider": {"provider": provider_selection.get("wakeword"), **dict(provider_map.get("wakeword", {}))},
            },
            "radar": {"top_signals": top_radar_signals[:5], "quality_buckets": radar_quality},
            "execution": {"latest_lifecycle": latest_execution},
            "session": {
                "trades_today": session_payload.get("trades_today", 0),
                "daily_realized_pnl": session_payload.get("daily_realized_pnl", 0.0),
                "done_for_day": session_payload.get("done_for_day", False),
                "emergency_shutdown": session_payload.get("emergency_shutdown", False),
            },
            "timeline": voice_payload.get("timeline", {"retention": 0, "events": []}),
            "target_move_board": _panel(voice_payload.get("target_move_board"), {"candidate_count": 0}),
            "trade_idea_opinion": _panel(voice_payload.get("trade_idea_opinion"), {"symbol": None, "summary": ""}),
            "trade_plan": _panel(voice_payload.get("trade_plan"), {"plan_id": None, "status": "unknown"}),
            "trade_plan_tracking": _panel(voice_payload.get("trade_plan_tracking"), {"plan_id": None, "status_after": "unknown"}),
            "trade_review": _panel(voice_payload.get("trade_review"), {"latest_review": {}, "metrics_summary": {}, "history": []}),
            "backtesting": _panel(voice_payload.get("backtesting"), {"latest_run_summary": {}, "recent_evaluations": {}}),
            "historical_data": _panel(voice_payload.get("historical_data"), {"last_download": {}, "cache_status": {}, "recent_downloads": [], "index_status": {}}),

            "premarket_gameplan": {
                "summary": dict(premarket_gameplan_payload.get("summary", {})),
                "market_posture": dict(premarket_gameplan_payload.get("market_posture", {})),
                "key_catalysts": list(premarket_gameplan_payload.get("key_catalysts", []))[:5],
                "earnings_today": list(premarket_gameplan_payload.get("earnings_today", []))[:5],
                "movers_to_watch": list(premarket_gameplan_payload.get("movers_to_watch", []))[:5],
                "watchlist_priorities": list(premarket_gameplan_payload.get("watchlist_priorities", []))[:8],
                "risks": list(premarket_gameplan_payload.get("risks", []))[:5],
                "opportunities": list(premarket_gameplan_payload.get("opportunities", []))[:5],
                "generated_at": premarket_gameplan_payload.get("generated_at"),
            },
            "market_intelligence": {
                "market_clock": dict(market_intelligence_payload.get("market_clock", {})),
                "market_calendar": list(market_intelligence_payload.get("market_calendar", [])),
                "regime": dict(market_intelligence_payload.get("regime", {})),
                "key_news": list(market_intelligence_payload.get("key_news", []))[:5],
                "top_movers": list(market_intelligence_payload.get("top_movers", []))[:5],
                "most_active": list(market_intelligence_payload.get("most_active", []))[:5],
                "cross_symbol_context": dict(market_intelligence_payload.get("cross_symbol_context", {})),
                "generated_at": market_intelligence_payload.get("generated_at"),
            },
        },
        "session": session_payload,
        "history": history_payload,
        "persistence": persistence_payload,
        "ticker_cards": cards,
    }
