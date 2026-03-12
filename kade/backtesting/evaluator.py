"""Deterministic evaluation logic for opinion/scenario/radar outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from kade.backtesting.models import OutcomeLabel


@dataclass
class EvaluationThresholds:
    partial_move_ratio: float = 0.5
    invalidation_ratio: float = 0.6
    radar_hit_move_pct: float = 0.4


class BacktestEvaluator:
    def __init__(self, thresholds: EvaluationThresholds) -> None:
        self.thresholds = thresholds

    def label_outcome(self, *, direction: str, current_price: float, target_price: float, future_prices: list[float]) -> OutcomeLabel:
        if not future_prices:
            return OutcomeLabel("unknown", False, None, 0.0, 0.0)

        delta = target_price - current_price
        move_pct_required = abs(delta) / max(current_price, 0.0001) * 100.0
        hit_step: int | None = None

        max_move_pct = (max(future_prices) - current_price) / max(current_price, 0.0001) * 100.0
        min_move_pct = (min(future_prices) - current_price) / max(current_price, 0.0001) * 100.0

        bullish = direction.lower() in {"bullish", "call", "long", "up"}
        if bullish:
            for i, px in enumerate(future_prices, start=1):
                if px >= target_price:
                    hit_step = i
                    break
            favorable_move = max_move_pct
            adverse_move = abs(min(min_move_pct, 0.0))
        else:
            for i, px in enumerate(future_prices, start=1):
                if px <= target_price:
                    hit_step = i
                    break
            favorable_move = abs(min(min_move_pct, 0.0))
            adverse_move = max(max_move_pct, 0.0)

        if hit_step is not None:
            label = "target_hit"
            hit = True
        elif move_pct_required > 0 and favorable_move >= (move_pct_required * self.thresholds.partial_move_ratio):
            label = "partial_move"
            hit = False
        elif move_pct_required > 0 and adverse_move >= (move_pct_required * self.thresholds.invalidation_ratio):
            label = "invalidated"
            hit = False
        else:
            label = "target_missed"
            hit = False

        return OutcomeLabel(label, hit, hit_step, round(max_move_pct, 4), round(min_move_pct, 4))

    def evaluate_stance_alignment(self, stance: str, outcome: str) -> str:
        supportive = stance in {"agree", "strong"}
        cautious = stance in {"pass", "cautious"}

        if outcome == "target_hit":
            return "aligned" if supportive else "too_bearish"
        if outcome in {"target_missed", "invalidated"}:
            return "too_bullish" if supportive else "aligned"
        if outcome == "partial_move":
            return "mixed"
        return "unknown"

    def scenario_usefulness(self, board: dict[str, object], outcome: OutcomeLabel) -> tuple[bool, str]:
        candidates = list(board.get("candidates", []))
        if not candidates:
            return False, "none"
        top = candidates[0]
        top_useful = bool(outcome.target_hit and float(top.get("estimated_percent_return", 0.0)) > 0)

        buckets = dict(board.get("buckets", {}))
        winner = "none"
        for bucket_name, bucket_items in buckets.items():
            if bucket_items and top.get("option_symbol") == bucket_items[0].get("option_symbol"):
                winner = bucket_name
                break
        return top_useful, winner

    def radar_hit(self, signal: dict[str, object], future_prices: list[float], current_price: float) -> bool:
        if not future_prices:
            return False
        direction = str(signal.get("direction") or signal.get("bias") or "bullish").lower()
        max_move_pct = (max(future_prices) - current_price) / max(current_price, 0.0001) * 100.0
        min_move_pct = (min(future_prices) - current_price) / max(current_price, 0.0001) * 100.0
        if direction in {"bearish", "put", "down"}:
            return abs(min(min_move_pct, 0.0)) >= self.thresholds.radar_hit_move_pct
        return max(max_move_pct, 0.0) >= self.thresholds.radar_hit_move_pct
