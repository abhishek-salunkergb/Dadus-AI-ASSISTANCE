"""Text-to-Speech (TTS) provider abstractions and implementations for DADUS."""
from abc import ABC, abstractmethod
import os
import time
import threading
import logging
from typing import Optional
import queue
from pathlib import Path
from app.config.settings import settings

logger = logging.getLogger("DADUS.TTS")

_speech_active_flag: bool = False
_speech_active_lock = threading.Lock()

def is_speech_active() -> bool:
    """Returns True if any TTS engine is actively speaking audio through speakers."""
    with _speech_active_lock:
        return _speech_active_flag

def set_speech_active(active: bool) -> None:
    """Updates active speech status to prevent microphone acoustic self-feedback."""
    global _speech_active_flag
    with _speech_active_lock:
        _speech_active_flag = active

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


class _SapiPlaybackEngine:
    """Dedicated background COM worker thread providing instant speech interruption and barge-in."""
    _instance = None
    _init_lock = threading.Lock()

    @classmethod
    def get_instance(cls, rate: int = 1, volume: int = 100):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = cls(rate=rate, volume=volume)
            else:
                cls._instance.set_params(rate=rate, volume=volume)
            return cls._instance

    def __init__(self, rate: int = 1, volume: int = 100):
        self.rate = rate
        self.volume = volume
        self._cmd_queue: queue.Queue = queue.Queue()
        self._active_done_event: Optional[threading.Event] = None
        self._is_speaking = False
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def set_params(self, rate: int, volume: int) -> None:
        self.rate = rate
        self.volume = volume

    def _worker_loop(self) -> None:
        speaker = None
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate = self.rate
            speaker.Volume = self.volume
        except Exception as ex:
            logger.error(f"SAPI voice initialization failed: {ex}")

        while True:
            cmd, payload, done_ev = self._cmd_queue.get()
            if speaker is None:
                if done_ev:
                    done_ev.set()
                continue

            try:
                speaker.Rate = self.rate
                speaker.Volume = self.volume
                if cmd == "SPEAK":
                    self._is_speaking = True
                    set_speech_active(True)
                    self._active_done_event = done_ev
                    # SVSFlagsAsync = 1, SVSFPurgeBeforeSpeak = 2 -> 1 | 2 = 3
                    speaker.Speak(payload, 3)
                    while True:
                        if speaker.WaitUntilDone(30):
                            break
                        if not self._cmd_queue.empty():
                            speaker.Speak("", 2)
                            break
                    self._is_speaking = False
                    set_speech_active(False)
                    if self._active_done_event:
                        self._active_done_event.set()
                        self._active_done_event = None
                elif cmd == "STOP":
                    speaker.Speak("", 2)
                    self._is_speaking = False
                    set_speech_active(False)
                    if self._active_done_event:
                        self._active_done_event.set()
                        self._active_done_event = None
                    if done_ev:
                        done_ev.set()
            except Exception as ex:
                logger.debug(f"SAPI worker loop error: {ex}")
                self._is_speaking = False
                if self._active_done_event:
                    self._active_done_event.set()
                    self._active_done_event = None
                if done_ev:
                    done_ev.set()

    def speak(self, text: str, async_mode: bool = True) -> None:
        ev = threading.Event()
        self._cmd_queue.put(("SPEAK", text, ev))
        if not async_mode:
            ev.wait()

    def stop(self) -> None:
        self._cmd_queue.put(("STOP", None, None))


class WindowsSapiTTS(BaseTTS):
    """
    Native Windows SAPI.SpVoice TTS provider with instant barge-in cancellation.
    Zero latency, completely offline, zero cloud dependencies.
    """

    def __init__(self, rate: int = 1, volume: int = 100):
        self.rate = rate
        self.volume = volume
        self._engine = _SapiPlaybackEngine.get_instance(rate=rate, volume=volume)

    def speak(self, text: str, async_mode: bool = True) -> None:
        """Speak text through Windows default audio device with interruptibility."""
        if not settings.TTS_ENABLED or not text.strip():
            return
        self._engine.speak(text, async_mode=async_mode)

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
            self._engine.stop()
        except Exception as ex:
            logger.debug(f"Stop TTS encountered: {ex}")

class OpenAITTS(BaseTTS):
    """OpenAI cloud neural TTS provider."""

    def __init__(self, model: str = "tts-1", voice: str = "alloy"):
        self.model = model
        self.voice = voice

    def speak(self, text: str, async_mode: bool = True) -> None:
        set_speech_active(True)
        try:
            audio_path = self.synthesize_to_file(text)
            if audio_path and os.path.exists(audio_path):
                import winsound
                winsound.PlaySound(audio_path, winsound.SND_FILENAME | (winsound.SND_ASYNC if async_mode else 0))
            else:
                WindowsSapiTTS().speak(text, async_mode=async_mode)
        finally:
            if not async_mode:
                set_speech_active(False)

    def stop(self) -> None:
        """Interrupt active sound playback."""
        set_speech_active(False)
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
            out_path = destination_path or str(audio_dir / f"openai_{os.getpid()}_{int(time.time()*1000)}.wav")

            response = client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format="wav"
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
        return OpenAITTS(voice=settings.TTS_VOICE)
    elif provider == "mock":
        return MockTTS()
    else:
        logger.warning(f"Unknown TTS provider '{provider}', defaulting to SAPI")
        return WindowsSapiTTS()
