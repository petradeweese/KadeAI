"""Deterministic trade plan builder."""

from __future__ import annotations

from datetime import datetime

from kade.market.structure import TickerState
from kade.planning.checklist import build_execution_checklist
from kade.planning.formatter import top_scenario_summary
from kade.planning.models import TradePlanContext, TradePlanDecision
from kade.planning.rules import (
    entry_plan,
    hold_plan,
    invalidation_plan,
    market_alignment,
    normalize_direction,
    risk_posture,
    target_plan,
)
from kade.utils.time import utc_now


class TradePlanBuilder:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    def build(self, context: TradePlanContext, now: datetime | None = None) -> TradePlanDecision:
        now = now or utc_now()
        direction = normalize_direction(context.direction)
        state = context.ticker_state if isinstance(context.ticker_state, TickerState) else TickerState(symbol=context.symbol)
        opinion = dict(context.trade_idea_opinion or {})
        request_context = dict(context.user_request_context or {})
        stance = str(opinion.get("stance") or "cautious")
        confidence = str(opinion.get("confidence_label") or str(state.confidence_label or "medium"))
        plausibility = str(opinion.get("target_plausibility") or "possible_but_stretched")
        trap_risk = str(opinion.get("trap_risk") or state.trap_risk or "moderate")
        regime_fit = str(opinion.get("regime_fit") or ("fit" if state.regime in {"trend", "momentum"} else "unclear"))
        breadth_bias = str(context.breadth_context.get("bias", "unknown"))
        align = str(opinion.get("market_alignment") or market_alignment(direction, state, breadth_bias))

        cautious = stance in {"cautious", "pass"} or align != "aligned" or trap_risk in {"moderate", "high"}

        current_price_raw = opinion.get("current_price")
        if current_price_raw is None:
            current_price_raw = request_context.get("current_price")
        if current_price_raw is None:
            current_price_raw = state.last_price
        current_price = float(current_price_raw if current_price_raw is not None else 0.0)

        target_price_raw = opinion.get("target_price")
        if target_price_raw is None:
            target_price_raw = request_context.get("target_price")
        if target_price_raw is None:
            target_price_raw = current_price
        target_price = float(target_price_raw)

        minutes_raw = opinion.get("time_horizon_minutes")
        if minutes_raw is None:
            minutes_raw = request_context.get("time_horizon_minutes")
        minutes = int(minutes_raw if minutes_raw is not None else 60)

        entry = entry_plan(direction, state, align, cautious)
        invalidation = invalidation_plan(direction, state)
        target = target_plan(direction, current_price, target_price, plausibility)
        hold = hold_plan(minutes, plausibility, int(self.config.get("stale_trade_timing_minutes", 20)))
        posture = risk_posture(stance, trap_risk, align, dict(self.config.get("stance_to_risk_posture", {})))
        qqq_alignment = str(opinion.get("qqq_alignment") or state.qqq_confirmation or "mixed")
        breadth_alignment = str(opinion.get("breadth_alignment") or breadth_bias)
        checklist = build_execution_checklist(
            entry_plan=entry,
            invalidation_plan=invalidation,
            target_plan=target,
            qqq_alignment=qqq_alignment,
            breadth_alignment=breadth_alignment,
            risk_posture=posture,
            checklist_verbosity=str(self.config.get("checklist_verbosity", "standard")),
        )

        return TradePlanDecision(
            stance=stance,
            confidence_label=confidence,
            target_plausibility=plausibility,
            market_alignment=align,
            regime_fit=regime_fit,
            trap_risk=trap_risk,
            entry_plan=entry,
            invalidation_plan=invalidation,
            target_plan=target,
            hold_plan=hold,
            risk_posture=posture,
            execution_checklist=checklist,
            linked_target_move_board=top_scenario_summary(context.target_move_board if isinstance(context.target_move_board, dict) else None),
            linked_trade_idea_opinion={
                "symbol": opinion.get("symbol") or context.symbol,
                "stance": stance,
                "summary": opinion.get("summary") or "No trade-idea opinion summary available.",
            },
            notes=["Deterministic planning rules applied.", f"Source mode: {context.source_mode}."],
            debug={
                "direction": direction,
                "cautious": cautious,
                "radar_setup_tags": list(context.radar_context.get("setup_tags", [])),
                "target_move_linked": bool(context.target_move_board),
            },
            generated_at=now,
        )
