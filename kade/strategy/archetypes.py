"""Rule-based setup archetype classification."""

from __future__ import annotations

from kade.strategy.models import SetupArchetypeResult


def classify_setup_archetype(trade: dict[str, object], rules: dict[str, object] | None = None) -> SetupArchetypeResult:
    rules = rules or {}
    plan = trade.get("plan") if isinstance(trade.get("plan"), dict) else {}
    tracking = trade.get("tracking") if isinstance(trade.get("tracking"), dict) else {}
    regime = str(trade.get("regime") or plan.get("regime_fit") or "unknown").lower()
    direction = str(plan.get("direction") or trade.get("direction") or "unknown").lower()
    trigger = str(plan.get("entry_plan", {}).get("trigger_condition", plan.get("trigger_condition", ""))).lower()
    invalidation = str(plan.get("invalidation_plan", {}).get("invalidation_condition", plan.get("invalidation_concept", ""))).lower()
    target = str(plan.get("target_plan", {}).get("primary_target", plan.get("target_exit_idea", ""))).lower()
    summary = str(tracking.get("summary", "")).lower()
    reasons: list[str] = []

    label = "trend_continuation"
    confidence = 0.58

    if "opening" in trigger or "open" in trigger:
        label = "opening_drive"
        confidence = 0.72
        reasons.append("Entry trigger references open/drive behavior.")
    elif "late" in summary or "late" in trigger:
        label = "late_day_momentum"
        confidence = 0.68
        reasons.append("Tracking/trigger indicates late-session momentum context.")
    elif "news" in regime or "catalyst" in trigger:
        label = "catalyst_breakout"
        confidence = 0.74
        reasons.append("Catalyst/news context detected from regime or trigger.")
    elif "reclaim" in trigger and "vwap" in trigger:
        label = "vwap_reclaim"
        confidence = 0.79
        reasons.append("Trigger contains VWAP reclaim language.")
    elif ("reject" in trigger or "fail" in invalidation) and "vwap" in trigger:
        label = "vwap_rejection"
        confidence = 0.75
        reasons.append("VWAP rejection/failure pattern detected.")
    elif "range" in regime or "reversion" in target:
        label = "range_reversion"
        confidence = 0.67
        reasons.append("Range/reversion cues found in regime or target language.")
    elif direction == "short" and ("breakdown" in trigger or "failed" in summary):
        label = "failed_breakdown"
        confidence = 0.7
        reasons.append("Short breakdown context with failure signals in tracking.")
    elif "reversal" in trigger or "reversal" in summary:
        label = "news_reversal" if "news" in regime else "range_reversion"
        confidence = 0.66
        reasons.append("Reversal wording detected in trigger/tracking summary.")

    stance = str(plan.get("stance", "")).lower()
    if label == "trend_continuation" and ("aligned" in stance or regime.startswith("trend")):
        confidence = 0.71
        reasons.append("Trend posture aligned with regime/stance.")

    override = rules.get("label_overrides", {}).get(str(plan.get("symbol", "")).upper()) if isinstance(rules.get("label_overrides"), dict) else None
    if isinstance(override, str) and override:
        label = override
        confidence = 0.65
        reasons.append("Applied deterministic config override.")

    if not reasons:
        reasons.append("Defaulted to trend continuation due to insufficient distinctive cues.")

    return SetupArchetypeResult(archetype_label=label, confidence=round(confidence, 2), reasoning=reasons)
