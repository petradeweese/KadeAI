"""Side-panel explainability builders for operator-facing visual context."""

from __future__ import annotations

from kade.visuals.models import ExplanationPanel


def build_panels(
    *,
    view_type: str,
    symbol: str,
    opinion: dict[str, object] | None,
    trade_plan: dict[str, object] | None,
    tracking: dict[str, object] | None,
    gameplan: dict[str, object] | None,
    market_intelligence: dict[str, object] | None,
    review: dict[str, object] | None,
) -> list[ExplanationPanel]:
    panels: list[ExplanationPanel] = []

    regime = dict((market_intelligence or {}).get("regime", {}))
    panels.append(
        ExplanationPanel(
            panel_type="regime",
            title="Market Regime",
            items=[
                f"Label: {regime.get('regime_label', 'unknown')}",
                f"Confidence: {regime.get('regime_confidence', 'unknown')}",
                *[str(item) for item in list(regime.get("reasons", []))[:2]],
            ],
            source="market_intelligence.regime",
        )
    )

    if view_type == "opinion" and opinion:
        panels.append(
            ExplanationPanel(
                panel_type="opinion_alignment",
                title=f"{symbol} Opinion Context",
                items=[
                    f"Stance: {opinion.get('stance', 'unknown')}",
                    f"Market alignment: {opinion.get('market_alignment', 'unknown')}",
                    f"QQQ alignment: {opinion.get('qqq_alignment', 'unknown')}",
                    str(opinion.get("summary", "")),
                ],
                source="trade_idea_opinion",
            )
        )

    if view_type == "plan" and trade_plan:
        panels.append(
            ExplanationPanel(
                panel_type="plan_checklist",
                title="Plan Checklist",
                items=[str(item) for item in list(trade_plan.get("execution_checklist", []))[:4]],
                source="trade_plan.execution_checklist",
            )
        )

    if view_type in {"tracking", "review"} and tracking:
        panels.append(
            ExplanationPanel(
                panel_type="tracking",
                title="Plan Tracking",
                items=[
                    f"Trigger: {tracking.get('trigger_state', 'unknown')}",
                    f"Invalidation: {tracking.get('invalidation_state', 'unknown')}",
                    f"Staleness: {tracking.get('staleness_state', 'unknown')}",
                    str(tracking.get("summary", "")),
                ],
                source="trade_plan_tracking",
            )
        )

    if view_type == "gameplan" and gameplan:
        movers = [str(item.get("symbol")) for item in list(gameplan.get("movers_to_watch", []))[:4]]
        panels.append(
            ExplanationPanel(
                panel_type="premarket",
                title="Premarket Context",
                items=[
                    f"Posture: {dict(gameplan.get('market_posture', {})).get('posture_label', 'unknown')}",
                    f"Top movers: {', '.join(movers) if movers else 'none'}",
                    *[str(item.get("headline")) for item in list(gameplan.get("key_catalysts", []))[:2]],
                ],
                source="premarket_gameplan",
            )
        )

    if view_type == "review" and review:
        latest = dict(review.get("latest_review", {}))
        panels.append(
            ExplanationPanel(
                panel_type="review",
                title="Review Notes",
                items=[
                    f"Outcome: {latest.get('outcome_label', 'unknown')}",
                    f"Discipline: {latest.get('discipline_label', 'unknown')}",
                    str(latest.get("summary", "")),
                ],
                source="trade_review.latest_review",
            )
        )

    return panels
