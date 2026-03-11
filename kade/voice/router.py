"""Deterministic transcript router into existing Kade capabilities."""

from __future__ import annotations

from collections.abc import Callable

from kade.voice.models import RoutedCommand


class VoiceCommandRouter:
    def __init__(self, handlers: dict[str, Callable[..., dict[str, object]]] | None = None) -> None:
        self.handlers = handlers or {}

    def route(self, transcript_text: str, current_mode: str) -> RoutedCommand:
        normalized = transcript_text.strip().lower()
        command = normalized.removeprefix("kade").strip()

        if "analyst mode" in command:
            payload = self._call("switch_mode", mode="analyst")
            return RoutedCommand("mode_switch", command, "mode_change", payload, mode_after="analyst")
        if "quiet mode" in command:
            payload = self._call("switch_mode", mode="quiet")
            return RoutedCommand("mode_switch", command, "mode_change", payload, mode_after="quiet")
        if "advisor mode" in command:
            payload = self._call("switch_mode", mode="advisor")
            return RoutedCommand("mode_switch", command, "mode_change", payload, mode_after="advisor")

        if "i'm done for the day" in command or "im done for the day" in command:
            payload = self._call("done_for_day")
            return RoutedCommand("done_for_day", command, "done_for_day", payload)
        if "emergency shutdown" in command:
            payload = self._call("emergency_shutdown")
            return RoutedCommand("emergency_shutdown", command, "emergency_shutdown", payload)

        if "radar" in command:
            payload = self._call("radar")
            return RoutedCommand("radar", command, "radar_alert", payload)
        if "status" in command:
            payload = self._call("status")
            return RoutedCommand("status", command, "status_update", payload)

        if "what is the market doing" in command:
            payload = self._call("market_overview")
            return RoutedCommand("market_overview", command, "status_update", payload)
        if "what was i watching" in command:
            payload = self._call("memory_watchlist")
            return RoutedCommand("memory_watchlist", command, "memory_summary", payload)
        if "what do you think about" in command:
            symbol = command.replace("what do you think about", "").strip().upper()
            payload = self._call("symbol_opinion", symbol=symbol)
            payload.setdefault("symbol", symbol)
            return RoutedCommand("symbol_opinion", command, "advisor_summary", payload)
        if "what is" in command and "doing" in command:
            symbol = command.replace("what is", "").replace("doing", "").strip().upper()
            payload = self._call("symbol_status", symbol=symbol)
            payload.setdefault("symbol", symbol)
            return RoutedCommand("symbol_status", command, "status_update", payload)

        payload = self._call("fallback", mode=current_mode, transcript=command)
        return RoutedCommand("fallback", command, "status_update", payload)

    def _call(self, name: str, **kwargs: object) -> dict[str, object]:
        handler = self.handlers.get(name)
        if not handler:
            return {}
        return handler(**kwargs)
