"""Plan calibration logic for target realism and discipline diagnostics."""

from __future__ import annotations

from kade.strategy.models import PlanCalibrationResult
from kade.strategy.performance import avg, safe_float


def build_plan_calibration(trades: list[dict[str, object]], thresholds: dict[str, object] | None = None) -> PlanCalibrationResult:
    thresholds = thresholds or {}
    count = len(trades)
    if count == 0:
        return PlanCalibrationResult(
            target_realism="insufficient_data",
            target_hit_rate=0.0,
            avg_target_distance=0.0,
            avg_actual_move=0.0,
            invalidation_hit_rate=0.0,
            invalidation_respect_rate=0.0,
            avg_loss_if_ignored=0.0,
            discipline_rate=0.0,
            avg_time_to_target=0.0,
            avg_time_to_stop=0.0,
            time_horizon_accuracy=0.0,
            notes=["No completed trades in lookback window."],
        )

    hits = sum(1 for t in trades if bool(t.get("target_hit")))
    invalidation_hits = sum(1 for t in trades if bool(t.get("invalidation_hit")))
    respected = sum(1 for t in trades if bool(t.get("invalidation_respected")))
    disciplined = sum(1 for t in trades if bool(t.get("disciplined")))

    target_distances = [safe_float(t.get("target_distance")) for t in trades]
    actual_moves = [safe_float(t.get("actual_move")) for t in trades]
    ignored_losses = [abs(safe_float(t.get("roi"))) for t in trades if t.get("discipline_label") == "invalidation_ignored" and safe_float(t.get("roi")) < 0]

    to_target = [safe_float(t.get("time_to_target_minutes")) for t in trades if t.get("time_to_target_minutes") is not None]
    to_stop = [safe_float(t.get("time_to_stop_minutes")) for t in trades if t.get("time_to_stop_minutes") is not None]

    horizon_hits = 0
    for trade in trades:
        hold = safe_float(trade.get("hold_minutes"))
        max_hold = safe_float(trade.get("max_hold_minutes"))
        if max_hold > 0 and hold <= max_hold:
            horizon_hits += 1

    target_hit_rate = round(hits / count, 4)
    avg_target_distance = avg(target_distances)
    avg_actual_move = avg(actual_moves)

    realistic_threshold = safe_float(thresholds.get("realistic_ratio_min"), 0.75)
    stretched_threshold = safe_float(thresholds.get("stretched_ratio_min"), 0.45)
    ratio = (avg_actual_move / avg_target_distance) if avg_target_distance > 0 else 0.0
    if ratio >= realistic_threshold:
        target_realism = "realistic"
    elif ratio >= stretched_threshold:
        target_realism = "stretched"
    else:
        target_realism = "unrealistic"

    notes = [
        f"Target realism ratio={round(ratio, 4)} using actual/target distance.",
        f"Discipline rate={round(disciplined / count, 4)} over {count} trades.",
    ]

    return PlanCalibrationResult(
        target_realism=target_realism,
        target_hit_rate=target_hit_rate,
        avg_target_distance=avg_target_distance,
        avg_actual_move=avg_actual_move,
        invalidation_hit_rate=round(invalidation_hits / count, 4),
        invalidation_respect_rate=round(respected / count, 4),
        avg_loss_if_ignored=avg(ignored_losses),
        discipline_rate=round(disciplined / count, 4),
        avg_time_to_target=avg(to_target),
        avg_time_to_stop=avg(to_stop),
        time_horizon_accuracy=round(horizon_hits / count, 4),
        notes=notes,
    )
