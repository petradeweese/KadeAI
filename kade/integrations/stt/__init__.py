"""Speech-to-text provider interfaces."""

from kade.integrations.stt.base import STTProvider
from kade.integrations.stt.mock import MockSTTProvider

__all__ = ["MockSTTProvider", "STTProvider"]
