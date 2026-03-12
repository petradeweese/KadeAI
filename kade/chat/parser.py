from __future__ import annotations

from kade.chat.models import InterpretedAction


class ChatIntentParser:
    """Maps natural language into deterministic command intents.

    This parser never decides trade logic values; it only maps user language to
    existing deterministic handlers.
    """

    def parse(self, text: str) -> InterpretedAction:
        normalized = text.strip()
        lowered = normalized.lower()
        tokens = normalized.split()

        if not normalized:
            return InterpretedAction(intent="invalid", source="heuristic", confidence=1.0)

        if lowered.startswith(("status", "radar", "trade_idea", "target_move", "trade_plan", "trade_plan_check", "trade_review", "visual_explain", "premarket_gameplan", "strategy_analysis")):
            return InterpretedAction(intent="explicit_command", payload={"command": normalized}, source="explicit", confidence=1.0)

        if "premarket" in lowered or "morning" in lowered:
            return InterpretedAction(intent="premarket_gameplan", source="heuristic", confidence=0.82)
        if "market" in lowered and ("doing" in lowered or "overview" in lowered):
            return InterpretedAction(intent="status", payload={"command": "status"}, source="heuristic", confidence=0.7)
        if "radar" in lowered or "setups" in lowered:
            return InterpretedAction(intent="radar", payload={"command": "radar"}, source="heuristic", confidence=0.72)
        if "visual" in lowered or "show" in lowered:
            symbol = _extract_symbol(tokens)
            if symbol:
                return InterpretedAction(intent="visual_explain", payload={"symbol": symbol}, source="heuristic", confidence=0.75)
        if "trade plan" in lowered or "plan" in lowered:
            symbol = _extract_symbol(tokens)
            payload: dict[str, object] = {}
            if symbol:
                payload["symbol"] = symbol
            return InterpretedAction(intent="trade_plan", payload=payload, source="heuristic", confidence=0.7)
        if "put" in lowered or "call" in lowered or "trade idea" in lowered or "think about" in lowered or "consider" in lowered:
            symbol = _extract_symbol(tokens)
            payload: dict[str, object] = {}
            if symbol:
                payload["symbol"] = symbol
            if "put" in lowered:
                payload["direction"] = "put"
            if "call" in lowered:
                payload["direction"] = "call"
            return InterpretedAction(intent="trade_idea", payload=payload, source="heuristic", confidence=0.73)
        if "strategy" in lowered:
            return InterpretedAction(intent="strategy_analysis", source="heuristic", confidence=0.67)

        return InterpretedAction(intent="status", payload={"command": "status"}, source="fallback", confidence=0.5)


def _extract_symbol(tokens: list[str]) -> str | None:
    for token in tokens:
        clean = "".join(ch for ch in token if ch.isalpha()).upper()
        if 1 < len(clean) <= 5 and clean.isupper() and clean not in {"WHAT", "SHOW", "TRADE", "ABOUT", "WITHIN", "HOUR", "MARKET", "MORNING", "SHOULD"}:
            return clean
    return None
