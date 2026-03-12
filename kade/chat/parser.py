from __future__ import annotations

import re

from kade.chat.models import InterpretedAction


class ChatIntentParser:
    """Maps natural language into deterministic command intents.

    This parser never decides trade logic values; it only maps user language to
    existing deterministic handlers.
    """

    def parse(self, text: str) -> InterpretedAction:
        normalized = text.strip()
        lowered = normalized.lower()
        extracted = _extract_trade_context(normalized)

        if not normalized:
            return InterpretedAction(intent="invalid", source="heuristic", confidence=1.0)

        if lowered.startswith(("status", "radar", "trade_idea", "target_move", "trade_plan", "trade_plan_check", "trade_review", "visual_explain", "premarket_gameplan", "strategy_analysis")):
            return InterpretedAction(intent="explicit_command", payload={"command": normalized}, source="explicit", confidence=1.0)

        if any(phrase in lowered for phrase in ("how did", "post-trade", "post trade", "review this trade", "grade this trade")):
            return InterpretedAction(intent="trade_review", payload=_trade_payload_from_context(extracted), source="heuristic", confidence=0.76)
        if any(phrase in lowered for phrase in ("performance", "stats", "expectancy", "win rate", "strategy")):
            return InterpretedAction(intent="strategy_analysis", source="heuristic", confidence=0.72)
        if any(phrase in lowered for phrase in ("manage", "tracking", "still valid", "active trade", "plan check")):
            return InterpretedAction(intent="trade_plan_check", payload=_trade_payload_from_context(extracted), source="heuristic", confidence=0.74)
        if "premarket" in lowered or "morning" in lowered:
            return InterpretedAction(intent="premarket_gameplan", source="heuristic", confidence=0.82)
        if "market" in lowered and ("doing" in lowered or "overview" in lowered):
            return InterpretedAction(intent="status", payload={"command": "status"}, source="heuristic", confidence=0.7)
        if "radar" in lowered or "setups" in lowered:
            return InterpretedAction(intent="radar", payload={"command": "radar"}, source="heuristic", confidence=0.72)
        if "visual" in lowered or "show" in lowered:
            symbol = extracted.get("symbol")
            if symbol:
                return InterpretedAction(intent="visual_explain", payload={"symbol": symbol}, source="heuristic", confidence=0.75)
        if "trade plan" in lowered or "plan" in lowered:
            return InterpretedAction(intent="trade_plan", payload=_trade_payload_from_context(extracted), source="heuristic", confidence=0.7)
        if any(phrase in lowered for phrase in ("put", "call", "trade idea", "think about", "consider", "long", "short", "bullish", "bearish")):
            return InterpretedAction(intent="trade_idea", payload=_trade_payload_from_context(extracted), source="heuristic", confidence=0.73)

        return InterpretedAction(intent="status", payload={"command": "status"}, source="fallback", confidence=0.5)


def _trade_payload_from_context(context: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in ("symbol", "direction", "target", "horizon_minutes", "horizon_label"):
        value = context.get(key)
        if value is not None and value != "":
            payload[key] = value
    return payload


def _extract_trade_context(text: str) -> dict[str, object]:
    tokens = re.findall(r"[A-Za-z]+", text)
    symbol = _extract_symbol(tokens)
    direction = _extract_direction(text)
    target = _extract_target(text)
    horizon = _extract_horizon(text)
    return {"symbol": symbol, "direction": direction, "target": target, **horizon}


def _extract_symbol(tokens: list[str]) -> str | None:
    stopwords = {
        "DO",
        "YOU",
        "YOUR",
        "HI",
        "HEY",
        "HELLO",
        "KADE",
        "THINK",
        "WHAT",
        "SHOW",
        "ABOUT",
        "TRADE",
        "IDEA",
        "WITHIN",
        "HOUR",
        "HOURS",
        "MINUTE",
        "MINUTES",
        "MARKET",
        "MORNING",
        "SHOULD",
        "CONSIDER",
        "CALL",
        "PUT",
        "LONG",
        "SHORT",
        "BULLISH",
        "BEARISH",
        "EXIT",
        "TARGET",
        "OF",
        "TODAY",
        "CLOSE",
        "NEXT",
        "ON",
        "AN",
        "A",
    }
    for token in tokens:
        clean = "".join(ch for ch in token if ch.isalpha()).upper()
        if 1 < len(clean) <= 5 and clean not in stopwords:
            return clean
    return None


def _extract_direction(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\b(put|short|bearish|downside)\b", lowered):
        return "put"
    if re.search(r"\b(call|long|bullish|upside)\b", lowered):
        return "call"
    return None


def _extract_horizon(text: str) -> dict[str, object]:
    lowered = text.lower()
    if re.search(r"\b(within|in|over|next)\s+an?\s+hour\b", lowered):
        return {"horizon_minutes": 60, "horizon_label": "within_an_hour"}

    minute_match = re.search(r"\b(within|in|over|next)\s+(\d{1,3})\s*(minute|minutes|min|mins)\b", lowered)
    if minute_match:
        minutes = int(minute_match.group(2))
        return {"horizon_minutes": minutes, "horizon_label": f"next_{minutes}_minutes"}

    hour_match = re.search(r"\b(within|in|over|next)\s+(\d{1,2})\s*(hour|hours|hr|hrs)\b", lowered)
    if hour_match:
        hours = int(hour_match.group(2))
        return {"horizon_minutes": hours * 60, "horizon_label": f"next_{hours}_hours"}

    if "by close" in lowered or "into the close" in lowered:
        return {"horizon_label": "by_close"}
    if "today" in lowered:
        return {"horizon_label": "today"}
    return {}


def _extract_target(text: str) -> float | None:
    lowered = text.lower()
    match = re.search(r"\b(?:exit|target)\s*(?:of\s*)?(\d{1,5}(?:\.\d{1,4})?)\b", lowered)
    if not match:
        return None
    return float(match.group(1))
