"""Cross-symbol context alignment/conflict helpers."""

from __future__ import annotations

from kade.market.intelligence.models import CrossSymbolContext


class CrossSymbolContextEngine:
    def __init__(self, config: dict[str, object]) -> None:
        mapping = config.get("sector_proxy_by_symbol", {})
        self.sector_proxy_by_symbol = {str(k).upper(): str(v).upper() for k, v in dict(mapping).items()}
        self.benchmarks = [str(symbol).upper() for symbol in list(config.get("benchmarks", ["QQQ", "SPY"]))]
        self.conflict_threshold = float(config.get("conflict_threshold_pct", 0.25))

    def evaluate(
        self,
        *,
        symbol: str,
        symbol_trend_pct: float | None,
        benchmark_trends: dict[str, float | None],
        breadth_bias: str,
        generated_at: str,
    ) -> CrossSymbolContext:
        symbol_u = symbol.upper()
        sector = self.sector_proxy_by_symbol.get(symbol_u)
        reasons: list[str] = []

        deltas: dict[str, float] = {}
        for benchmark in self.benchmarks:
            benchmark_trend = benchmark_trends.get(benchmark)
            if symbol_trend_pct is None or benchmark_trend is None:
                continue
            deltas[benchmark] = float(symbol_trend_pct) - float(benchmark_trend)

        if not deltas:
            label = "insufficient_data"
            reasons.append("missing benchmark or symbol trend")
        else:
            same_direction_count = sum(
                1 for benchmark in deltas if (symbol_trend_pct or 0.0) * (benchmark_trends.get(benchmark) or 0.0) >= 0
            )
            if same_direction_count == len(deltas) and max(abs(delta) for delta in deltas.values()) <= self.conflict_threshold:
                label = "aligned"
                reasons.append("symbol direction agrees with benchmark tape")
            elif same_direction_count == 0:
                label = "conflict"
                reasons.append("symbol direction conflicts with benchmark tape")
            else:
                label = "mixed"
                reasons.append("symbol has partial alignment vs benchmark tape")

        if breadth_bias == "risk_off" and (symbol_trend_pct or 0.0) > 0:
            label = "conflict"
            reasons.append("upside move fights risk_off breadth")
        elif breadth_bias == "risk_on" and (symbol_trend_pct or 0.0) < 0:
            label = "conflict"
            reasons.append("downside move fights risk_on breadth")

        return CrossSymbolContext(
            timestamp=generated_at,
            source="cross_symbol_context_engine",
            symbol=symbol_u,
            benchmark_symbols=list(self.benchmarks),
            sector_proxy=sector,
            alignment_label=label,
            reasons=reasons,
            debug={"symbol_trend_pct": symbol_trend_pct, "benchmark_trends": benchmark_trends, "deltas": deltas, "breadth_bias": breadth_bias},
        )
