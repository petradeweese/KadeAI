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
        "market_intelligence": 50,
        "premarket_gameplan": 50,
        "radar": 50,
        "movers": 60,
        "trade_idea": 70,
        "target_move": 70,
        "trade_plan": 70,
        "visual_explainability": 75,
        "trade_plan_tracking": 80,
        "execution_monitor": 90,
        "trade_review": 95,
        "strategy_intelligence": 95,
        "timeline": 120,
        "provider_diagnostics": 120,
        "raw_debug": 130,
    }
    collapsed = {"timeline", "provider_diagnostics", "raw_debug"}
    highlighted: list[str] = []

    if mode == "market":
        panel_order.update({"market_intelligence": 1, "premarket_gameplan": 2, "radar": 3, "movers": 4})
        collapsed.update({"trade_review", "execution_monitor"})
    elif mode == "trade":
        panel_order.update({"trade_idea": 1, "target_move": 2, "trade_plan": 3, "visual_explainability": 4})
        highlighted.extend(["trade_idea", "target_move", "trade_plan", "visual_explainability"])
        collapsed.update({"trade_review", "timeline"})
    elif mode == "tracking":
        panel_order.update({"trade_plan_tracking": 1, "trade_plan": 2, "visual_explainability": 3, "execution_monitor": 4})
        highlighted.extend(["trade_plan_tracking", "trade_plan", "visual_explainability", "execution_monitor"])
        collapsed.update({"market_intelligence", "premarket_gameplan"})
    elif mode == "review":
        panel_order.update({"trade_review": 1, "trade_plan_tracking": 2, "strategy_intelligence": 3, "trade_plan": 4})
        highlighted.extend(["trade_review", "strategy_intelligence"])
        collapsed.update({"execution_monitor", "radar"})
    elif mode == "analysis":
        panel_order.update({"strategy_intelligence": 1, "trade_review": 2, "market_intelligence": 3, "movers": 4})
        highlighted.extend(["strategy_intelligence", "market_intelligence"])
        collapsed.update({"execution_monitor", "trade_plan_tracking"})

    if active_symbol:
        for symbol_panel in ("trade_idea", "target_move", "trade_plan", "visual_explainability", "trade_plan_tracking"):
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
