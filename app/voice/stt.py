"""Speech-to-Text (STT) provider abstractions and implementations for DADUS."""
from abc import ABC, abstractmethod
import os
import logging
from typing import Optional, List
from app.config.settings import settings

logger = logging.getLogger("DADUS.STT")

class BaseSTT(ABC):
    """Abstract interface for speech-to-text engines."""

    @abstractmethod
    def transcribe_file(self, audio_path: str) -> Optional[str]:
        """Transcribe an audio file to text."""
        pass

    @abstractmethod
    def listen_and_transcribe(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        """Capture microphone input and transcribe to text."""
        pass

class SpeechRecognitionSTT(BaseSTT):
    """STT implementation utilizing the speech_recognition library."""

    def __init__(self, language: str = "en-US"):
        import speech_recognition as sr
        self.language = language
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = settings.STT_ENERGY_THRESHOLD
        self.recognizer.dynamic_energy_threshold = settings.STT_DYNAMIC_ENERGY_THRESHOLD

    def transcribe_file(self, audio_path: str) -> Optional[str]:
        import speech_recognition as sr
        if not os.path.exists(audio_path):
            logger.error(f"Audio file does not exist: {audio_path}")
            return None

        try:
            with sr.AudioFile(audio_path) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio, language=self.language)
                return text.strip()
        except sr.UnknownValueError:
            logger.info("Speech was unintelligible")
            return None
        except sr.RequestError as ex:
            logger.error(f"Speech recognition service request error: {ex}")
            return None
        except Exception as ex:
            logger.error(f"Error transcribing audio file: {ex}")
            return None

    def listen_and_transcribe(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        import speech_recognition as sr
        try:
            with sr.Microphone() as source:
                if not getattr(self, "_calibrated", False):
                    logger.info("Calibrating microphone for ambient noise...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    self._calibrated = True
                logger.info("Listening for voice...")
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )
                logger.info("Processing captured speech...")
                text = self.recognizer.recognize_google(audio, language=self.language)
                return text.strip()
        except sr.WaitTimeoutError:
            logger.info("Listening timed out with no speech detected")
            return None
        except sr.UnknownValueError:
            logger.info("Speech was detected but could not be understood")
            return None
        except sr.RequestError as ex:
            logger.error(f"STT network service error: {ex}")
            return None
        except Exception as ex:
            logger.error(f"Microphone access error: {ex}")
            return None

class WhisperSTT(BaseSTT):
    """OpenAI Whisper cloud STT implementation."""

    def transcribe_file(self, audio_path: str) -> Optional[str]:
        if not settings.OPENAI_API_KEY:
            logger.warning("No OPENAI_API_KEY for WhisperSTT; falling back to SpeechRecognitionSTT")
            return SpeechRecognitionSTT().transcribe_file(audio_path)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
            with open(audio_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    prompt="Hey Dadus, Dadus, play music, open Chrome, take screenshot, set reminder."
                )
                return transcription.text.strip()
        except Exception as ex:
            logger.error(f"Whisper transcription error: {ex}")
            return SpeechRecognitionSTT().transcribe_file(audio_path)

    def listen_and_transcribe(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        # Records to temp file via speech_recognition then calls Whisper
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = settings.STT_ENERGY_THRESHOLD
        recognizer.dynamic_energy_threshold = settings.STT_DYNAMIC_ENERGY_THRESHOLD
        try:
            with sr.Microphone() as source:
                if not getattr(self, "_calibrated", False):
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    self._calibrated = True
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                temp_wav = str(settings.DATA_DIR / "audio" / "temp_whisper.wav")
                with open(temp_wav, "wb") as f:
                    f.write(audio.get_wav_data())
                return self.transcribe_file(temp_wav)
        except Exception as ex:
            logger.error(f"Microphone recording failed for Whisper: {ex}")
            return None

class MockSTT(BaseSTT):
    """Mock STT provider for unit tests and simulations."""

    def __init__(self, canned_inputs: Optional[List[str]] = None):
        self.queue = canned_inputs or []

    def set_inputs(self, inputs: List[str]) -> None:
        self.queue = list(inputs)

    def transcribe_file(self, audio_path: str) -> Optional[str]:
        return self.queue.pop(0) if self.queue else "Hey Dadus, open Chrome"

    def listen_and_transcribe(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        return self.queue.pop(0) if self.queue else "Hey Dadus, what is my schedule today"

def get_stt_provider(provider_name: Optional[str] = None) -> BaseSTT:
    """Factory to retrieve configured STT provider."""
    provider = (provider_name or settings.STT_PROVIDER).lower()
    if provider == "speech_recognition":
        return SpeechRecognitionSTT(language=settings.STT_LANGUAGE)
    elif provider == "whisper":
        return WhisperSTT()
    elif provider == "mock":
        return MockSTT()
    else:
        logger.warning(f"Unknown STT provider '{provider}', defaulting to SpeechRecognitionSTT")
        return SpeechRecognitionSTT()
