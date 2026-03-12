"""Structured visual explainability models for deterministic dashboard rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OverlayItem:
    overlay_type: str
    label: str
    value: float | None = None
    start_index: int | None = None
    end_index: int | None = None
    color: str = "neutral"
    reason: str = ""
    source: str = ""
    style: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "overlay_type": self.overlay_type,
            "label": self.label,
            "color": self.color,
            "reason": self.reason,
            "source": self.source,
            "style": dict(self.style),
        }
        if self.value is not None:
            payload["value"] = self.value
        if self.start_index is not None:
            payload["start_index"] = self.start_index
        if self.end_index is not None:
            payload["end_index"] = self.end_index
        return payload


@dataclass(frozen=True)
class SymbolChartView:
    symbol: str
    timeframe: str
    bars: list[dict[str, object]]
    overlays: list[OverlayItem]
    annotations: list[dict[str, object]] = field(default_factory=list)
    reasoning_links: list[dict[str, object]] = field(default_factory=list)
    title: str = ""
    subtitle: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars": list(self.bars),
            "overlays": [item.as_dict() for item in self.overlays],
            "annotations": list(self.annotations),
            "reasoning_links": list(self.reasoning_links),
            "title": self.title,
            "subtitle": self.subtitle,
        }


@dataclass(frozen=True)
class ExplanationPanel:
    panel_type: str
    title: str
    items: list[str]
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "panel_type": self.panel_type,
            "title": self.title,
            "items": list(self.items),
            "source": self.source,
        }


@dataclass(frozen=True)
class VisualExplanationSnapshot:
    symbol: str
    view_type: str
    charts: list[SymbolChartView]
    side_panels: list[ExplanationPanel]
    generated_at: str
    debug: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "view_type": self.view_type,
            "charts": [chart.as_dict() for chart in self.charts],
            "side_panels": [panel.as_dict() for panel in self.side_panels],
            "generated_at": self.generated_at,
            "debug": dict(self.debug),
        }
