"""Overlay generation from existing Kade runtime outputs."""

from __future__ import annotations

from kade.market.structure import TickerState
from kade.visuals.levels import parse_first_level
from kade.visuals.models import OverlayItem


def _trend_color(trend: str | None) -> str:
    if trend == "up":
        return "bull"
    if trend == "down":
        return "bear"
    return "neutral"


class OverlayFactory:
    def __init__(self, config: dict[str, object]) -> None:
        self.enabled = dict(config.get("overlays", {}))

    def build(
        self,
        *,
        symbol: str,
        timeframe: str,
        bars: list[dict[str, object]],
        state: TickerState | None,
        view_type: str,
        trade_plan: dict[str, object] | None,
        tracking: dict[str, object] | None,
    ) -> list[OverlayItem]:
        overlays: list[OverlayItem] = []
        if state and state.vwap is not None and self.enabled.get("vwap", True):
            overlays.append(OverlayItem("vwap_line", "VWAP", value=float(state.vwap), color="accent", reason="Using ticker state VWAP.", source="ticker_state.vwap"))

        if state and self.enabled.get("trend_guide", True):
            overlays.append(
                OverlayItem(
                    "trend_guide",
                    f"Trend: {state.trend or 'unknown'}",
                    color=_trend_color(state.trend),
                    start_index=max(len(bars) - 20, 0),
                    end_index=max(len(bars) - 1, 0) if bars else None,
                    reason="Trend guide mirrors ticker trend classification.",
                    source="ticker_state.trend",
                )
            )

        plan = trade_plan or {}
        if self.enabled.get("plan_lines", True) and view_type in {"plan", "tracking", "review"} and plan:
            trigger = parse_first_level(dict(plan.get("entry_plan", {})).get("trigger_condition"))
            invalidation = parse_first_level(dict(plan.get("invalidation_plan", {})).get("invalidation_condition"))
            primary = parse_first_level(dict(plan.get("target_plan", {})).get("primary_target"))
            secondary = parse_first_level(dict(plan.get("target_plan", {})).get("secondary_target"))
            if trigger is not None:
                overlays.append(OverlayItem("trigger_line", "Entry Trigger", value=trigger, color="entry", reason="Parsed from trade plan entry condition.", source="trade_plan.entry_plan.trigger_condition"))
            if invalidation is not None:
                overlays.append(OverlayItem("invalidation_line", "Invalidation", value=invalidation, color="risk", reason="Parsed from trade plan invalidation condition.", source="trade_plan.invalidation_plan.invalidation_condition"))
            if primary is not None:
                overlays.append(OverlayItem("target_line", "Primary Target", value=primary, color="target", reason="Parsed from primary target note.", source="trade_plan.target_plan.primary_target"))
            if secondary is not None:
                overlays.append(OverlayItem("target_line", "Secondary Target", value=secondary, color="target_secondary", reason="Parsed from secondary target note.", source="trade_plan.target_plan.secondary_target"))

        status = str(dict(tracking or {}).get("status_after", ""))
        if self.enabled.get("tracking_markers", True) and view_type in {"tracking", "review"} and status:
            marker = "stale" if status in {"stale", "cancelled"} else "active"
            overlays.append(
                OverlayItem(
                    "state_marker",
                    f"Plan state: {status}",
                    start_index=max(len(bars) - 1, 0) if bars else None,
                    color="warn" if marker == "stale" else "info",
                    reason="Derived from latest trade-plan tracking status.",
                    source="trade_plan_tracking.status_after",
                )
            )
        return overlays
