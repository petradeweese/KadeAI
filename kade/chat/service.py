from __future__ import annotations

import json

from kade.chat.formatter import ChatFormatter
from kade.chat.models import ChatResponse, InterpretedAction
from kade.chat.parser import ChatIntentParser
from kade.chat.router import ChatActionRouter
from kade.integrations.llm.base import LLMProvider
from kade.runtime.interaction import InteractionOrchestrator


class ChatService:
    def __init__(
        self,
        interaction: InteractionOrchestrator,
        llm_provider: LLMProvider | None = None,
        llm_enabled: bool = True,
    ) -> None:
        self.interaction = interaction
        self.llm_provider = llm_provider
        self.llm_enabled = llm_enabled
        self.parser = ChatIntentParser()
        self.router = ChatActionRouter()
        self.formatter = ChatFormatter()

    def handle_message(self, text: str) -> ChatResponse:
        interpreted = self._interpret(text)
        panel_payload = self.router.to_panel_payload(interpreted)
        response = self.interaction.submit_text_panel_command(panel_payload)

        deterministic_reply = self.formatter.format_deterministic(response, interpreted.intent)
        final_reply = deterministic_reply
        used_llm_formatting = False
        fallback_used = False

        if self.llm_enabled and self.llm_provider is not None:
            generation = self.llm_provider.generate(
                prompt=(
                    "Summarize the deterministic Kade output in plain language without changing any decisions. "
                    f"Intent: {interpreted.intent}\n"
                    f"Deterministic response: {json.dumps(response.get('raw_result', {}), default=str)}"
                ),
                system_prompt="You are a formatting assistant. Never invent or override trading decisions.",
                temperature=0.0,
                max_tokens=220,
            )
            if generation.success and generation.content.strip():
                final_reply = generation.content.strip()
                used_llm_formatting = True
            else:
                fallback_used = True

        return ChatResponse(
            reply=final_reply,
            interpreted_action=interpreted,
            command_response=response,
            used_llm_for_parsing=interpreted.source == "llm",
            used_llm_for_formatting=used_llm_formatting,
            fallback_used=fallback_used,
        )

    def _interpret(self, text: str) -> InterpretedAction:
        parsed = self.parser.parse(text)
        if parsed.intent == "explicit_command" or not self.llm_enabled or self.llm_provider is None:
            return parsed

        generation = self.llm_provider.generate(
            prompt=(
                "Map the user request to one intent in this whitelist only: "
                "status,radar,premarket_gameplan,trade_idea,target_move,trade_plan,trade_plan_check,trade_review,visual_explain,strategy_analysis. "
                "Return strict JSON: {\"intent\":\"...\",\"symbol\":\"\",\"direction\":\"\"}. "
                "No trade decisioning. User request: "
                f"{text}"
            ),
            system_prompt="You are an intent parser. Only map language to deterministic action names.",
            temperature=0.0,
            max_tokens=80,
        )
        if not generation.success:
            return parsed

        try:
            payload = json.loads(generation.content)
        except json.JSONDecodeError:
            return parsed

        intent = str(payload.get("intent", "")).strip()
        if intent not in {
            "status",
            "radar",
            "premarket_gameplan",
            "trade_idea",
            "target_move",
            "trade_plan",
            "trade_plan_check",
            "trade_review",
            "visual_explain",
            "strategy_analysis",
        }:
            return parsed

        mapped_payload: dict[str, object] = {}
        if payload.get("symbol"):
            mapped_payload["symbol"] = str(payload["symbol"]).upper()
        if payload.get("direction"):
            mapped_payload["direction"] = str(payload["direction"]).lower()
        return InterpretedAction(intent=intent, payload=mapped_payload, source="llm", confidence=0.85)
