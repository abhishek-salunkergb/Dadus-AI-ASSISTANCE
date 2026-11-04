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
        self.recognizer.pause_threshold = 0.8

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
        recognizer.pause_threshold = 0.8
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


class DeepgramSTT(BaseSTT):
    """Deepgram Nova-2 / Nova-3 ultra-low latency speech-to-text implementation."""

    API_URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.model = model or settings.DEEPGRAM_MODEL or "nova-2"

    def _get_api_key(self) -> Optional[str]:
        key = self.api_key or settings.DEEPGRAM_API_KEY
        if key and key.strip() and not key.strip().startswith("your_"):
            return key.strip()
        return None

    def transcribe_bytes(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribes raw audio bytes with Deepgram Nova-2."""
        key = self._get_api_key()
        if not key:
            logger.info("DEEPGRAM_API_KEY is not configured; using fallback STT")
            if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("your_"):
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tf.write(audio_bytes)
                    tpath = tf.name
                res = WhisperSTT().transcribe_file(tpath)
                try:
                    os.remove(tpath)
                except Exception:
                    pass
                return res
            return None

        try:
            import requests
            headers = {
                "Authorization": f"Token {key}",
                "Content-Type": "audio/wav"
            }
            lang = settings.STT_LANGUAGE.split("-")[0] if "-" in settings.STT_LANGUAGE else settings.STT_LANGUAGE
            params = {
                "model": self.model,
                "smart_format": "true",
                "punctuate": "true",
                "filler_words": "false",
                "language": lang,
                "keywords": ["Dadus:3", "Hey Dadus:3"]
            }

            resp = requests.post(
                self.API_URL,
                headers=headers,
                params=params,
                data=audio_bytes,
                timeout=10
            )

            if resp.status_code != 200:
                logger.error(f"Deepgram STT error (HTTP {resp.status_code}): {resp.text}")
                return None

            data = resp.json()
            channels = data.get("results", {}).get("channels", [])
            if channels and channels[0].get("alternatives"):
                transcript = channels[0]["alternatives"][0].get("transcript", "")
                if transcript and transcript.strip():
                    logger.info(f"Deepgram ({self.model}) recognized: '{transcript.strip()}'")
                    return transcript.strip()

            return None
        except Exception as ex:
            logger.error(f"Deepgram request error: {ex}")
            return None

    def transcribe_file(self, audio_path: str) -> Optional[str]:
        if not self._get_api_key():
            logger.info("DEEPGRAM_API_KEY not configured; falling back to Whisper/SpeechRecognition")
            if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("your_"):
                return WhisperSTT().transcribe_file(audio_path)
            return SpeechRecognitionSTT().transcribe_file(audio_path)

        if not os.path.exists(audio_path):
            logger.error(f"Audio file does not exist: {audio_path}")
            return None

        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            return self.transcribe_bytes(audio_bytes)
        except Exception as ex:
            logger.error(f"Error reading audio file for Deepgram: {ex}")
            return None

    def listen_and_transcribe(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        if not self._get_api_key():
            if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("your_"):
                return WhisperSTT().listen_and_transcribe(timeout, phrase_time_limit)
            return SpeechRecognitionSTT().listen_and_transcribe(timeout, phrase_time_limit)

        import speech_recognition as sr
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = settings.STT_ENERGY_THRESHOLD
        recognizer.dynamic_energy_threshold = settings.STT_DYNAMIC_ENERGY_THRESHOLD
        recognizer.pause_threshold = 0.8
        try:
            with sr.Microphone() as source:
                if not getattr(self, "_calibrated", False):
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    self._calibrated = True
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                wav_bytes = audio.get_wav_data()
                return self.transcribe_bytes(wav_bytes)
        except sr.WaitTimeoutError:
            logger.info("Listening timed out with no speech detected")
            return None
        except Exception as ex:
            logger.error(f"Microphone recording failed for Deepgram: {ex}")
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
    if provider == "deepgram":
        return DeepgramSTT()
    elif provider == "speech_recognition":
        return SpeechRecognitionSTT(language=settings.STT_LANGUAGE)
    elif provider == "whisper":
        return WhisperSTT()
    elif provider == "mock":
        return MockSTT()
    else:
        logger.warning(f"Unknown STT provider '{provider}', defaulting to DeepgramSTT")
        return DeepgramSTT()
