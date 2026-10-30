"""Wake-word detection and push-to-talk controller for DADUS."""
from abc import ABC, abstractmethod
import threading
import time
import logging
from typing import Callable, Optional
from app.config.settings import settings
from app.voice.stt import get_stt_provider, BaseSTT

logger = logging.getLogger("DADUS.WakeWord")

class BaseWakeWord(ABC):
    """Abstract interface for wake-word engines."""

    @abstractmethod
    def start_listening(self, callback: Callable[[str], None]) -> None:
        """Start listening for the wake word."""
        pass

    @abstractmethod
    def stop_listening(self) -> None:
        """Stop listening."""
        pass

class KeywordWakeWord(BaseWakeWord):
    """
    Continuous background listener that triggers on 'Hey Dadus' or 'Dadus'.
    Extracts the command directly if uttered in the same sentence
    (e.g. 'Hey Dadus, open Chrome' triggers with 'open Chrome').
    """

    def __init__(self, stt_provider: Optional[BaseSTT] = None):
        self.stt = stt_provider or get_stt_provider()
        self.wake_phrases = ["hey dadus", "dadus", "ok dadus", "hi dadus"]
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_trigger_time: float = 0.0

    def start_listening(self, callback: Callable[[str], None]) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, args=(callback,), daemon=True)
        self._thread.start()
        logger.info(f"Wake-word engine started. Listening for '{settings.WAKE_PHRASE}'...")

    def stop_listening(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Wake-word engine stopped.")

    def _listen_loop(self, callback: Callable[[str], None]) -> None:
        from app.voice.tts import get_tts_provider

        while self._running:
            try:
                # Capture speech segment
                text = self.stt.listen_and_transcribe(timeout=3, phrase_time_limit=8)
                if not text:
                    continue

                now = time.time()
                # Debounce to prevent duplicate repeated commands within 1.5s
                if now - self._last_trigger_time < 1.5:
                    logger.debug("Ignoring duplicate phrase within debounce window")
                    continue

                lower = text.lower()
                detected = False
                command = ""

                # Robust phonetic pattern matching for 'Hey Dadus' to catch STT acoustic variants
                import re
                wake_pattern = r"\b(hey|hi|ok|hello)?\s*(dadus|dadas|dad\s*is|dadu|datus|daddus|dartus|status|that\s*is)\b"
                match = re.search(wake_pattern, lower)
                if match:
                    detected = True
                    command = text[match.end():].strip(" ,.?!")
                else:
                    # Fallback check against configured phrase list
                    for phrase in self.wake_phrases:
                        if phrase in lower:
                            detected = True
                            idx = lower.find(phrase) + len(phrase)
                            command = text[idx:].strip(" ,.?!")
                            break

                if detected:
                    self._last_trigger_time = now
                    # Interrupt any ongoing assistant speech
                    try:
                        get_tts_provider().stop()
                    except Exception:
                        pass
                    logger.info(f"Wake phrase recognized! Command uttered: '{command}'")
                    callback(command)
                    time.sleep(0.5)
            except Exception as ex:
                logger.debug(f"Wake word loop cycle exception: {ex}")
                time.sleep(0.5)

class PushToTalkWakeWord(BaseWakeWord):
    """
    Manual push-to-talk mode.
    Triggered explicitly via UI click, API call, or hotkey.
    Never blocks or locks up development.
    """

    def __init__(self, stt_provider: Optional[BaseSTT] = None):
        self.stt = stt_provider or get_stt_provider()

    def start_listening(self, callback: Callable[[str], None]) -> None:
        pass  # Controlled explicitly via trigger_once

    def stop_listening(self) -> None:
        pass

    def trigger_once(self, callback: Callable[[str], None]) -> Optional[str]:
        """Record a single command, interrupt playback, and pass to callback."""
        from app.voice.tts import get_tts_provider
        try:
            get_tts_provider().stop()
        except Exception:
            pass

        logger.info("Push-to-talk activated. Listening...")
        text = self.stt.listen_and_transcribe(timeout=5, phrase_time_limit=10)
        if text:
            logger.info(f"Push-to-talk transcribed: '{text}'")
            callback(text)
            return text
        return None

def get_wakeword_provider() -> BaseWakeWord:
    """Factory to retrieve configured wake-word engine."""
    provider = settings.WAKEWORD_PROVIDER.lower()
    if provider == "keyword":
        return KeywordWakeWord()
    else:
        return PushToTalkWakeWord()
