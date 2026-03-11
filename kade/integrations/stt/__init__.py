"""Speech-to-text provider interfaces."""

from kade.integrations.stt.base import STTProvider
from kade.integrations.stt.mock import MockSTTProvider
from kade.integrations.stt.whisper import WhisperSTTProvider

__all__ = ["MockSTTProvider", "STTProvider", "WhisperSTTProvider"]
