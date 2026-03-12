"""Service entrypoint for deterministic visual explainability snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from kade.market.structure import Bar, TickerState
from kade.utils.time import utc_now_iso
from kade.visuals.charts import ChartDataAssembler
from kade.visuals.explain import build_panels
from kade.visuals.models import SymbolChartView, VisualExplanationSnapshot
from kade.visuals.overlays import OverlayFactory


@dataclass(frozen=True)
class VisualExplainabilityRequest:
    symbol: str
    view_type: str
    timeframes: tuple[str, ...]
    plan_id: str | None = None


class VisualExplainabilityService:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.default_timeframes = tuple(config.get("default_timeframes", ["1m", "5m", "15m"]))
        self.assembler = ChartDataAssembler(config)
        self.overlays = OverlayFactory(config)

    def build_visual_explanation(
        self,
        *,
        request: VisualExplainabilityRequest,
        bars_1m: list[Bar],
        state: TickerState | None,
        opinion: dict[str, object] | None,
        trade_plan: dict[str, object] | None,
        tracking: dict[str, object] | None,
        gameplan: dict[str, object] | None,
        market_intelligence: dict[str, object] | None,
        review: dict[str, object] | None,
    ) -> dict[str, object]:
        charts: list[SymbolChartView] = []
        timeframes = request.timeframes or self.default_timeframes
        for timeframe in timeframes:
            bars = self.assembler.bars_for_timeframe(bars_1m, timeframe)
            overlays = self.overlays.build(
                symbol=request.symbol,
                timeframe=timeframe,
                bars=bars,
                state=state,
                view_type=request.view_type,
                trade_plan=trade_plan,
                tracking=tracking,
            )
            annotations = []
            if not bars:
                annotations.append({"type": "warning", "text": "No bars available for timeframe.", "source": "bars"})
            charts.append(
                SymbolChartView(
                    symbol=request.symbol,
                    timeframe=timeframe,
                    bars=bars,
                    overlays=overlays,
                    annotations=annotations,
                    reasoning_links=[{"source": "view_type", "value": request.view_type}],
                    title=f"{request.symbol} {timeframe}",
                    subtitle=f"View: {request.view_type}",
                )
            )

        side_panels = build_panels(
            view_type=request.view_type,
            symbol=request.symbol,
            opinion=opinion,
            trade_plan=trade_plan,
            tracking=tracking,
            gameplan=gameplan,
            market_intelligence=market_intelligence,
            review=review,
        )
        snapshot = VisualExplanationSnapshot(
            symbol=request.symbol,
            view_type=request.view_type,
            charts=charts,
            side_panels=side_panels,
            generated_at=utc_now_iso(),
            debug={"plan_id": request.plan_id, "bars_input": len(bars_1m), "timeframes": list(timeframes)},
        )
        return snapshot.as_dict()
