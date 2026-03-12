"""High-level strategy analytics aggregations."""

from __future__ import annotations

from collections import Counter, defaultdict

from kade.strategy.models import DisciplineImpactSummary, RegimePerformanceSummary, SymbolPerformanceSummary
from kade.strategy.performance import avg, safe_float, win_rate

DISCIPLINED_LABELS = {"disciplined", "well_executed", "mostly_disciplined", "cancelled_correctly"}


def compute_regime_performance(trades: list[dict[str, object]]) -> list[RegimePerformanceSummary]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("regime", "unknown"))].append(trade)

    summaries: list[RegimePerformanceSummary] = []
    for regime in sorted(grouped):
        rows = grouped[regime]
        rois = [safe_float(item.get("roi")) for item in rows]
        disciplined = sum(1 for item in rows if bool(item.get("disciplined")))
        summaries.append(
            RegimePerformanceSummary(
                regime=regime,
                trade_count=len(rows),
                win_rate=win_rate(rois),
                avg_roi=avg(rois),
                disciplined_rate=round(disciplined / len(rows), 4) if rows else 0.0,
            )
        )
    return summaries


def compute_symbol_performance(trades: list[dict[str, object]]) -> list[SymbolPerformanceSummary]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("symbol", "UNKNOWN")).upper()].append(trade)

    summaries: list[SymbolPerformanceSummary] = []
    for symbol in sorted(grouped):
        rows = grouped[symbol]
        rois = [safe_float(item.get("roi")) for item in rows]
        setup_rois: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            setup_rois[str(row.get("setup_archetype", "unknown"))].append(safe_float(row.get("roi")))
        setup_means = {setup: avg(values) for setup, values in setup_rois.items()}
        best_setup = max(setup_means, key=setup_means.get) if setup_means else "unknown"
        worst_setup = min(setup_means, key=setup_means.get) if setup_means else "unknown"
        summaries.append(
            SymbolPerformanceSummary(
                symbol=symbol,
                trade_count=len(rows),
                win_rate=win_rate(rois),
                avg_roi=avg(rois),
                best_setup=best_setup,
                worst_setup=worst_setup,
            )
        )
    return summaries


def compute_discipline_impact(trades: list[dict[str, object]]) -> DisciplineImpactSummary:
    disciplined_rows = [t for t in trades if bool(t.get("disciplined"))]
    undisciplined_rows = [t for t in trades if not bool(t.get("disciplined"))]

    disciplined_rois = [safe_float(item.get("roi")) for item in disciplined_rows]
    undisciplined_rois = [safe_float(item.get("roi")) for item in undisciplined_rows]

    return DisciplineImpactSummary(
        disciplined_win_rate=win_rate(disciplined_rois),
        undisciplined_win_rate=win_rate(undisciplined_rois),
        avg_roi_disciplined=avg(disciplined_rois),
        avg_roi_undisciplined=avg(undisciplined_rois),
        disciplined_count=len(disciplined_rows),
        undisciplined_count=len(undisciplined_rows),
    )


def setup_archetype_stats(archetypes: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in archetypes:
        grouped[str(item.get("archetype_label", "unknown"))].append(item)

    out: list[dict[str, object]] = []
    for label in sorted(grouped):
        rows = grouped[label]
        rois = [safe_float(row.get("roi")) for row in rows]
        disciplines = Counter(str(row.get("discipline_label", "unknown")) for row in rows)
        out.append(
            {
                "archetype_label": label,
                "trade_count": len(rows),
                "win_rate": win_rate(rois),
                "avg_roi": avg(rois),
                "discipline_distribution": dict(disciplines),
            }
        )
    return out
