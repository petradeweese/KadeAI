"""Style profile scaffolding for deterministic language preferences."""

from __future__ import annotations

from kade.brain.models import StyleProfile


class StyleProfileManager:
    def __init__(self, config: dict) -> None:
        self.config = config
        defaults = config.get("style_profile", {}).get("defaults", {})
        self.active_profile = StyleProfile(
            profile_name=defaults.get("profile_name", "default"),
            tone=defaults.get("tone", "calm"),
            verbosity=defaults.get("verbosity", "balanced"),
            directness=defaults.get("directness", "direct"),
            common_phrases=list(defaults.get("common_phrases", [])),
        )

    def set_profile(self, profile: StyleProfile) -> None:
        self.active_profile = profile

    def response_guidance(self) -> dict[str, object]:
        return {
            "profile_name": self.active_profile.profile_name,
            "tone": self.active_profile.tone,
            "verbosity": self.active_profile.verbosity,
            "directness": self.active_profile.directness,
            "common_phrases": self.active_profile.common_phrases,
        }

    def apply_scaffold(self, message: str) -> str:
        if self.active_profile.verbosity == "concise":
            return message.split(".")[0].strip()
        if self.active_profile.directness == "very_direct":
            return message.replace("I would", "Do").replace("consider", "use")
        return message
