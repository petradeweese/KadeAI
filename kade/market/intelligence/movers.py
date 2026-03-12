"""Most-active and mover normalization."""

from __future__ import annotations

from kade.market.intelligence.models import SymbolActivity, SymbolMover


class MoversNormalizer:
    def __init__(self, config: dict[str, object]) -> None:
        self.top_movers_limit = int(config.get("top_movers_limit", 10))
        self.most_active_limit = int(config.get("most_active_limit", 10))

    def movers(self, raw_items: list[dict[str, object]], source: str, generated_at: str) -> list[SymbolMover]:
        items: list[SymbolMover] = []
        for item in raw_items[: self.top_movers_limit]:
            move_pct = float(item.get("change_pct", 0.0))
            items.append(
                SymbolMover(
                    timestamp=generated_at,
                    source=source,
                    symbol=str(item.get("symbol", "")).upper(),
                    move_pct=move_pct,
                    last_price=self._to_float(item.get("price")),
                    volume=self._to_float(item.get("volume")),
                    direction="up" if move_pct >= 0 else "down",
                    mover_type=str(item.get("mover_type", "top_mover")),
                    debug={"raw": dict(item)},
                )
            )
        return items

    def most_active(self, raw_items: list[dict[str, object]], source: str, generated_at: str) -> list[SymbolActivity]:
        items: list[SymbolActivity] = []
        for item in raw_items[: self.most_active_limit]:
            items.append(
                SymbolActivity(
                    timestamp=generated_at,
                    source=source,
                    symbol=str(item.get("symbol", "")).upper(),
                    volume=float(item.get("volume") or 0.0),
                    trade_count=self._to_int(item.get("trade_count")),
                    last_price=self._to_float(item.get("price")),
                )
            )
        return items

    @staticmethod
    def _to_float(value: object) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None

    @staticmethod
    def _to_int(value: object) -> int | None:
        return int(value) if isinstance(value, (int, float)) else None
