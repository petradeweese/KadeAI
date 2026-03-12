"""Strategy intelligence orchestration service."""

from __future__ import annotations

from kade.strategy.analytics import compute_discipline_impact, compute_regime_performance, compute_symbol_performance, setup_archetype_stats
from kade.strategy.archetypes import classify_setup_archetype
from kade.strategy.calibration import build_plan_calibration
from kade.strategy.grouping import compute_grouped_statistics
from kade.strategy.models import SetupArchetype, StrategyAnalyticsSnapshot, StrategyPerformanceSnapshot
from kade.strategy.performance import avg, max_drawdown, median_value, parse_price, safe_float, win_rate
from kade.utils.time import utc_now_iso


class StrategyIntelligenceService:
    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.config = config or {}

    def analyze_completed_trades(
        self,
        completed_plans: list[dict[str, object]],
        tracking_snapshots: list[dict[str, object]],
        review_results: list[dict[str, object]],
        lookback: int | None = None,
    ) -> list[dict[str, object]]:
        lookback_limit = lookback if lookback is not None else int(self.config.get("lookback_limits", {}).get("default", 50))
        plans = completed_plans[-lookback_limit:] if lookback_limit > 0 else []
        tracking_by_id = {str(s.get("plan_id")): s for s in tracking_snapshots}
        review_by_id = {str(r.get("plan_id")): r for r in review_results}

        trades: list[dict[str, object]] = []
        for plan in plans:
            pid = str(plan.get("plan_id", "unknown"))
            tracking = tracking_by_id.get(pid, {})
            review = review_by_id.get(pid, {})
            entry = parse_price(dict(plan.get("entry_plan", {})).get("trigger_condition", plan.get("trigger_condition")))
            target = parse_price(dict(plan.get("target_plan", {})).get("primary_target", plan.get("target_exit_idea")))
            invalidation = parse_price(dict(plan.get("invalidation_plan", {})).get("invalidation_condition", plan.get("invalidation_concept")))
            exit_price = parse_price(review.get("exit_price"))
            roi = safe_float(review.get("realized_outcome", {}).get("roi", review.get("roi", 0.0)))

            discipline_label = str(review.get("review_label") or review.get("discipline_label") or "unknown")
            disciplined = discipline_label in {"well_executed", "mostly_disciplined", "cancelled_correctly", "disciplined"}
            regime = str(plan.get("linked_trade_idea_opinion", {}).get("regime_fit") or plan.get("regime_fit") or "unknown")

            target_distance = abs(target - entry) / entry if entry and target else 0.0
            actual_move = abs((exit_price if exit_price else entry or 0.0) - (entry or 0.0)) / (entry or 1.0) if entry else 0.0
            hold_minutes = safe_float(review.get("hold_minutes", tracking.get("elapsed_minutes", plan.get("max_hold_minutes", 0))))

            trades.append(
                {
                    "plan_id": pid,
                    "symbol": str(plan.get("symbol", "UNKNOWN")).upper(),
                    "direction": str(plan.get("direction", "unknown")),
                    "regime": regime,
                    "risk_posture": str(plan.get("risk_posture", "unknown")),
                    "target_plausibility": str(plan.get("target_plausibility", "unknown")),
                    "discipline_label": discipline_label,
                    "disciplined": disciplined,
                    "entry_price": entry,
                    "target_price": target,
                    "invalidation_price": invalidation,
                    "exit_price": exit_price,
                    "roi": roi,
                    "outcome": str(review.get("outcome_label", review.get("final_status", plan.get("status", "unknown")))),
                    "hold_minutes": hold_minutes,
                    "max_hold_minutes": safe_float(plan.get("max_hold_minutes", 0)),
                    "target_distance": round(target_distance, 4),
                    "actual_move": round(actual_move, 4),
                    "target_hit": bool(review.get("outcome_label") == "target_reached_or_positive" or roi > 0),
                    "invalidation_hit": str(tracking.get("invalidation_state", "safe")) in {"invalidated", "warning"},
                    "invalidation_respected": bool(review.get("invalidation_respected", discipline_label != "invalidation_ignored")),
                    "time_to_target_minutes": review.get("time_to_target_minutes"),
                    "time_to_stop_minutes": review.get("time_to_stop_minutes"),
                    "plan": plan,
                    "tracking": tracking,
                    "review": review,
                }
            )
        return trades

    def classify_setup_archetype(self, trade: dict[str, object]) -> SetupArchetype:
        result = classify_setup_archetype(trade, rules=dict(self.config.get("archetype_rules", {})))
        plan = trade.get("plan") if isinstance(trade.get("plan"), dict) else {}
        setup = SetupArchetype(
            plan_id=str(trade.get("plan_id", "unknown")),
            symbol=str(trade.get("symbol", "UNKNOWN")),
            setup_type=str(plan.get("linked_target_move_board", {}).get("setup_tags", ["untagged"])[0]),
            regime=str(trade.get("regime", "unknown")),
            posture=str(plan.get("risk_posture", "unknown")),
            direction=str(trade.get("direction", "unknown")),
            entry_price=trade.get("entry_price"),
            target_price=trade.get("target_price"),
            invalidation_price=trade.get("invalidation_price"),
            outcome=str(trade.get("outcome", "unknown")),
            roi=safe_float(trade.get("roi")),
            discipline_label=str(trade.get("discipline_label", "unknown")),
            archetype_label=result.archetype_label,
            confidence=result.confidence,
            reasoning=result.reasoning,
            created_at=str(plan.get("created_at", "")),
            completed_at=str(trade.get("review", {}).get("reviewed_at", plan.get("updated_at", ""))),
        )
        return setup

    def compute_regime_performance(self, trades: list[dict[str, object]]) -> list[dict[str, object]]:
        return [item.to_payload() for item in compute_regime_performance(trades)]

    def compute_symbol_performance(self, trades: list[dict[str, object]]) -> list[dict[str, object]]:
        return [item.to_payload() for item in compute_symbol_performance(trades)]

    def compute_discipline_impact(self, trades: list[dict[str, object]]) -> dict[str, object]:
        return compute_discipline_impact(trades).to_payload()

    def build_strategy_snapshot(
        self,
        completed_plans: list[dict[str, object]],
        tracking_snapshots: list[dict[str, object]],
        review_results: list[dict[str, object]],
        lookback: int | None = None,
        now_iso: str | None = None,
    ) -> StrategyAnalyticsSnapshot:
        trades = self.analyze_completed_trades(completed_plans, tracking_snapshots, review_results, lookback=lookback)
        archetypes = [self.classify_setup_archetype(trade) for trade in trades]
        enriched = [{**trade, "setup_archetype": archetype.archetype_label} for trade, archetype in zip(trades, archetypes)]

        rois = [safe_float(t.get("roi")) for t in enriched]
        holds = [safe_float(t.get("hold_minutes")) for t in enriched]
        summary = StrategyPerformanceSnapshot(
            trade_count=len(enriched),
            win_rate=win_rate(rois),
            average_roi=avg(rois),
            median_roi=median_value(rois),
            max_drawdown=max_drawdown(rois),
            avg_hold_minutes=avg(holds),
        )

        calibration = build_plan_calibration(enriched, dict(self.config.get("calibration_thresholds", {})))
        snapshot = StrategyAnalyticsSnapshot(
            setup_archetype_stats=setup_archetype_stats([a.to_payload() for a in archetypes]),
            regime_performance=self.compute_regime_performance(enriched),
            symbol_performance=self.compute_symbol_performance(enriched),
            discipline_impact=self.compute_discipline_impact(enriched),
            plan_calibration_summary=calibration.to_payload(),
            recent_trades_summary=summary.to_payload(),
            grouped_statistics=compute_grouped_statistics(enriched),
            generated_at=now_iso or utc_now_iso(),
        )
        return snapshot
