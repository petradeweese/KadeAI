from __future__ import annotations


def dashboard_view_model(payload: dict[str, object]) -> dict[str, object]:
    console = dict(payload.get("operator_console", {}))
    market = dict(console.get("market_intelligence", {}))
    premarket = dict(console.get("premarket_gameplan", {}))
    trade_idea = dict(console.get("trade_idea_opinion", {}))
    trade_plan = dict(console.get("trade_plan", {}))
    tracking = dict(console.get("trade_plan_tracking", {}))
    strategy = dict(console.get("strategy_intelligence", {}))
    visual = dict(console.get("visual_explainability", {}))

    return {
        "runtime": dict(console.get("runtime", {})),
        "providers": dict(console.get("providers", {})),
        "llm": dict(console.get("llm", {})),
        "market_overview": {
            "regime": dict(market.get("regime", {})).get("label", "unknown"),
            "news_count": len(list(market.get("key_news", []))),
            "movers_count": len(list(market.get("top_movers", []))),
            "summary": dict(market.get("narrative_summary", {})).get("summary") or "Market intelligence ready.",
        },
        "premarket_gameplan": {
            "posture": dict(premarket.get("market_posture", {})).get("posture_label", "mixed"),
            "catalysts": list(premarket.get("key_catalysts", [])),
            "risks": list(premarket.get("risks", [])),
            "summary": dict(premarket.get("narrative_summary", {})).get("summary") or "Premarket priorities prepared.",
        },
        "trade_workflow": {
            "trade_idea": trade_idea,
            "target_move": dict(console.get("target_move_board", {})),
            "trade_plan": trade_plan,
            "trade_plan_tracking": tracking,
            "trade_review": dict(console.get("trade_review", {})),
        },
        "visual_explainability": visual,
        "strategy_intelligence": strategy,
        "secondary": {
            "execution": dict(console.get("execution", {})),
            "timeline": dict(console.get("timeline", {})),
            "diagnostics": dict(console.get("providers", {})),
        },
    }
