"""Operator-facing radar explanation synthesis."""

from __future__ import annotations

from datetime import datetime, timezone


class RadarExplanationBuilder:
    def __init__(self, config: dict) -> None:
        self.config = config

    def build(
        self,
        symbol: str,
        score: float,
        setup_tags: list[str],
        alignment_label: str,
        regime_fit_label: str,
        trap_risk: str,
        contributions: dict[str, float],
        timestamp: datetime | None,
    ) -> dict[str, object]:
        max_reasons = int(self.config.get("max_reasons", 3))
        positive = sorted(((k, v) for k, v in contributions.items() if v > 0), key=lambda item: item[1], reverse=True)
        negative = sorted(((k, v) for k, v in contributions.items() if v < 0), key=lambda item: item[1])

        supporting = [self._reason_text(key, value) for key, value in positive[:max_reasons]]
        cautionary = [self._reason_text(key, value) for key, value in negative[:max_reasons]]

        return {
            "symbol": symbol,
            "setup_tags": setup_tags,
            "confidence": round(score, 2),
            "alignment_label": alignment_label,
            "regime_fit_label": regime_fit_label,
            "supporting_reasons": supporting,
            "cautionary_reasons": cautionary,
            "trap_risk": trap_risk,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
            "summary": self._summary(setup_tags, alignment_label, regime_fit_label, trap_risk),
        }

    @staticmethod
    def _reason_text(key: str, value: float) -> str:
        normalized = key.replace("_", " ")
        direction = "boost" if value > 0 else "drag"
        return f"{normalized}: {direction} {abs(value):.2f}"

    @staticmethod
    def _summary(setup_tags: list[str], alignment_label: str, regime_fit_label: str, trap_risk: str) -> str:
        tag_text = ", ".join(setup_tags[:2]) if setup_tags else "untagged setup"
        return f"{tag_text}; alignment={alignment_label}; regime_fit={regime_fit_label}; trap={trap_risk}"
