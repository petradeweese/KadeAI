"""Entrypoint for Kade local application."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from kade.brain import AdvisorReasoningEngine, ConversationMemory, SessionPlanTracker, StyleProfileManager
from kade.dashboard.app import create_app_status
from kade.execution import PaperExecutionWorkflow
from kade.execution.models import ExecutionRejection
from kade.logging_utils import LogCategory, get_logger, log_event, setup_logging
from kade.market.alpaca_client import MockAlpacaClient
from kade.market.market_loop import MarketStateLoop
from kade.options import OptionsSelectionPipeline, TradeIntent
from kade.options.mock_chain import build_mock_chain

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

    memory = ConversationMemory(brain_config, logger=LOGGER)
    plan_tracker = SessionPlanTracker(brain_config, logger=LOGGER)
    style_profile = StyleProfileManager(brain_config)
    advisor = AdvisorReasoningEngine(brain_config, logger=LOGGER)

    market_loop = MarketStateLoop(
        market_client=MockAlpacaClient(),
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
    else:
        states, debug_values = market_loop.update_once()
        options_payload = {"by_symbol": {}}
        execution_payload = {"orders": [], "rejections": [], "debug": {}}

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
            chain = build_mock_chain(target_symbol, target_state.last_price)
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
                    trades_today=0,
                    daily_realized_pnl=0.0,
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
                },
            }

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

        dashboard_state = create_app_status(
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
        )
        print("Kade Phase 5 initialized")
        print(f"Ticker cards: {dashboard_state['card_count']}")
        print(f"Radar queue: {len(dashboard_state['radar']['queue'])}")
        print(f"Active plans: {len(dashboard_state['plans'].get('active', []))}")
        print(f"Recent memory entries: {len(dashboard_state['memory'].get('recent', []))}")
        print(f"Advisor outputs: {len(dashboard_state['advisor'].get('by_symbol', {}))}")


if __name__ == "__main__":
    main()
