"""Entrypoint for Kade local application."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from kade.brain import AdvisorReasoningEngine, ConversationMemory, SessionPlanTracker, StyleProfileManager, TradeIdeaOpinionEngine, TradeIdeaOpinionRequest
from kade.planning import TradePlanBuilder, TradePlanContext
from kade.data.history import HistoryService
from kade.execution import PaperExecutionWorkflow
from kade.execution.models import ExecutionRejection
from kade.integrations.diagnostics import ProviderDiagnostics
from kade.integrations.marketdata import AlpacaMarketDataProvider
from kade.integrations.options_data import AlpacaOptionsDataProvider
from kade.integrations.providers import (
    build_llm_provider,
    build_market_data_provider,
    build_options_data_provider,
    resolve_runtime_provider_routes,
    build_stt_provider,
    build_tts_provider,
    build_wakeword_provider,
)
from kade.logging_utils import LogCategory, get_logger, log_event, setup_logging
from kade.market.market_loop import MarketStateLoop
from kade.market.intelligence import MarketIntelligenceService
from kade.gameplan import PremarketGameplanService
from kade.options import OptionsSelectionPipeline, TargetMoveScenarioBoard, TargetMoveScenarioRequest, TradeIntent
from kade.runtime import (
    AlpacaSmokeTester,
    InteractionOrchestrator,
    InteractionRuntimeState,
    NarrativeSummaryService,
    ReplayRuntime,
    RuntimePersistence,
    RuntimeTimeline,
    build_dashboard_state,
    build_voice_handlers,
    print_runtime_summary,
)
from kade.runtime.configuration import apply_runtime_env_overrides
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import VoiceSessionState
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter
from kade.tracking import TradePlanMonitor, TradePlanTrackingContext, to_payload as tracking_payload
from kade.utils.time import utc_now_iso
from kade.review import TradeReviewAnalyzer, TradeReviewContext, ReviewMetricsAggregator, review_to_payload, metrics_to_payload
from kade.visuals import VisualExplainabilityRequest, VisualExplainabilityService
from kade.strategy import StrategyIntelligenceService

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
        "backtesting.yaml",
        "history.yaml",
        "planning.yaml",
        "tracking.yaml",
        "review.yaml",
        "market_intelligence.yaml",
        "gameplan.yaml",
        "visuals.yaml",
        "strategy.yaml",
        "llm.yaml",
    ]
    loaded_configs: dict[str, dict] = {}
    for name in config_names:
        loaded_configs[name] = load_yaml(CONFIG_DIR / name)
        log_event(LOGGER, LogCategory.CONFIG_LOAD, "Config loaded", file=name)
    return apply_runtime_env_overrides(loaded_configs)


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
    provider_routes = resolve_runtime_provider_routes(provider_runtime)
    runtime_market_data_provider = build_market_data_provider(provider_runtime, route_key="runtime_market_loop_provider")
    historical_data_provider = build_market_data_provider(provider_runtime, route_key="historical_data_provider")
    options_data_provider = build_options_data_provider(provider_runtime, route_key="options_runtime_provider")
    alpaca_market_backend = AlpacaMarketDataProvider(dict(dict(provider_runtime.get("market_data_backends", {})).get("alpaca", {})))
    alpaca_options_backend = AlpacaOptionsDataProvider(dict(dict(provider_runtime.get("options_data_backends", {})).get("alpaca", {})))
    llm_cfg = dict(configs["llm.yaml"].get("llm", {}))
    llm_provider = build_llm_provider(llm_cfg)
    narrative_service = NarrativeSummaryService(llm_provider, dict(llm_cfg.get("usage", {})))

    history_service = HistoryService.from_config(
        provider=historical_data_provider,
        logger=LOGGER,
        history_config=configs["history.yaml"].get("history", {}),
        mental_model_config=market_state_config["mental_model"],
    )
    history_runtime = persistence.load_history_runtime()

    history_symbols = [symbol.strip().upper() for symbol in os.getenv("KADE_HISTORY_DOWNLOAD_SYMBOLS", "").split(",") if symbol.strip()]
    if history_symbols:
        days = int(os.getenv("KADE_HISTORY_DAYS", "30"))
        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(days=days)
        download_summary = history_service.download(history_symbols, start=start_ts, end=end_ts)
        cache_status = history_service.cache_status(history_symbols, start=start_ts, end=end_ts)
        history_runtime = persistence.persist_history_runtime(
            {
                "last_download": download_summary.__dict__,
                "cache_status": cache_status.__dict__,
                "recent_downloads": list(history_runtime.get("recent_downloads", [])) + [download_summary.__dict__],
                "index_status": dict(cache_status.index_status),
            }
        )

    log_event(
        LOGGER,
        LogCategory.APP_START,
        "Data providers selected",
        runtime_market_loop_provider=runtime_market_data_provider.provider_name,
        historical_data_provider=historical_data_provider.provider_name,
        market_intelligence_provider=provider_routes.get("market_intelligence_provider", "alpaca"),
        options_runtime_provider=options_data_provider.provider_name,
    )

    market_loop = MarketStateLoop(
        market_client=runtime_market_data_provider,
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
    scenario_engine = TargetMoveScenarioBoard(configs["execution.yaml"]["execution"]["option_scenarios"])
    opinion_engine = TradeIdeaOpinionEngine(brain_config.get("trade_idea_opinion", {}), logger=LOGGER)
    planning_cfg = dict(configs["planning.yaml"].get("planning", {}))
    tracking_cfg = dict(configs["tracking.yaml"].get("tracking", {}))
    review_cfg = dict(configs["review.yaml"].get("review", {}))
    market_intelligence_cfg = dict(configs["market_intelligence.yaml"].get("market_intelligence", {}))
    market_intelligence_alpaca_cfg = dict(market_intelligence_cfg.get("alpaca", {}))
    if provider_routes.get("market_intelligence_provider", "alpaca") != "alpaca":
        market_intelligence_alpaca_cfg["enabled"] = False
    market_intelligence_cfg["alpaca"] = market_intelligence_alpaca_cfg
    gameplan_cfg = dict(configs["gameplan.yaml"].get("gameplan", {}))
    visuals_cfg = dict(configs["visuals.yaml"].get("visuals", {}))
    strategy_cfg = dict(configs["strategy.yaml"].get("strategy", {}))
    market_intelligence_service = MarketIntelligenceService(market_intelligence_cfg)
    gameplan_service = PremarketGameplanService(gameplan_cfg)
    visual_service = VisualExplainabilityService(visuals_cfg)
    strategy_service = StrategyIntelligenceService(strategy_cfg)
    market_intelligence_snapshot = market_intelligence_service.build_snapshot(
        ticker_states=states,
        latest_breadth=market_loop.latest_breadth,
        watchlist=tickers_config.get("watchlist", []),
    )
    market_intelligence_payload = market_intelligence_snapshot.to_payload()
    market_intelligence_summary = narrative_service.summarize("market_intelligence", market_intelligence_payload)
    session_state["latest_market_intelligence"] = market_intelligence_payload
    retention = int(market_intelligence_cfg.get("history_retention", 25))
    history = list(session_state.get("market_intelligence_history", [])) + [market_intelligence_payload]
    session_state["market_intelligence_history"] = history[-retention:] if retention > 0 else []
    gameplan_payload = gameplan_service.refresh_daily_gameplan(
        snapshot=market_intelligence_snapshot,
        watchlist=list(tickers_config.get("watchlist", [])),
        ticker_states=states,
    )
    premarket_summary = narrative_service.summarize("premarket_gameplan", gameplan_payload)
    session_state["latest_premarket_gameplan"] = gameplan_payload
    gameplan_retention = int(gameplan_cfg.get("history_retention", 10))
    gameplan_history = list(session_state.get("premarket_gameplan_history", [])) + [gameplan_payload]
    session_state["premarket_gameplan_history"] = gameplan_history[-gameplan_retention:] if gameplan_retention > 0 else []

    trade_plan_builder = TradePlanBuilder(planning_cfg)
    trade_plan_monitor = TradePlanMonitor(plan_tracker, tracking_cfg)
    trade_plan_tracking_history: list[dict[str, object]] = list(session_state.get("trade_plan_tracking_history", []))
    review_analyzer = TradeReviewAnalyzer(review_cfg)
    review_metrics = ReviewMetricsAggregator(review_cfg)
    trade_review_history: list[dict[str, object]] = list(session_state.get("trade_review_history", []))
    visual_history: list[dict[str, object]] = list(session_state.get("visual_explanation_history", []))
    strategy_runtime = persistence.load_strategy_runtime()
    strategy_history: list[dict[str, object]] = list(strategy_runtime.get("strategy_history", []))
    latest_strategy_snapshot = dict(strategy_runtime.get("latest_strategy_snapshot", {}))
    strategy_summary = narrative_service.summarize("strategy_intelligence", latest_strategy_snapshot) if latest_strategy_snapshot else {}
    latest_visual_snapshot = dict(session_state.get("latest_visual_explanation", {}))
    visual_summary = narrative_service.summarize("visual_explainability", latest_visual_snapshot) if latest_visual_snapshot else {}


    def build_trade_idea_opinion(payload: dict[str, object]) -> dict[str, object]:
        symbol = str(payload.get("symbol", "")).upper()
        state = states.get(symbol)
        if state is None:
            return {
                "symbol": symbol,
                "direction": str(payload.get("direction", "unknown")),
                "current_price": float(payload.get("current_price") or payload.get("current") or 0.0),
                "target_price": float(payload.get("target_price") or payload.get("target") or 0.0),
                "time_horizon_minutes": int(payload.get("time_horizon_minutes") or payload.get("minutes") or 30),
                "stance": "pass",
                "confidence_label": "very_low",
                "target_plausibility": "unclear",
                "market_alignment": "mixed",
                "qqq_alignment": "mixed",
                "breadth_alignment": "mixed",
                "regime_fit": "unclear",
                "trap_risk": "unknown",
                "summary": f"No current ticker state available for {symbol}.",
                "supporting_reasons": [],
                "cautionary_reasons": ["Ticker is not in the active runtime state map."],
                "suggested_next_step": "Load symbol into watchlist and reassess after market state refresh.",
                "timestamp": utc_now_iso(),
                "debug": {"reason": "missing_symbol_state"},
            }
        request = TradeIdeaOpinionRequest(
            symbol=symbol,
            direction=str(payload.get("direction", "")),
            current_price=float(payload.get("current_price") or payload.get("current") or state.last_price or 0.0),
            target_price=float(payload.get("target_price") or payload.get("target") or state.last_price or 0.0),
            time_horizon_minutes=int(payload.get("time_horizon_minutes") or payload.get("minutes") or 30),
            user_context=str(payload.get("user_context")) if payload.get("user_context") else None,
            profile=str(payload.get("profile")) if payload.get("profile") else None,
        )
        opinion = opinion_engine.evaluate(
            request=request,
            ticker_state=state,
            radar_context=market_loop.latest_radar.get("by_symbol", {}).get(symbol, {}),
            breadth_context=market_loop.latest_breadth,
        )
        return opinion.as_dict()

    def build_target_move_board(payload: dict[str, object]) -> dict[str, object]:
        symbol = str(payload.get("symbol", "")).upper()
        state = states.get(symbol)
        current_price = float(payload.get("current_price") or payload.get("current") or (state.last_price if state else 0.0))
        allowed_dtes = payload.get("allowed_dtes") or configs["execution.yaml"]["execution"]["option_scenarios"].get("default_allowed_dtes", [0, 1, 2])
        request = TargetMoveScenarioRequest(
            symbol=symbol,
            direction=str(payload.get("direction", "call")),
            current_price=current_price,
            target_price=float(payload.get("target_price") or payload.get("target") or current_price),
            time_horizon_minutes=int(payload.get("time_horizon_minutes") or payload.get("minutes") or 30),
            budget=float(payload.get("budget") or 0.0),
            allowed_dtes=tuple(int(d) for d in allowed_dtes),
            profile=str(payload.get("profile")) if payload.get("profile") else None,
        )
        chain = options_data_provider.get_option_chain(symbol, current_price)
        return scenario_engine.generate(request, chain)


    def build_trade_plan(payload: dict[str, object]) -> dict[str, object]:
        symbol = str(payload.get("symbol", "")).upper()
        state = states.get(symbol)
        if state is None:
            return {
                "plan_id": f"plan-{symbol}-missing",
                "symbol": symbol,
                "direction": str(payload.get("direction", "unknown")),
                "status": "watching",
                "risk_posture": "pass",
                "entry_plan": {"trigger_condition": "No state loaded"},
                "invalidation_plan": {"invalidation_condition": "Missing ticker state"},
                "target_plan": {},
                "hold_plan": {"max_hold_minutes": 0},
                "execution_checklist": ["Load symbol state before planning."],
                "generated_at": utc_now_iso(),
                "debug": {"reason": "missing_symbol_state"},
            }

        opinion_payload = payload.get("trade_idea_opinion")
        if not isinstance(opinion_payload, dict):
            latest = interaction_state.latest_trade_idea_opinion
            opinion_payload = latest if str(latest.get("symbol", "")).upper() == symbol else None

        board_payload = payload.get("target_move_board")
        if not isinstance(board_payload, dict):
            latest_board = interaction_state.latest_target_move_board
            board_payload = latest_board if str(dict(latest_board.get("request", {})).get("symbol", "")).upper() == symbol else None

        context = TradePlanContext(
            symbol=symbol,
            direction=str(payload.get("direction", "")),
            ticker_state=state,
            radar_context=market_loop.latest_radar.get("by_symbol", {}).get(symbol, {}),
            breadth_context=market_loop.latest_breadth,
            source_mode=str(payload.get("source_mode", "operator_request")),
            trade_idea_opinion=opinion_payload,
            target_move_board=board_payload,
            user_request_context=dict(payload),
        )
        decision = trade_plan_builder.build(context)
        plan = plan_tracker.create_plan(
            symbol=symbol,
            direction=str(payload.get("direction", "")) or decision.debug.get("direction", "unknown"),
            trigger_condition=decision.entry_plan.trigger_condition,
            target_exit_idea=decision.target_plan.primary_target,
            max_hold_minutes=decision.hold_plan.max_hold_minutes,
            invalidation_concept=decision.invalidation_plan.invalidation_condition,
            status="ready" if decision.risk_posture in {"full", "reduced"} else "watching",
            notes=list(decision.notes),
            source_mode=context.source_mode,
            stance=decision.stance,
            confidence_label=decision.confidence_label,
            target_plausibility=decision.target_plausibility,
            market_alignment=decision.market_alignment,
            regime_fit=decision.regime_fit,
            trap_risk=decision.trap_risk,
            entry_plan={
                "entry_style": decision.entry_plan.entry_style,
                "trigger_condition": decision.entry_plan.trigger_condition,
                "confirmation_signals": decision.entry_plan.confirmation_signals,
                "avoid_if": decision.entry_plan.avoid_if,
            },
            invalidation_plan={
                "invalidation_condition": decision.invalidation_plan.invalidation_condition,
                "soft_invalidation": decision.invalidation_plan.soft_invalidation,
                "hard_invalidation": decision.invalidation_plan.hard_invalidation,
            },
            target_plan={
                "primary_target": decision.target_plan.primary_target,
                "secondary_target": decision.target_plan.secondary_target,
                "scale_out_guidance": decision.target_plan.scale_out_guidance,
            },
            hold_plan={
                "max_hold_minutes": decision.hold_plan.max_hold_minutes,
                "expected_time_window": decision.hold_plan.expected_time_window,
                "stale_trade_rule": decision.hold_plan.stale_trade_rule,
            },
            risk_posture=decision.risk_posture,
            execution_checklist=list(decision.execution_checklist),
            linked_target_move_board=dict(decision.linked_target_move_board),
            linked_trade_idea_opinion=dict(decision.linked_trade_idea_opinion),
            debug=dict(decision.debug),
        )
        return plan_tracker._serialize(plan)




    def evaluate_trade_plan_tracking(payload: dict[str, object]) -> dict[str, object]:
        plan_id = str(payload.get("plan_id", "")).strip()
        symbol = str(payload.get("symbol", "")).upper()
        plan = plan_tracker.plans.get(plan_id)
        if plan is None and symbol:
            plans = plan_tracker.plans_for_symbol(symbol)
            plan = plans[0] if plans else None
        if plan is None:
            return {"plan_id": plan_id, "symbol": symbol, "summary": "No matching plan found.", "debug": {"reason": "missing_plan"}}

        state = states.get(plan.symbol)
        if state is None:
            return {"plan_id": plan.plan_id, "symbol": plan.symbol, "summary": "No current symbol state loaded.", "debug": {"reason": "missing_symbol_state"}}

        context = TradePlanTrackingContext(
            plan=plan,
            ticker_state=state,
            radar_context=dict(payload.get("radar_context", market_loop.latest_radar.get("by_symbol", {}).get(plan.symbol, {}))),
            breadth_context=dict(payload.get("breadth_context", market_loop.latest_breadth)),
            elapsed_minutes=int(payload["elapsed_minutes"]) if payload.get("elapsed_minutes") is not None else None,
            execution_state=str(payload.get("execution_state")) if payload.get("execution_state") is not None else None,
        )
        snapshot = trade_plan_monitor.evaluate(context, apply_transition=bool(payload.get("apply_transition", True)))
        tracking = tracking_payload(snapshot)
        trade_plan_tracking_history.append(tracking)
        limit = int(tracking_cfg.get("history_limit", 40))
        del trade_plan_tracking_history[:-limit]
        session_state["trade_plan_tracking_history"] = trade_plan_tracking_history
        session_state["latest_trade_plan_tracking"] = tracking
        persistence.persist_session(session_state)
        return tracking

    def review_trade_plan(payload: dict[str, object]) -> dict[str, object]:
        plan_id = str(payload.get("plan_id", "")).strip()
        symbol = str(payload.get("symbol", "")).upper()
        plan = plan_tracker.plans.get(plan_id)
        if plan is None and symbol:
            plans = plan_tracker.plans_for_symbol(symbol)
            plan = plans[0] if plans else None
        if plan is None:
            latest = {
                "plan_id": plan_id,
                "symbol": symbol,
                "review_label": "unknown",
                "discipline_label": "unknown",
                "outcome_label": "unknown",
                "summary": "No matching plan found for review.",
                "strengths": [],
                "mistakes": ["Missing plan context."],
                "lessons": ["Review requires a persisted plan."],
                "reviewed_at": utc_now_iso(),
            }
            metrics_payload = metrics_to_payload(review_metrics.build_snapshot(trade_review_history), compact=True)
            return {"latest_review": latest, "metrics_summary": metrics_payload}

        snapshots = [item for item in trade_plan_tracking_history if str(item.get("plan_id")) == plan.plan_id]
        context = TradeReviewContext(
            plan=plan_tracker._serialize(plan),
            tracking_snapshots=snapshots,
            final_status=str(payload.get("final_status")) if payload.get("final_status") is not None else None,
            execution_state=dict(payload.get("execution_state", {})) if isinstance(payload.get("execution_state"), dict) else None,
            exit_reason=str(payload.get("exit_reason")) if payload.get("exit_reason") is not None else None,
            realized_outcome=dict(payload.get("realized_outcome", {})) if isinstance(payload.get("realized_outcome"), dict) else None,
            notes=str(payload.get("notes")) if payload.get("notes") is not None else None,
        )
        result = review_analyzer.review(context)
        latest_review = review_to_payload(result)
        latest_review["plan"] = plan_tracker._serialize(plan)
        trade_review_history.append(latest_review)
        limit = int(review_cfg.get("history_limit", 120))
        del trade_review_history[:-limit]
        metrics_snapshot = review_metrics.build_snapshot(trade_review_history)
        metrics_payload = metrics_to_payload(metrics_snapshot, compact=True)

        session_state["trade_review_history"] = trade_review_history
        session_state["latest_trade_review"] = latest_review
        session_state["trade_review_metrics"] = metrics_payload
        persistence.persist_session(session_state)

        return {"latest_review": latest_review, "metrics_summary": metrics_payload}

    def review_latest_trade_plan_payload(payload: dict[str, object]) -> dict[str, object]:
        closed = [plan for plan in plan_tracker.plans.values() if plan.status in {"exited", "cancelled"}]
        if not closed:
            return dict(payload)
        latest = sorted(closed, key=lambda item: item.updated_at, reverse=True)[0]
        merged = dict(payload)
        merged["plan_id"] = latest.plan_id
        merged.setdefault("symbol", latest.symbol)
        merged.setdefault("final_status", latest.status)
        return merged

    def update_trade_plan_status(payload: dict[str, object]) -> dict[str, object]:
        plan_id = str(payload.get("plan_id", ""))
        new_status = str(payload.get("status", ""))
        reason = str(payload.get("reason")) if payload.get("reason") is not None else None
        if plan_id not in plan_tracker.plans:
            return {"plan_id": plan_id, "status": "unknown", "debug": {"reason": "missing_plan"}}
        plan = plan_tracker.update_status(plan_id, new_status, reason=reason)
        return plan_tracker._serialize(plan)


    def build_strategy_analysis(payload: dict[str, object]) -> dict[str, object]:
        lookback_raw = payload.get("lookback", strategy_cfg.get("lookback_limits", {}).get("default", 50))
        try:
            lookback = int(lookback_raw)
        except (TypeError, ValueError):
            lookback = int(strategy_cfg.get("lookback_limits", {}).get("default", 50))
        min_lb = int(strategy_cfg.get("lookback_limits", {}).get("min", 10))
        max_lb = int(strategy_cfg.get("lookback_limits", {}).get("max", 250))
        lookback = max(min_lb, min(max_lb, lookback))

        all_plans = list(plan_tracker.snapshot().get("all", []))
        completed = [p for p in all_plans if str(p.get("status")) in {"exited", "cancelled"}]
        snapshot = strategy_service.build_strategy_snapshot(
            completed_plans=completed,
            tracking_snapshots=trade_plan_tracking_history,
            review_results=trade_review_history,
            lookback=lookback,
        ).to_payload()

        strategy_history.append(snapshot)
        retention = int(strategy_cfg.get("history_retention", 40))
        del strategy_history[:-retention]

        persistence.persist_strategy_runtime(
            {"latest_strategy_snapshot": snapshot, "strategy_history": strategy_history},
            retention=retention,
        )
        session_state["latest_strategy_snapshot"] = snapshot
        session_state["strategy_history"] = list(strategy_history)
        persistence.persist_session(session_state)
        return snapshot

    def build_visual_explanation(payload: dict[str, object]) -> dict[str, object]:
        symbol = str(payload.get("symbol", "")).upper()
        view_type = str(payload.get("view_type", "opinion")).lower()
        raw_timeframes = payload.get("timeframes")
        if isinstance(raw_timeframes, str):
            timeframes = tuple(item.strip() for item in raw_timeframes.split(",") if item.strip())
        elif isinstance(raw_timeframes, (list, tuple)):
            timeframes = tuple(str(item) for item in raw_timeframes)
        else:
            timeframes = tuple(visuals_cfg.get("default_timeframes", ["1m", "5m", "15m"]))

        bars_limit = int(visuals_cfg.get("bar_window_sizes", {}).get("1m", 90))
        bars_1m = runtime_market_data_provider.get_bars(symbol, "1m", bars_limit)
        state = states.get(symbol)
        latest_plan = interaction_state.latest_trade_plan if str(interaction_state.latest_trade_plan.get("symbol", "")).upper() == symbol else {}
        latest_tracking = interaction_state.latest_trade_plan_tracking if str(interaction_state.latest_trade_plan_tracking.get("symbol", "")).upper() == symbol else {}
        latest_opinion = interaction_state.latest_trade_idea_opinion if str(interaction_state.latest_trade_idea_opinion.get("symbol", "")).upper() == symbol else {}
        snapshot = visual_service.build_visual_explanation(
            request=VisualExplainabilityRequest(symbol=symbol, view_type=view_type, timeframes=timeframes, plan_id=str(payload.get("plan_id")) if payload.get("plan_id") else None),
            bars_1m=bars_1m,
            state=state,
            opinion=dict(payload.get("opinion", latest_opinion)) if isinstance(payload.get("opinion", latest_opinion), dict) else latest_opinion,
            trade_plan=dict(payload.get("trade_plan", latest_plan)) if isinstance(payload.get("trade_plan", latest_plan), dict) else latest_plan,
            tracking=dict(payload.get("tracking", latest_tracking)) if isinstance(payload.get("tracking", latest_tracking), dict) else latest_tracking,
            gameplan=interaction_state.latest_premarket_gameplan,
            market_intelligence=market_intelligence_payload,
            review=interaction_state.latest_trade_review,
        )
        visual_history.append(snapshot)
        retention = int(visuals_cfg.get("history_retention", 20))
        del visual_history[:-retention]
        session_state["visual_explanation_history"] = visual_history
        session_state["latest_visual_explanation"] = snapshot
        persistence.persist_session(session_state)
        return snapshot

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
        target_move_handler=build_target_move_board,
        trade_idea_handler=build_trade_idea_opinion,
        trade_plan_handler=build_trade_plan,
        trade_plan_status_handler=update_trade_plan_status,
        trade_plan_tracking_handler=evaluate_trade_plan_tracking,
        trade_review_handler=review_trade_plan,
        latest_trade_review_handler=review_latest_trade_plan_payload,
        premarket_gameplan_handler=lambda payload: gameplan_service.refresh_daily_gameplan(
            snapshot=market_intelligence_snapshot,
            watchlist=list(payload.get("watchlist") or tickers_config.get("watchlist", [])),
            ticker_states=states,
            explicit_symbols=list(payload.get("symbols") or []),
        ),
        visual_explanation_handler=build_visual_explanation,
        strategy_analysis_handler=build_strategy_analysis,
        narrative_summary_handler=lambda summary_type, payload: narrative_service.summarize(summary_type, payload),
    )

    if session_state.get("latest_target_move_board"):
        interaction.state.latest_target_move_board = dict(session_state.get("latest_target_move_board", {}))
    if session_state.get("latest_trade_idea_opinion"):
        interaction.state.latest_trade_idea_opinion = dict(session_state.get("latest_trade_idea_opinion", {}))
    if session_state.get("latest_trade_plan"):
        interaction.state.latest_trade_plan = dict(session_state.get("latest_trade_plan", {}))
    if session_state.get("latest_trade_plan_tracking"):
        interaction.state.latest_trade_plan_tracking = dict(session_state.get("latest_trade_plan_tracking", {}))
    if session_state.get("latest_trade_review"):
        interaction.state.latest_trade_review = dict(session_state.get("latest_trade_review", {}))
    interaction.state.trade_review_history = list(session_state.get("trade_review_history", []))[-int(review_cfg.get("history_limit", 120)) :]
    interaction.state.trade_review_metrics = dict(session_state.get("trade_review_metrics", {}))
    if session_state.get("latest_backtest_run_summary"):
        interaction.state.latest_backtest_run_summary = dict(session_state.get("latest_backtest_run_summary", {}))
    interaction.state.recent_backtest_evaluations = dict(session_state.get("recent_backtest_evaluations", {}))
    interaction.state.latest_historical_data = dict(session_state.get("latest_historical_data", {}))
    interaction.state.latest_premarket_gameplan = dict(session_state.get("latest_premarket_gameplan", gameplan_payload))
    interaction.state.latest_visual_explanation = dict(session_state.get("latest_visual_explanation", {}))
    interaction.state.visual_explanation_history = list(session_state.get("visual_explanation_history", []))[-int(visuals_cfg.get("history_retention", 20)) :]
    trade_plan_tracking_history[:] = trade_plan_tracking_history[-int(tracking_cfg.get("history_limit", 40)) :]
    if market_intelligence_summary:
        interaction.ingest_llm_summary(market_intelligence_summary)
    if premarket_summary:
        interaction.ingest_llm_summary(premarket_summary)
    if strategy_summary:
        interaction.ingest_llm_summary(strategy_summary)
    if visual_summary:
        interaction.ingest_llm_summary(visual_summary)

    diagnostics = ProviderDiagnostics(policy=str(provider_runtime.get("diagnostics_policy", "warn_on_degraded")), logger=LOGGER)
    provider_diagnostics = diagnostics.evaluate(
        {
            "runtime_market_loop": runtime_market_data_provider.health_snapshot(active=True),
            "market_data": runtime_market_data_provider.health_snapshot(active=True),
            "historical_data": historical_data_provider.health_snapshot(active=True),
            "options_data": options_data_provider.health_snapshot(active=True),
            "alpaca_market_data": alpaca_market_backend.health_snapshot(active=provider_routes.get("runtime_market_loop_provider") == "alpaca" or provider_routes.get("historical_data_provider") == "alpaca"),
            "alpaca_options_data": alpaca_options_backend.health_snapshot(active=provider_routes.get("options_runtime_provider") in {"alpaca", "alpaca_options"}),
            "market_intelligence": market_intelligence_service.source.health_snapshot(active=provider_routes.get("market_intelligence_provider") == "alpaca"),
            "wakeword": voice_orchestrator.wakeword_detector.health_snapshot(active=interaction_state.wakeword_enabled),
            "stt": interaction.stt_provider.health_snapshot(active=interaction_state.stt_enabled),
            "tts": voice_orchestrator.tts_provider.health_snapshot(active=interaction_state.tts_enabled),
            "llm": llm_provider.health_snapshot(active=bool(dict(llm_cfg.get("usage", {})).get("narrative_summaries_enabled", True))),
        }
    )
    interaction_state.latest_strategy_analysis = dict(strategy_runtime.get("latest_strategy_snapshot", {}))
    interaction.set_provider_diagnostics(provider_diagnostics)
    interaction.timeline.add_event(
        "llm_provider_changed",
        utc_now_iso(),
        {
            "provider": llm_provider.provider_name,
            "state": dict(provider_diagnostics.get("providers", {})).get("llm", {}).get("state"),
            "model": dict(dict(provider_diagnostics.get("providers", {})).get("llm", {}).get("metadata", {})).get("model"),
        },
    )

    alpaca_smoke_test: dict[str, object] = {}
    if os.getenv("KADE_RUN_ALPACA_SMOKE_TEST", "0") == "1":
        alpaca_smoke_test = AlpacaSmokeTester(
            market_data=alpaca_market_backend,
            intelligence_source=market_intelligence_service.source,
        ).run(symbol=os.getenv("KADE_ALPACA_SMOKE_SYMBOL", "SPY").upper())
        interaction.timeline.add_event(
            "alpaca_smoke_test_completed",
            utc_now_iso(),
            {
                "state": alpaca_smoke_test.get("state"),
                "passed": dict(alpaca_smoke_test.get("summary", {})).get("passed"),
                "failed": dict(alpaca_smoke_test.get("summary", {})).get("failed"),
            },
        )

    radar_signals = [
        {
            "symbol": item.get("symbol"),
            "setup": item.get("state"),
            "signal_type": item.get("state"),
            "confidence": item.get("score"),
            "timeframe": item.get("timeframe", "intraday"),
            "notes": "; ".join(item.get("reasons", [])),
            "supporting_indicators": item.get("reasons", []),
            "setup_tags": item.get("setup_tags", []),
            "alignment_label": item.get("alignment_label"),
            "regime_fit": item.get("regime_fit_label"),
            "supporting_reasons": dict(item.get("explanation", {})).get("supporting_reasons", []),
            "cautionary_reasons": dict(item.get("explanation", {})).get("cautionary_reasons", []),
            "trap_risk": dict(item.get("explanation", {})).get("trap_risk"),
            "summary": dict(item.get("explanation", {})).get("summary"),
            "timestamp": dict(item.get("explanation", {})).get("timestamp") or utc_now_iso(),
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

    previous_regime = str(session_state.get("latest_market_regime", ""))
    interaction.timeline.add_event(
        "market_intelligence_updated",
        utc_now_iso(),
        {
            "regime_label": dict(market_intelligence_payload.get("regime", {})).get("regime_label"),
            "confidence": dict(market_intelligence_payload.get("regime", {})).get("regime_confidence"),
            "headline_count": len(list(market_intelligence_payload.get("key_news", []))),
            "movers_count": len(list(market_intelligence_payload.get("top_movers", []))),
            "major_reasons": list(dict(market_intelligence_payload.get("regime", {})).get("reasons", []))[:3],
        },
    )
    regime_label = str(dict(market_intelligence_payload.get("regime", {})).get("regime_label", "unknown"))
    if previous_regime and previous_regime != regime_label:
        interaction.timeline.add_event(
            "regime_changed",
            utc_now_iso(),
            {
                "from": previous_regime,
                "to": regime_label,
                "confidence": dict(market_intelligence_payload.get("regime", {})).get("regime_confidence"),
                "major_reasons": list(dict(market_intelligence_payload.get("regime", {})).get("reasons", []))[:3],
            },
        )
    major_catalysts = [
        item for item in list(market_intelligence_payload.get("key_news", [])) if str(item.get("catalyst_type")) in {"macro", "earnings", "regulatory"}
    ]
    if major_catalysts:
        interaction.timeline.add_event(
            "major_catalyst_detected",
            utc_now_iso(),
            {
                "count": len(major_catalysts),
                "headlines": [str(item.get("headline", "")) for item in major_catalysts[:3]],
                "catalysts": [str(item.get("catalyst_type", "unknown")) for item in major_catalysts[:3]],
            },
        )
    interaction.timeline.add_event(
        "premarket_gameplan_generated",
        utc_now_iso(),
        {
            "posture": dict(gameplan_payload.get("market_posture", {})).get("posture_label"),
            "regime_label": gameplan_payload.get("regime_label"),
            "top_watchlist_symbols": [item.get("symbol") for item in list(gameplan_payload.get("watchlist_priorities", []))[:3]],
            "catalyst_count": len(list(gameplan_payload.get("key_catalysts", []))),
        },
    )
    interaction.timeline.add_event(
        "watchlist_priorities_updated",
        utc_now_iso(),
        {
            "top_watchlist_symbols": [item.get("symbol") for item in list(gameplan_payload.get("watchlist_priorities", []))[:5]],
            "high_priority_count": len([item for item in list(gameplan_payload.get("watchlist_priorities", [])) if item.get("priority") == "priority_high"]),
        },
    )
    interaction.timeline.add_event(
        "market_posture_changed",
        utc_now_iso(),
        {
            "posture": dict(gameplan_payload.get("market_posture", {})).get("posture_label"),
            "regime_label": gameplan_payload.get("regime_label"),
            "regime_confidence": gameplan_payload.get("regime_confidence"),
        },
    )

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
    session_state["provider_routes"] = provider_routes
    session_state["provider_selection"] = {
        "runtime_market_loop": runtime_market_data_provider.provider_name,
        "market_data": runtime_market_data_provider.provider_name,
        "historical_data": historical_data_provider.provider_name,
        "market_intelligence": market_intelligence_service.source.health_snapshot(active=provider_routes.get("market_intelligence_provider") == "alpaca").provider_name,
        "options_data": options_data_provider.provider_name,
        "options_runtime": options_data_provider.provider_name,
        "wakeword": voice_orchestrator.wakeword_detector.provider_name,
        "stt": interaction.stt_provider.provider_name,
        "tts": voice_orchestrator.tts_provider.provider_name,
        "llm": llm_provider.provider_name,
    }
    session_state["replay_debug"] = interaction.replay_runtime.snapshot()
    session_state["latest_target_move_board"] = interaction_state.latest_target_move_board
    session_state["latest_trade_idea_opinion"] = interaction_state.latest_trade_idea_opinion
    session_state["latest_trade_plan"] = interaction_state.latest_trade_plan
    session_state["latest_trade_plan_tracking"] = interaction_state.latest_trade_plan_tracking
    session_state["latest_trade_review"] = interaction_state.latest_trade_review
    session_state["trade_review_history"] = interaction_state.trade_review_history
    session_state["trade_review_metrics"] = interaction_state.trade_review_metrics
    session_state["latest_backtest_run_summary"] = interaction_state.latest_backtest_run_summary
    session_state["recent_backtest_evaluations"] = interaction_state.recent_backtest_evaluations
    session_state["latest_historical_data"] = interaction_state.latest_historical_data
    session_state["latest_premarket_gameplan"] = interaction_state.latest_premarket_gameplan or gameplan_payload
    session_state["latest_visual_explanation"] = interaction_state.latest_visual_explanation
    session_state["visual_explanation_history"] = interaction_state.visual_explanation_history
    session_state["latest_strategy_snapshot"] = interaction_state.latest_strategy_analysis
    session_state["strategy_history"] = list(strategy_history)
    session_state["latest_market_regime"] = regime_label
    session_state["latest_llm_summary"] = interaction_state.latest_llm_summary
    session_state["llm_summaries"] = interaction_state.llm_summaries
    session_state["llm_summary_history"] = interaction_state.llm_summary_history
    session_state["latest_alpaca_smoke_test"] = alpaca_smoke_test
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
        states=states,
        debug_values=debug_values,
        latest_breadth=market_loop.latest_breadth,
        latest_radar=market_loop.latest_radar,
        options_payload=options_payload,
        execution_payload=execution_payload,
        memory_payload=memory.snapshot(limit=10),
        plan_payload=plan_tracker.snapshot(),
        advisor_payload=advisor_payload,
        style_payload=style_profile.response_guidance(),
        voice_payload={**interaction.dashboard_payload(), "provider_diagnostics": provider_diagnostics, "provider_selection": session_state.get("provider_selection", {}), "historical_data": history_runtime},
        persistence_payload=persistence_meta,
        session_payload=session_state,
        history_payload=history_payload,
        market_intelligence_payload=market_intelligence_payload,
        premarket_gameplan_payload=session_state.get("latest_premarket_gameplan", {}),
        strategy_intelligence_payload=session_state.get("latest_strategy_snapshot", {}),
        alpaca_smoke_test_payload=session_state.get("latest_alpaca_smoke_test", {}),
    )
    print_runtime_summary(dashboard_state, session_state, history_payload, provider_routes=provider_routes)


if __name__ == "__main__":
    main()
