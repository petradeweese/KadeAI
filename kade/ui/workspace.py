from __future__ import annotations

from dataclasses import dataclass

WORKSPACE_MODES = {"overview", "market", "trade", "tracking", "review", "analysis"}


@dataclass
class WorkspaceLayout:
    active_workspace_mode: str
    highlighted_panels: list[str]
    collapsed_panels: list[str]
    panel_priority_map: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "active_workspace_mode": self.active_workspace_mode,
            "highlighted_panels": self.highlighted_panels,
            "collapsed_panels": self.collapsed_panels,
            "panel_priority_map": self.panel_priority_map,
        }


def intent_to_workspace_mode(intent: str) -> str:
    intent = str(intent or "").strip().lower()
    mapping = {
        "status": "market",
        "market_overview": "market",
        "radar": "market",
        "premarket_gameplan": "market",
        "trade_idea": "trade",
        "trade_idea_opinion": "trade",
        "target_move": "trade",
        "target_move_scenario": "trade",
        "trade_plan": "trade",
        "trade_plan_tracking": "tracking",
        "trade_plan_check": "tracking",
        "trade_plan_status": "tracking",
        "trade_review": "review",
        "strategy_analysis": "analysis",
        "visual_explain": "trade",
        "visual_explainability": "trade",
        "explicit_command": "overview",
    }
    return mapping.get(intent, "overview")


def build_workspace_layout(mode: str, active_symbol: str | None = None) -> WorkspaceLayout:
    mode = mode if mode in WORKSPACE_MODES else "overview"

    panel_order = {
        "market_context": 5,
        "visual_explainability": 18,
        "trade_idea": 20,
        "target_move": 24,
        "trade_plan": 28,
        "market_intelligence": 60,
        "premarket_gameplan": 62,
        "radar": 64,
        "movers": 66,
        "trade_plan_tracking": 70,
        "execution_monitor": 74,
        "strategy_intelligence": 76,
        "trade_review": 78,
        "timeline": 120,
        "provider_diagnostics": 122,
        "raw_debug": 130,
    }
    collapsed = {
        "market_intelligence",
        "premarket_gameplan",
        "radar",
        "movers",
        "trade_plan_tracking",
        "execution_monitor",
        "strategy_intelligence",
        "trade_review",
        "timeline",
        "provider_diagnostics",
        "raw_debug",
    }
    highlighted: list[str] = []

    if mode == "market":
        panel_order.update({"market_intelligence": 1, "premarket_gameplan": 2, "radar": 3, "movers": 4, "market_context": 5})
        highlighted.extend(["market_intelligence", "premarket_gameplan", "radar", "movers", "market_context"])
        collapsed.difference_update({"market_intelligence", "premarket_gameplan", "radar", "movers"})
    elif mode == "trade":
        panel_order.update({"visual_explainability": 1, "trade_idea": 2, "target_move": 3, "trade_plan": 4, "market_context": 5})
        highlighted.extend(["visual_explainability", "trade_idea", "target_move", "trade_plan", "market_context"])
        collapsed.update({"market_intelligence", "premarket_gameplan", "radar", "movers", "trade_plan_tracking", "execution_monitor", "strategy_intelligence", "trade_review", "timeline", "provider_diagnostics"})
    elif mode == "tracking":
        panel_order.update({"trade_plan_tracking": 1, "trade_plan": 2, "visual_explainability": 3, "execution_monitor": 4, "market_context": 5})
        highlighted.extend(["trade_plan_tracking", "trade_plan", "visual_explainability", "execution_monitor", "market_context"])
        collapsed.difference_update({"trade_plan_tracking", "execution_monitor"})
    elif mode == "review":
        panel_order.update({"trade_review": 1, "trade_plan_tracking": 2, "strategy_intelligence": 3, "trade_plan": 4, "market_context": 5})
        highlighted.extend(["trade_review", "strategy_intelligence", "trade_plan_tracking", "market_context"])
        collapsed.difference_update({"trade_review", "strategy_intelligence", "trade_plan_tracking"})
    elif mode == "analysis":
        panel_order.update({"strategy_intelligence": 1, "trade_review": 2, "market_intelligence": 3, "movers": 4, "market_context": 5})
        highlighted.extend(["strategy_intelligence", "market_intelligence", "trade_review", "market_context"])
        collapsed.difference_update({"strategy_intelligence", "market_intelligence", "trade_review", "movers"})

    if active_symbol:
        for symbol_panel in ("trade_idea", "target_move", "trade_plan", "visual_explainability", "market_context"):
            if symbol_panel not in highlighted:
                highlighted.append(symbol_panel)

    return WorkspaceLayout(
        active_workspace_mode=mode,
        highlighted_panels=highlighted,
        collapsed_panels=sorted(collapsed),
        panel_priority_map=panel_order,
    )


def parse_symbol_from_command(command: str) -> str | None:
    for part in str(command).split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key.strip().lower() == "symbol" and value.strip():
            return value.strip().upper()
    return None
