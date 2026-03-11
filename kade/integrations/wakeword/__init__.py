"""Wake-word provider interfaces."""

from kade.integrations.wakeword.base import WakeWordDetector
from kade.integrations.wakeword.mock import MockWakeWordDetector

__all__ = ["MockWakeWordDetector", "WakeWordDetector"]
