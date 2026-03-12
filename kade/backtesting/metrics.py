"""Metric aggregation helpers for deterministic calibration reports."""

from __future__ import annotations

from collections import defaultdict

from kade.backtesting.models import OpinionEvaluationRecord, RadarEvaluationRecord, ScenarioEvaluationRecord


def _rate(hit: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(hit / total, 4)


def opinion_metrics(records: list[OpinionEvaluationRecord]) -> dict[str, object]:
    by_stance: dict[str, list[OpinionEvaluationRecord]] = defaultdict(list)
    by_plausibility: dict[str, list[OpinionEvaluationRecord]] = defaultdict(list)
    for record in records:
        stance = str(record.opinion.get("stance", "unknown"))
        plausibility = str(record.opinion.get("target_plausibility", "unknown"))
        by_stance[stance].append(record)
        by_plausibility[plausibility].append(record)

    stance_distribution = {k: len(v) for k, v in by_stance.items()}
    hit_rate_by_stance = {k: _rate(sum(1 for r in v if r.target_hit), len(v)) for k, v in by_stance.items()}
    hit_rate_by_plausibility = {k: _rate(sum(1 for r in v if r.target_hit), len(v)) for k, v in by_plausibility.items()}

    strong_agree = [r for r in records if str(r.opinion.get("stance")) in {"strong", "agree"}]
    false_positive_rate = _rate(sum(1 for r in strong_agree if not r.target_hit), len(strong_agree))

    avoided = [r for r in records if str(r.opinion.get("stance")) in {"pass", "cautious"}]
    avoidance_usefulness = _rate(sum(1 for r in avoided if not r.target_hit), len(avoided))

    avg_target_distance_by_result: dict[str, float] = {}
    grouped: dict[str, list[float]] = defaultdict(list)
    for r in records:
        req = r.request
        current = float(req.get("current_price", 0.0) or 0.0)
        target = float(req.get("target_price", 0.0) or 0.0)
        if current > 0:
            grouped[r.realized_outcome].append(abs(target - current) / current * 100.0)
    for label, values in grouped.items():
        avg_target_distance_by_result[label] = round(sum(values) / len(values), 4)

    return {
        "count": len(records),
        "stance_distribution": stance_distribution,
        "hit_rate_by_stance": hit_rate_by_stance,
        "hit_rate_by_plausibility": hit_rate_by_plausibility,
        "average_target_distance_by_result": avg_target_distance_by_result,
        "false_positive_rate_strong_agree": false_positive_rate,
        "pass_cautious_avoidance_usefulness": avoidance_usefulness,
    }


def scenario_metrics(records: list[ScenarioEvaluationRecord]) -> dict[str, object]:
    if not records:
        return {"count": 0}

    bucket_hits: dict[str, int] = defaultdict(int)
    bucket_counts: dict[str, int] = defaultdict(int)
    dte_perf: dict[str, list[float]] = defaultdict(list)
    delta_perf: dict[str, list[float]] = defaultdict(list)

    top_useful = 0
    directional_useful = 0
    for r in records:
        if r.top_rank_useful:
            top_useful += 1
        if r.target_hit or r.realized_outcome == "partial_move":
            directional_useful += 1
        bucket = r.bucket_winner
        bucket_counts[bucket] += 1
        if r.target_hit:
            bucket_hits[bucket] += 1

        candidates = list(r.board.get("candidates", []))
        if candidates:
            top = candidates[0]
            dte_perf[f"dte_{top.get('dte', 'unknown')}"] += [1.0 if r.target_hit else 0.0]
            delta = abs(float(top.get("delta", 0.0) or 0.0))
            delta_bucket = "low" if delta < 0.35 else "mid" if delta <= 0.6 else "high"
            delta_perf[delta_bucket] += [1.0 if r.target_hit else 0.0]

    return {
        "count": len(records),
        "target_hit_rate": _rate(sum(1 for r in records if r.target_hit), len(records)),
        "directional_usefulness_rate": _rate(directional_useful, len(records)),
        "top_ranked_candidate_usefulness": _rate(top_useful, len(records)),
        "bucket_usefulness": {k: _rate(bucket_hits[k], v) for k, v in bucket_counts.items()},
        "dte_bucket_performance": {k: round(sum(v) / len(v), 4) for k, v in dte_perf.items() if v},
        "delta_bucket_performance": {k: round(sum(v) / len(v), 4) for k, v in delta_perf.items() if v},
    }


def radar_metrics(records: list[RadarEvaluationRecord]) -> dict[str, object]:
    if not records:
        return {"count": 0}
    score_buckets: dict[str, list[bool]] = defaultdict(list)
    alignment_buckets: dict[str, list[bool]] = defaultdict(list)
    setup_buckets: dict[str, list[bool]] = defaultdict(list)
    regime_buckets: dict[str, list[bool]] = defaultdict(list)

    for r in records:
        signal = r.signal
        score = float(signal.get("score", signal.get("confidence", 0.0)) or 0.0)
        score_bucket = "high" if score >= 70 else "medium" if score >= 50 else "low"
        score_buckets[score_bucket].append(r.target_hit)
        alignment_buckets[str(signal.get("alignment_label", "unknown"))].append(r.target_hit)
        for tag in list(signal.get("setup_tags", [])):
            setup_buckets[str(tag)].append(r.target_hit)
        regime_buckets[str(signal.get("regime_fit", signal.get("regime_fit_label", "unknown")))].append(r.target_hit)

    return {
        "count": len(records),
        "top_signal_hit_rate": _rate(sum(1 for r in records if r.target_hit), len(records)),
        "score_bucket_hit_rate": {k: _rate(sum(v), len(v)) for k, v in score_buckets.items()},
        "alignment_bucket_hit_rate": {k: _rate(sum(v), len(v)) for k, v in alignment_buckets.items()},
        "setup_tag_hit_rate": {k: _rate(sum(v), len(v)) for k, v in setup_buckets.items()},
        "regime_fit_hit_rate": {k: _rate(sum(v), len(v)) for k, v in regime_buckets.items()},
    }
