"""Inspectable deterministic planning rules."""

from __future__ import annotations

from kade.market.structure import TickerState
from kade.planning.models import EntryPlan, HoldPlan, InvalidationPlan, TargetPlan


def normalize_direction(direction: str) -> str:
    lowered = direction.strip().lower()
    if lowered in {"put", "short", "bear", "bearish"}:
        return "bearish"
    if lowered in {"call", "long", "bull", "bullish"}:
        return "bullish"
    return lowered


def market_alignment(direction: str, ticker_state: TickerState, breadth_bias: str) -> str:
    trend = str(ticker_state.trend or "unknown")
    trend_aligned = (direction == "bullish" and trend == "bullish") or (direction == "bearish" and trend == "bearish")
    breadth_aligned = (direction == "bullish" and breadth_bias == "risk_on") or (direction == "bearish" and breadth_bias == "risk_off")
    breadth_conflicting = (direction == "bullish" and breadth_bias == "risk_off") or (direction == "bearish" and breadth_bias == "risk_on")
    if trend_aligned and breadth_aligned:
        return "aligned"
    if not trend_aligned and breadth_conflicting:
        return "conflicting"
    return "mixed"


def entry_plan(direction: str, state: TickerState, alignment: str, cautious: bool) -> EntryPlan:
    if direction == "bearish":
        trigger = "Continuation below VWAP after failed reclaim" if state.vwap else "Continuation lower after rejection"
        confirmation = ["Momentum stays down_bias/strong_down", "QQQ remains risk-off aligned"]
        avoid = ["Price reclaims VWAP with expanding buy volume", "Momentum shifts to mixed"]
    else:
        trigger = "Hold above VWAP after reclaim with continuation" if state.vwap else "Continuation higher after reclaim"
        confirmation = ["Momentum stays up_bias/strong_up", "QQQ remains confirmed"]
        avoid = ["Price loses VWAP on heavy sell pressure", "Momentum shifts to mixed"]
    style = "confirmation" if cautious else "continuation"
    if cautious:
        confirmation.insert(0, "Wait for one extra confirming push/candle")
    return EntryPlan(entry_style=style, trigger_condition=trigger, confirmation_signals=confirmation, avoid_if=avoid)


def invalidation_plan(direction: str, state: TickerState) -> InvalidationPlan:
    if direction == "bearish":
        soft = ["Momentum degrades from down_bias to mixed", "Breadth rotates back to risk_on"]
        hard = ["Reclaim and hold above VWAP", "Break above trigger swing high"]
        condition = "Thesis invalid if price reclaims key reclaim level and momentum flips against downside"
    else:
        soft = ["Momentum degrades from up_bias to mixed", "Breadth rotates back to risk_off"]
        hard = ["Lose and hold below VWAP", "Break below trigger swing low"]
        condition = "Thesis invalid if price loses reclaim zone and momentum flips against upside"
    if not state.vwap:
        hard = [item for item in hard if "VWAP" not in item]
    return InvalidationPlan(invalidation_condition=condition, soft_invalidation=soft, hard_invalidation=hard)


def target_plan(direction: str, current_price: float, target_price: float, plausibility: str) -> TargetPlan:
    if direction == "bearish":
        primary = f"Primary target: {target_price:.2f} downside test"
        secondary = f"Stretch target: {target_price - abs(target_price - current_price) * 0.35:.2f}" if plausibility != "unlikely" else "No stretch target until fresh setup"
    else:
        primary = f"Primary target: {target_price:.2f} upside test"
        secondary = f"Stretch target: {target_price + abs(target_price - current_price) * 0.35:.2f}" if plausibility != "unlikely" else "No stretch target until fresh setup"
    scale = ["Take first scale near primary target", "Trail remainder only if momentum remains aligned"]
    if plausibility == "possible_but_stretched":
        scale.insert(0, "Reduce size and scale sooner because target is stretched")
    if plausibility == "unlikely":
        scale = ["Treat as scalp only", "Exit into first impulse; do not hold for full target"]
    return TargetPlan(primary_target=primary, secondary_target=secondary, scale_out_guidance=scale)


def hold_plan(time_horizon_minutes: int, plausibility: str, stale_default: int) -> HoldPlan:
    max_hold = min(max(time_horizon_minutes, 15), 240)
    if plausibility == "unlikely":
        max_hold = min(max_hold, 45)
    elif plausibility == "possible_but_stretched":
        max_hold = min(max_hold, 90)
    window = "fast follow-through expected in first 15-30m" if max_hold <= 60 else "expected follow-through within first 60m"
    stale_rule = f"If no progress after {min(stale_default, max_hold)} minutes, cancel or de-risk"
    return HoldPlan(max_hold_minutes=max_hold, expected_time_window=window, stale_trade_rule=stale_rule)


def risk_posture(stance: str, trap_risk: str, market_alignment_label: str, mapping: dict[str, str]) -> str:
    posture = mapping.get(stance, "watch_only")
    if trap_risk == "high":
        return "watch_only" if posture == "full" else "pass"
    if market_alignment_label == "conflicting":
        return "reduced" if posture == "full" else "watch_only"
    if trap_risk == "moderate" and posture == "full":
        return "reduced"
    return posture
