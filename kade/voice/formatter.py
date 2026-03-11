"""Speech-friendly deterministic response formatting."""

from __future__ import annotations

from kade.voice.models import RoutedCommand, SpokenResponse


class SpokenResponseFormatter:
    def format(self, routed: RoutedCommand, mode: str) -> SpokenResponse:
        response_type = routed.response_type
        payload = routed.response_payload

        if response_type == "mode_change":
            text = f"Switching to {routed.mode_after} mode."
        elif response_type == "done_for_day":
            text = "Understood. Marking you done for the day and standing by."
        elif response_type == "emergency_shutdown":
            text = "Emergency shutdown confirmed. Disabling trading workflows now."
        elif response_type == "radar_alert":
            top = payload.get("top_symbol") or payload.get("symbol") or "none"
            summary = payload.get("summary") or "No high-conviction setup yet."
            text = f"Radar top setup is {top}. {summary}"
        elif response_type == "advisor_summary":
            summary = payload.get("summary") or "Signals are mixed right now."
            text = str(summary)
        elif response_type == "memory_summary":
            watch = payload.get("watching") or []
            text = "You were watching " + ", ".join(str(item) for item in watch) if watch else "No active watchlist notes right now."
        else:
            text = str(payload.get("summary") or payload.get("message") or "Status is stable.")

        return SpokenResponse(text=self._apply_mode(text, mode), mode=mode, response_type=response_type)

    def _apply_mode(self, text: str, mode: str) -> str:
        cleaned = " ".join(text.split())
        if mode == "quiet":
            return cleaned.split(".")[0].strip() + "."
        if mode == "advisor":
            return cleaned
        if mode == "analyst":
            if cleaned.endswith("."):
                return cleaned + " Monitoring for confirmation and invalidation conditions."
            return cleaned + ". Monitoring for confirmation and invalidation conditions."
        return cleaned
