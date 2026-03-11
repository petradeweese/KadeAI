"""Structured voice models for Phase 6 orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class WakeWordEvent:
    wake_word: str
    detected_at: datetime
    source: str = "mock"


@dataclass
class Transcript:
    text: str
    received_at: datetime
    provider: str
    confidence: float = 1.0
    is_final: bool = True
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass
class RoutedCommand:
    intent: str
    command: str
    response_type: str
    response_payload: dict[str, object] = field(default_factory=dict)
    mode_after: str | None = None


@dataclass
class SpokenResponse:
    text: str
    mode: str
    response_type: str


@dataclass
class VoiceCommandEvent:
    intent: str
    command: str
    transcript: str
    spoken_response: str
    happened_at: datetime


@dataclass
class VoiceSessionState:
    listening_mode: str = "always_on"
    wake_state: str = "passive_listening"
    current_mode: str = "advisor"
    wake_word: str = "Kade"
    command_window_ms: int = 8_000
    cooldown_ms: int = 1_000
    self_trigger_prevention: bool = True
    command_window_opened_at: datetime | None = None
    cooldown_until: datetime | None = None
    done_for_day: bool = False
    emergency_shutdown: bool = False
    last_transcript: str | None = None
    last_spoken_response: str | None = None
    recent_events: list[VoiceCommandEvent] = field(default_factory=list)

    def can_accept_wake(self, now: datetime) -> bool:
        return not self.cooldown_until or now >= self.cooldown_until

    def open_command_window(self, now: datetime) -> None:
        self.wake_state = "command_window_open"
        self.command_window_opened_at = now

    def close_command_window(self, now: datetime) -> None:
        self.wake_state = "passive_listening"
        self.command_window_opened_at = None
        self.cooldown_until = now + timedelta(milliseconds=self.cooldown_ms)

    def command_window_active(self, now: datetime) -> bool:
        if self.wake_state != "command_window_open" or not self.command_window_opened_at:
            return False
        elapsed = now - self.command_window_opened_at
        return elapsed <= timedelta(milliseconds=self.command_window_ms)
