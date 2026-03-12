"""Entrypoint for Kade local application."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from kade.brain import AdvisorReasoningEngine, ConversationMemory, SessionPlanTracker, StyleProfileManager
from kade.execution import PaperExecutionWorkflow
from kade.execution.models import ExecutionRejection
from kade.integrations.diagnostics import ProviderDiagnostics
from kade.integrations.providers import (
    build_market_data_provider,
    build_options_data_provider,
    build_stt_provider,
    build_tts_provider,
    build_wakeword_provider,
)
from kade.logging_utils import LogCategory, get_logger, log_event, setup_logging
from kade.market.market_loop import MarketStateLoop
from kade.options import OptionsSelectionPipeline, TradeIntent
from kade.runtime import (
    InteractionOrchestrator,
    InteractionRuntimeState,
    ReplayRuntime,
    RuntimePersistence,
    RuntimeTimeline,
    build_dashboard_state,
    build_voice_handlers,
    print_runtime_summary,
)
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import VoiceSessionState
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter
from kade.utils.time import utc_now_iso

CONFIG_DIR = Path(__file__).parent / "config"
LOGGER = get_logger(__name__)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def bootstrap_config() -> dict[str, dict]:
    config_names = [
        "tickers.yaml",
        "trading_rules.yaml",
        "radar_rules.yaml",
        "personality.yaml",
        "voice.yaml",
        "execution.yaml",
        "news.yaml",
        "market_state.yaml",
        "brain.yaml",
        "storage.yaml",
        "dashboard.yaml",
    ]
    loaded_configs: dict[str, dict] = {}
    for name in config_names:
        loaded_configs[name] = load_yaml(CONFIG_DIR / name)
        log_event(LOGGER, LogCategory.CONFIG_LOAD, "Config loaded", file=name)
    return loaded_configs


def main() -> None:
    setup_logging()
    log_event(LOGGER, LogCategory.APP_START, "Kade startup initiated")

    configs = bootstrap_config()
    tickers_config = configs["tickers.yaml"]
    market_state_config = configs["market_state.yaml"]
    brain_config = configs["brain.yaml"]
    storage_config = configs["storage.yaml"].get("storage", {})
    persistence = RuntimePersistence.from_config(storage_config, logger=LOGGER)

    memory = ConversationMemory(brain_config, logger=LOGGER, autosave=lambda: persistence.persist_memory(memory))
    plan_tracker = SessionPlanTracker(brain_config, logger=LOGGER, autosave=lambda: persistence.persist_plans(plan_tracker))
    style_profile = StyleProfileManager(brain_config)
    advisor = AdvisorReasoningEngine(brain_config, logger=LOGGER)

    radar_history, advisor_history, execution_history, session_state = persistence.restore_startup_state(memory, plan_tracker)
    session_state = persistence.apply_rollover(session_state)

    provider_runtime = configs["execution.yaml"].get("providers", {})
    market_data_provider = build_market_data_provider(provider_runtime)
    options_data_provider = build_options_data_provider(provider_runtime)

    log_event(
        LOGGER,
        LogCategory.APP_START,
        "Data providers selected",
        market_data_provider=market_data_provider.provider_name,
        options_data_provider=options_data_provider.provider_name,
    )

    market_loop = MarketStateLoop(
        market_client=market_data_provider,
        watchlist=tickers_config.get("watchlist", []),
        timeframes=tickers_config.get("timeframes", {}),
        bars_limit=market_state_config["market_loop"]["bars_limit"],
        mental_model_config=market_state_config["mental_model"],
        radar_config=configs["radar_rules.yaml"]["radar"],
    )

    run_loop = os.getenv("KADE_RUN_MARKET_LOOP", "0") == "1"
    if run_loop:
        poll_seconds = market_state_config["market_loop"]["poll_seconds"]
        log_event(LOGGER, LogCategory.APP_START, "Starting continuous market loop", poll_seconds=poll_seconds)
        market_loop.run_forever(poll_seconds=poll_seconds)
        return

    states, debug_values = market_loop.update_once()
    options_payload = {"by_symbol": {}}
    execution_payload = {"orders": [], "rejections": [], "debug": {}}

    for event in market_loop.latest_radar.get("events", []):
        radar_history.append({**event, "timestamp": utc_now_iso()})
    radar_history = persistence.persist_radar_history(radar_history)

    if os.getenv("KADE_RUN_PHASE4_DEMO", "1") == "1":
        radar_queue = market_loop.latest_radar.get("queue", [])
        target_symbol = radar_queue[0]["symbol"] if radar_queue else sorted(states)[0]
        target_state = states[target_symbol]
        direction = "short" if target_state.trend == "bearish" else "long"

        intent = TradeIntent(
            symbol=target_symbol,
            direction=direction,
            style="intraday_momentum",
            desired_position_size_usd=configs["trading_rules.yaml"]["positioning"]["default_position_size_usd"],
            max_hold_minutes=configs["trading_rules.yaml"]["positioning"]["max_hold_minutes"],
        )
        chain = options_data_provider.get_option_chain(target_symbol, target_state.last_price)
        options_pipeline = OptionsSelectionPipeline(configs["execution.yaml"]["execution"]["option_selection"])
        selected_plan = options_pipeline.build_plan(
            intent,
            contracts=chain,
            ticker_state=target_state,
            radar_context=market_loop.latest_radar.get("by_symbol", {}).get(target_symbol, {}),
        )
        plan = plan_tracker.create_plan(
            symbol=target_symbol,
            direction=direction,
            trigger_condition="VWAP break with QQQ alignment",
            target_exit_idea="Scale near momentum exhaustion",
            max_hold_minutes=intent.max_hold_minutes,
            invalidation_concept="Reclaim against setup direction",
        )

        memory.record_user_intent(f"Watching {target_symbol} if VWAP confirms", symbol=target_symbol)
        memory.add_structured_note("Seeded by radar top setup.", symbol=target_symbol, linked_plan_id=plan.plan_id)

        options_payload["by_symbol"][target_symbol] = {
            "candidates": [
                {
                    "option_symbol": c.contract.option_symbol,
                    "score": c.total_score,
                    "strike": c.contract.strike,
                    "dte": c.contract.days_to_expiration,
                    "spread_pct": round(c.spread_pct, 4),
                }
                for c in selected_plan.ranked_candidates[:5]
            ],
            "selected_plan": {
                "target_contracts": selected_plan.target_contracts,
                "estimated_cost": selected_plan.total_estimated_cost,
                "allocations": [a.__dict__ for a in selected_plan.allocations],
            },
        }

        workflow = PaperExecutionWorkflow(configs["execution.yaml"]["execution"])
        order_requests = workflow.build_order_requests(selected_plan)
        staged_results = [
            workflow.engine.stage_order(
                request,
                trades_today=int(session_state.get("trades_today", 0)),
                daily_realized_pnl=float(session_state.get("daily_realized_pnl", 0.0)),
                confirm=True,
            )
            for request in order_requests
        ]

        execution_payload = {
            "orders": [r.__dict__ for r in staged_results if not isinstance(r, ExecutionRejection)],
            "rejections": [r.failure.__dict__ for r in staged_results if isinstance(r, ExecutionRejection)],
            "debug": {
                "symbol": target_symbol,
                "intent": intent.__dict__,
                "order_preview": [workflow.engine.preview_order(req) for req in order_requests],
                "latest_lifecycle": [
                    r.lifecycle for r in staged_results if not isinstance(r, ExecutionRejection)
                ],
            },
        }

        for request in order_requests:
            execution_history.append(
                {
                    "event_type": "paper_order_request",
                    "timestamp": utc_now_iso(),
                    "symbol": request.symbol,
                    "option_symbol": request.option_symbol,
                    "contracts": request.contracts,
                    "limit_price": request.limit_price,
                }
            )
        for result in staged_results:
            if isinstance(result, ExecutionRejection):
                execution_history.append(
                    {
                        "event_type": "guardrail_failure",
                        "timestamp": utc_now_iso(),
                        "symbol": result.request.symbol,
                        "option_symbol": result.request.option_symbol,
                        "code": result.failure.code,
                        "reason": result.failure.reason,
                    }
                )
            else:
                execution_history.append(
                    {
                        "event_type": "paper_order_status",
                        "timestamp": utc_now_iso(),
                        "symbol": result.request.symbol,
                        "option_symbol": result.request.option_symbol,
                        "status": result.status,
                        "filled_contracts": result.filled_contracts,
                        "remaining_contracts": result.remaining_contracts,
                        "avg_fill_price": result.avg_fill_price,
                        "nudged_limit_price": result.nudged_limit_price,
                        "lifecycle": result.lifecycle,
                    }
                )
                if result.filled_contracts > 0:
                    session_state["trades_today"] = int(session_state.get("trades_today", 0)) + 1

        execution_history = persistence.persist_execution_history(execution_history)

        if execution_payload["orders"]:
            plan_tracker.update_status(plan.plan_id, "triggered", reason="paper workflow created staged orders")

    advisor_payload = {"by_symbol": {}, "top_radar": []}
    top_radar = market_loop.latest_radar.get("queue", [])[:3]
    for idea in top_radar:
        symbol = str(idea["symbol"])
        advice = advisor.build_advice(
            symbol=symbol,
            ticker_state=states[symbol],
            radar_context=market_loop.latest_radar.get("by_symbol", {}).get(symbol, {}),
            breadth_context=market_loop.latest_breadth,
            active_plans=plan_tracker.active_plans(),
            memory=memory,
            options_plan=options_payload.get("by_symbol", {}).get(symbol, {}).get("selected_plan"),
        )
        advice.summary = style_profile.apply_scaffold(advice.summary)
        memory.record_kade_response(advice.summary, symbol=symbol, stance=advice.stance)
        advisor_payload["by_symbol"][symbol] = {
            "stance": advice.stance,
            "summary": advice.summary,
            "supporting_reasons": advice.supporting_reasons,
            "cautionary_reasons": advice.cautionary_reasons,
            "suggested_action": advice.suggested_action,
            "linked_plan_id": advice.linked_plan_id,
            "debug": advice.debug,
        }
        advisor_payload["top_radar"].append({"symbol": symbol, "stance": advice.stance, "summary": advice.summary})
        advisor_history.append(
            {
                "timestamp": utc_now_iso(),
                "symbol": symbol,
                "stance": advice.stance,
                "summary": advice.summary,
                "linked_plan_id": advice.linked_plan_id,
                "debug": advice.debug,
            }
        )

    advisor_history = persistence.persist_advisor_history(advisor_history, session_state)

    voice_config = configs["voice.yaml"].get("voice", {})
    dashboard_cfg = configs["dashboard.yaml"].get("dashboard", {})
    voice_state = VoiceSessionState(
        listening_mode=str(voice_config.get("listening_mode", "always_on")),
        wake_word=str(voice_config.get("wake_word", "Kade")),
        current_mode=str(voice_config.get("response_mode_default", "advisor")),
        cooldown_ms=int(voice_config.get("cooldown_ms", 1000)),
        command_window_ms=int(voice_config.get("command_window_ms", 8000)),
        self_trigger_prevention=bool(voice_config.get("self_trigger_prevention", True)),
    )
    runtime_mode = str(voice_config.get("runtime_mode", "text_first"))
    interaction_state = InteractionRuntimeState(
        runtime_mode=runtime_mode,
        voice_runtime_enabled=bool(voice_config.get("voice_runtime_enabled", False)),
        text_command_input_enabled=bool(voice_config.get("text_command_input_enabled", True)),
        wakeword_enabled=bool(voice_config.get("wakeword_enabled", False)),
        stt_enabled=bool(voice_config.get("stt_enabled", False)),
        tts_enabled=bool(voice_config.get("tts_enabled", False)),
        command_history_limit=int(dict(dashboard_cfg.get("command_panel", {})).get("history_limit", 50)),
        execution_history_limit=int(dict(dashboard_cfg.get("execution_monitor", {})).get("retention", 50)),
        radar_top_signals_limit=int(dict(dashboard_cfg.get("radar_panel", {})).get("top_signals", 5)),
        provider_health_history_limit=int(dict(voice_config.get("provider_health", {})).get("history_limit", 20)),
    )
    voice_orchestrator = VoiceOrchestrator(
        wakeword_detector=build_wakeword_provider(voice_config),
        router=VoiceCommandRouter(
            handlers=build_voice_handlers(
                session_state=session_state,
                persist_session=lambda: persistence.persist_session(session_state),
                states=states,
                plan_active_count=lambda: len(plan_tracker.active_plans()),
                latest_radar=lambda: market_loop.latest_radar,
                latest_breadth=lambda: market_loop.latest_breadth,
                memory_snapshot=lambda limit: memory.snapshot(limit=limit),
                advisor_by_symbol=advisor_payload["by_symbol"],
            )
        ),
        formatter=SpokenResponseFormatter(),
        tts_provider=build_tts_provider(voice_config),
        state=voice_state,
        logger=LOGGER,
        enable_tts=interaction_state.tts_enabled,
    )
    interaction = InteractionOrchestrator(
        voice_orchestrator=voice_orchestrator,
        stt_provider=build_stt_provider(voice_config),
        state=interaction_state,
        logger=LOGGER,
        replay_runtime=ReplayRuntime(retention_limit=int(dict(voice_config.get("replay_debug", {})).get("retention_limit", 40))),
        timeline=RuntimeTimeline(retention=int(dict(dashboard_cfg.get("timeline", {})).get("retention", 200))),
    )

    diagnostics = ProviderDiagnostics(policy=str(provider_runtime.get("diagnostics_policy", "warn_on_degraded")), logger=LOGGER)
    provider_diagnostics = diagnostics.evaluate(
        {
            "market_data": market_data_provider.health_snapshot(active=True),
            "options_data": options_data_provider.health_snapshot(active=True),
            "wakeword": voice_orchestrator.wakeword_detector.health_snapshot(active=interaction_state.wakeword_enabled),
            "stt": interaction.stt_provider.health_snapshot(active=interaction_state.stt_enabled),
            "tts": voice_orchestrator.tts_provider.health_snapshot(active=interaction_state.tts_enabled),
        }
    )
    interaction.set_provider_diagnostics(provider_diagnostics)

    radar_signals = [
        {
            "symbol": item.get("symbol"),
            "setup": item.get("setup") or item.get("state"),
            "signal_type": item.get("state"),
            "confidence": item.get("confidence"),
            "timeframe": item.get("timeframe", "intraday"),
            "notes": item.get("why") or item.get("notes"),
            "supporting_indicators": item.get("indicators", []),
            "timestamp": utc_now_iso(),
        }
        for item in market_loop.latest_radar.get("queue", [])
    ]
    interaction.ingest_radar_signals(radar_signals)

    execution_events = [
        {
            "symbol": order.get("symbol"),
            "option_symbol": order.get("option_symbol"),
            "status": order.get("status"),
            "lifecycle_state": dict(order.get("lifecycle", {})).get("state"),
            "contracts": (order.get("filled_contracts", 0) or 0) + (order.get("remaining_contracts", 0) or 0),
            "filled_contracts": order.get("filled_contracts"),
            "avg_fill_price": order.get("avg_fill_price"),
            "timestamp": order.get("timestamp"),
            "fill_price": order.get("avg_fill_price"),
        }
        for order in execution_payload.get("orders", [])
    ]
    interaction.ingest_execution_events(execution_events)

    log_event(
        LOGGER,
        LogCategory.VOICE_EVENT,
        "Interaction runtime configured",
        runtime_mode=interaction_state.runtime_mode,
        voice_runtime_enabled=interaction_state.voice_runtime_enabled,
        wakeword_enabled=interaction_state.wakeword_enabled,
        stt_enabled=interaction_state.stt_enabled,
        tts_enabled=interaction_state.tts_enabled,
    )
    log_event(
        LOGGER,
        LogCategory.VOICE_EVENT,
        "Provider selected",
        wakeword_provider=voice_orchestrator.wakeword_detector.provider_name,
        stt_provider=interaction.stt_provider.provider_name,
        tts_provider=voice_orchestrator.tts_provider.provider_name,
    )

    default_text_command = os.getenv("KADE_TEXT_COMMAND", "status")
    if interaction_state.text_command_input_enabled:
        text_result = interaction.submit_text_command(default_text_command)
        print(f"Text intent: {text_result['intent']}")
        print(f"Text response: {text_result['formatted_response']}")

    if os.getenv("KADE_SIMULATE_VOICE", "0") == "1":
        voice_result = interaction.process_voice_sample(f"{voice_state.wake_word} status")
        if voice_result:
            print(f"Voice intent: {voice_result['intent']}")
            print(f"Voice response: {voice_result['formatted_response']}")

    session_state["interaction_runtime"] = {
        "runtime_mode": interaction_state.runtime_mode,
        "voice_runtime_enabled": interaction_state.voice_runtime_enabled,
        "text_command_input_enabled": interaction_state.text_command_input_enabled,
    }
    session_state["command_interface_mode"] = interaction_state.runtime_mode
    session_state["recent_command_history"] = interaction_state.recent_commands
    session_state["provider_health"] = interaction_state.provider_health
    session_state["provider_health_history"] = interaction_state.provider_health_history
    session_state["provider_diagnostics"] = provider_diagnostics
    session_state["provider_selection"] = {
        "market_data": market_data_provider.provider_name,
        "options_data": options_data_provider.provider_name,
        "wakeword": voice_orchestrator.wakeword_detector.provider_name,
        "stt": interaction.stt_provider.provider_name,
        "tts": voice_orchestrator.tts_provider.provider_name,
    }
    session_state["replay_debug"] = interaction.replay_runtime.snapshot()
    persistence.retain_recent_voice_events(session_state)
    persistence.retain_recent_commands(session_state)
    persistence.retain_provider_health_history(session_state)

    persistence.persist_memory(memory)
    persistence.persist_plans(plan_tracker)
    persistence.persist_session(session_state)

    persistence_meta = persistence.metadata_snapshot()
    history_payload = {
        "radar": radar_history,
        "advisor": advisor_history,
        "execution": execution_history,
    }
    dashboard_state = build_dashboard_state(
        states,
        debug_values,
        market_loop.latest_breadth,
        market_loop.latest_radar,
        options_payload,
        execution_payload,
        memory.snapshot(limit=10),
        plan_tracker.snapshot(),
        advisor_payload,
        style_profile.response_guidance(),
        {**interaction.dashboard_payload(), "provider_diagnostics": provider_diagnostics, "provider_selection": session_state.get("provider_selection", {})},
        persistence_meta,
        session_state,
        history_payload,
    )
    print_runtime_summary(dashboard_state, session_state, history_payload)


if __name__ == "__main__":
    main()
