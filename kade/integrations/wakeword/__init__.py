"""Wake-word provider interfaces."""

from kade.integrations.wakeword.base import WakeWordDetector
from kade.integrations.wakeword.mock import MockWakeWordDetector
from kade.integrations.wakeword.porcupine import PorcupineWakeWordDetector

__all__ = ["MockWakeWordDetector", "PorcupineWakeWordDetector", "WakeWordDetector"]
