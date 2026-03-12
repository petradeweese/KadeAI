"""Narrative summaries built from deterministic structured payloads."""

from __future__ import annotations

import json
from hashlib import sha1

from kade.integrations.llm import LLMProvider
from kade.utils.time import utc_now_iso


class NarrativeSummaryService:
    def __init__(self, provider: LLMProvider, usage_config: dict[str, object] | None = None) -> None:
        usage = usage_config or {}
        self.provider = provider
        self.narrative_summaries_enabled = bool(usage.get("narrative_summaries_enabled", True))
        self.allow_trade_logic_override = bool(usage.get("allow_trade_logic_override", False))

    def summarize(self, summary_type: str, payload: dict[str, object] | None) -> dict[str, object]:
        structured_payload = dict(payload or {})
        deterministic_text = self._fallback(summary_type, structured_payload)
        result = {
            "summary_id": f"{summary_type}-{sha1(json.dumps(structured_payload, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:10]}",
            "summary_type": summary_type,
            "generated_at": utc_now_iso(),
            "narrative_text": deterministic_text,
            "deterministic_text": deterministic_text,
            "source": "deterministic",
            "provider_name": self.provider.provider_name,
            "model": getattr(self.provider, "model", self.provider.provider_name),
            "llm_used": False,
            "allow_trade_logic_override": self.allow_trade_logic_override,
            "core_payload_preserved": True,
            "payload_keys": sorted(structured_payload.keys()),
        }
        if not self.narrative_summaries_enabled:
            result["disabled_reason"] = "narrative_summaries_disabled"
            return result

        prompt = self._prompt(summary_type, structured_payload, deterministic_text)
        generation = self.provider.generate(
            prompt=prompt,
            system_prompt=(
                "You are generating operator-facing narrative summaries for a deterministic trading system. "
                "Do not invent new trade actions. Do not override deterministic fields. Summarize only what is present."
            ),
            temperature=0.0,
            max_tokens=180,
        )
        result["generation"] = generation.as_dict()
        if generation.success and generation.content.strip():
            result["narrative_text"] = generation.content.strip()
            result["source"] = generation.provider_name
            result["provider_name"] = generation.provider_name
            result["model"] = generation.model
            result["llm_used"] = True
        else:
            result["error"] = generation.error
            result["finish_reason"] = generation.finish_reason
        return result

    @staticmethod
    def _prompt(summary_type: str, payload: dict[str, object], fallback: str) -> str:
        return (
            f"Summary type: {summary_type}\n"
            "Structured payload:\n"
            f"{json.dumps(payload, sort_keys=True, default=str)}\n"
            "Deterministic baseline:\n"
            f"{fallback}\n"
            "Write a concise operator narrative summary that preserves the same meaning."
        )

    def _fallback(self, summary_type: str, payload: dict[str, object]) -> str:
        if summary_type == "premarket_gameplan":
            headline = str(dict(payload.get("summary", {})).get("headline", "Premarket gameplan generated."))
            posture = str(dict(payload.get("market_posture", {})).get("posture_label", "unknown"))
            watchlist = [str(item.get("symbol")) for item in list(payload.get("watchlist_priorities", []))[:3] if isinstance(item, dict)]
            return f"{headline} Posture {posture}. Top watchlist: {', '.join(watchlist) if watchlist else 'none'}."
        if summary_type == "market_intelligence":
            regime = str(dict(payload.get("regime", {})).get("regime_label", "unknown"))
            confidence = dict(payload.get("regime", {})).get("regime_confidence", "unknown")
            movers = [str(item.get("symbol")) for item in list(payload.get("top_movers", []))[:3] if isinstance(item, dict)]
            return f"Market regime is {regime} with confidence {confidence}. Top movers: {', '.join(movers) if movers else 'none'}."
        if summary_type == "strategy_intelligence":
            trades = dict(payload.get("recent_trades_summary", {})).get("trade_count", 0)
            win_rate = dict(payload.get("recent_trades_summary", {})).get("win_rate", 0.0)
            calibration = dict(payload.get("plan_calibration_summary", {})).get("target_realism", "unknown")
            return f"Strategy snapshot covers {trades} trades with win rate {win_rate}. Target realism is {calibration}."
        if summary_type == "visual_explainability":
            symbol = str(payload.get("symbol", "unknown"))
            view_type = str(payload.get("view_type", "unknown"))
            charts = list(payload.get("charts", []))
            overlays = sum(len(list(item.get("overlays", []))) for item in charts if isinstance(item, dict))
            return f"Visual explanation for {symbol} in {view_type} view includes {len(charts)} charts and {overlays} overlays."
        return "Structured narrative summary generated from deterministic payload."
