"""Text-to-speech provider interfaces."""

from kade.integrations.tts.base import TTSOutput, TTSProvider
from kade.integrations.tts.kokoro import KokoroTTSProvider

__all__ = ["KokoroTTSProvider", "TTSOutput", "TTSProvider"]
