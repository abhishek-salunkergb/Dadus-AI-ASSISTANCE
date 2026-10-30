"""Text-to-Speech (TTS) provider abstractions and implementations for DADUS."""
from abc import ABC, abstractmethod
import os
import threading
import logging
from typing import Optional
from pathlib import Path
from app.config.settings import settings

logger = logging.getLogger("DADUS.TTS")

class BaseTTS(ABC):
    """Abstract interface for text-to-speech providers."""

    @abstractmethod
    def speak(self, text: str, async_mode: bool = True) -> None:
        """Speak the given text."""
        pass

    @abstractmethod
    def synthesize_to_file(self, text: str, destination_path: Optional[str] = None) -> Optional[str]:
        """Synthesize speech to a WAV or MP3 audio file and return the path."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Interrupt active speech playback immediately."""
        pass

class WindowsSapiTTS(BaseTTS):
    """
    Native Windows SAPI.SpVoice TTS provider.
    Zero latency, completely offline, zero cloud dependencies.
    """

    def __init__(self, rate: int = 1, volume: int = 100):
        self.rate = rate
        self.volume = volume
        self._lock = threading.Lock()

    def speak(self, text: str, async_mode: bool = True) -> None:
        """Speak text through Windows default audio device."""
        if not settings.TTS_ENABLED or not text.strip():
            return

        def _do_speak():
            with self._lock:
                try:
                    import pythoncom
                    import win32com.client
                    pythoncom.CoInitialize()
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Rate = self.rate
                    speaker.Volume = self.volume
                    speaker.Speak(text)
                except Exception as ex:
                    logger.error(f"SAPI speech failed: {ex}")
                finally:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass

        if async_mode:
            thread = threading.Thread(target=_do_speak, daemon=True)
            thread.start()
        else:
            _do_speak()

    def synthesize_to_file(self, text: str, destination_path: Optional[str] = None) -> Optional[str]:
        """Synthesize speech into a WAV file using SAPI.SpFileStream."""
        if not text.strip():
            return None

        audio_dir = settings.DATA_DIR / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        out_path = destination_path or str(audio_dir / f"response_{int(os.getpid())}.wav")

        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            filestream = win32com.client.Dispatch("SAPI.SpFileStream")
            
            # SSFMCreateForWrite = 3
            filestream.Open(out_path, 3, False)
            speaker.AudioOutputStream = filestream
            speaker.Rate = self.rate
            speaker.Volume = self.volume
            speaker.Speak(text)
            filestream.Close()
            return out_path
        except Exception as ex:
            logger.error(f"Failed to synthesize audio to file: {ex}")
            return None
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def stop(self) -> None:
        """Interrupt and silence any playing speech immediately."""
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            # SVSFPurgeBeforeSpeak (2) purges existing speech
            speaker.Speak("", 2)
            pythoncom.CoUninitialize()
        except Exception as ex:
            logger.debug(f"Stop TTS encountered: {ex}")

class OpenAITTS(BaseTTS):
    """OpenAI cloud neural TTS provider."""

    def __init__(self, model: str = "tts-1", voice: str = "alloy"):
        self.model = model
        self.voice = voice

    def speak(self, text: str, async_mode: bool = True) -> None:
        audio_path = self.synthesize_to_file(text)
        if audio_path and os.path.exists(audio_path):
            # Play using Windows default audio player / winsound
            import winsound
            winsound.PlaySound(audio_path, winsound.SND_FILENAME | (winsound.SND_ASYNC if async_mode else 0))

    def stop(self) -> None:
        """Interrupt active sound playback."""
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def synthesize_to_file(self, text: str, destination_path: Optional[str] = None) -> Optional[str]:
        if not settings.OPENAI_API_KEY:
            logger.warning("OpenAI API key missing for OpenAITTS, falling back to SAPI.")
            return WindowsSapiTTS().synthesize_to_file(text, destination_path)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
            audio_dir = settings.DATA_DIR / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            out_path = destination_path or str(audio_dir / f"openai_{os.getpid()}.mp3")

            response = client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text
            )
            response.stream_to_file(out_path)
            return out_path
        except Exception as ex:
            logger.error(f"OpenAI TTS synthesis failed: {ex}")
            return WindowsSapiTTS().synthesize_to_file(text, destination_path)

class MockTTS(BaseTTS):
    """Mock TTS provider for unit tests and headless environments."""

    def __init__(self):
        self.spoken_history = []
        self.stopped = False

    def speak(self, text: str, async_mode: bool = True) -> None:
        self.spoken_history.append(text)
        self.stopped = False
        logger.info(f"[MockTTS]: {text}")

    def stop(self) -> None:
        self.stopped = True

    def synthesize_to_file(self, text: str, destination_path: Optional[str] = None) -> Optional[str]:
        self.spoken_history.append(text)
        dummy_path = destination_path or str(settings.DATA_DIR / "audio" / "mock.wav")
        Path(dummy_path).touch()
        return dummy_path

def get_tts_provider(provider_name: Optional[str] = None) -> BaseTTS:
    """Factory to retrieve configured TTS provider."""
    provider = (provider_name or settings.TTS_PROVIDER).lower()
    if provider == "sapi":
        return WindowsSapiTTS(rate=settings.TTS_VOICE_RATE, volume=settings.TTS_VOICE_VOLUME)
    elif provider == "openai":
        return OpenAITTS()
    elif provider == "mock":
        return MockTTS()
    else:
        logger.warning(f"Unknown TTS provider '{provider}', defaulting to SAPI")
        return WindowsSapiTTS()
