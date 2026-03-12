from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str
    text: str
    timestamp: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class InterpretedAction:
    intent: str
    payload: dict[str, object] = field(default_factory=dict)
    source: str = "heuristic"
    confidence: float = 0.0


@dataclass
class ChatResponse:
    reply: str
    interpreted_action: InterpretedAction
    command_response: dict[str, object]
    used_llm_for_parsing: bool = False
    used_llm_for_formatting: bool = False
    fallback_used: bool = False
