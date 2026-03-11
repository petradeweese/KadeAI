"""Developer STT provider for deterministic testing."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.integrations.stt.base import STTProvider
from kade.voice.models import Transcript


class MockSTTProvider(STTProvider):
    provider_name = "mock"

    def __init__(self, seeded_transcripts: list[str] | None = None) -> None:
        self.seeded_transcripts = seeded_transcripts or []

    def transcribe(self, audio_hint: str) -> Transcript:
        text = self.seeded_transcripts.pop(0) if self.seeded_transcripts else audio_hint
        return Transcript(text=text, received_at=datetime.utcnow(), provider=self.provider_name)

    def developer_transcript(self, text: str) -> Transcript:
        return Transcript(text=text, received_at=datetime.utcnow(), provider=self.provider_name, metadata={"source": "developer"})

    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth(
            provider_type="stt",
            provider_name=self.provider_name,
            state="mock",
            active=active,
            metadata={"deterministic": True, "seeded_transcripts": len(self.seeded_transcripts)},
        )
