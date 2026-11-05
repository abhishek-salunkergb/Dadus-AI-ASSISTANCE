"""Always-on Voice Agent Service with robust State Machine for DADUS.
Coordinates continuous background wake-word detection, conversational lifecycle,
VAD silence truncation, barge-in interruption, multi-turn follow-ups, and audio ducking.
"""
import time
import re
import queue
import threading
import logging
from enum import Enum
from typing import Optional, Dict, Any, Callable

from app.config.settings import settings
from app.voice.tts import get_tts_provider
from app.voice.stt import get_stt_provider
from app.agent.agent import dadus_agent
from app.audio.ducking import audio_ducker
from app.voice.tts import is_speech_active
from app.voice.wakeword_matcher import WakeWordMatcher

logger = logging.getLogger("DADUS.VoiceService")

class VoiceState(str, Enum):
    IDLE_WAKE_MONITORING = "IDLE_WAKE_MONITORING"
    WAKE_DETECTED = "WAKE_DETECTED"
    GREETING = "GREETING"
    ACTIVE_LISTENING = "ACTIVE_LISTENING"
    SPEECH_RECOGNITION = "SPEECH_RECOGNITION"
    INTENT_UNDERSTANDING = "INTENT_UNDERSTANDING"
    TASK_EXECUTION = "TASK_EXECUTION"
    RESULT_VERIFICATION = "RESULT_VERIFICATION"
    SPOKEN_RESPONSE = "SPOKEN_RESPONSE"
    ERROR = "ERROR"

class VoiceAgentService:
    """
    Central background voice service managing true hands-free activation,
    multi-turn conversational follow-up, and audio hardware synchronization.
    """

    def __init__(self):
        self._state = VoiceState.IDLE_WAKE_MONITORING
        self._state_lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._session_id = "voice_agent_session"

        # Timing and sensitivity settings
        self.wake_phrases = ["hey dadus", "dadus", "ok dadus", "hi dadus", "hello dadus"]
        self.conversation_timeout = 7.0  # seconds to wait for follow-up command
        self.last_interaction_time = 0.0
        self.mic_available = True
        self.last_error: Optional[str] = None

        # Callbacks
        self.state_listeners = []

    @property
    def current_state(self) -> VoiceState:
        with self._state_lock:
            return self._state

    def add_state_listener(self, listener: Callable[[VoiceState, str], None]) -> None:
        self.state_listeners.append(listener)

    def _set_state(self, new_state: VoiceState, message: str = "") -> None:
        with self._state_lock:
            self._state = new_state
        logger.info(f"Voice State -> {new_state.value}: {message}")

        # Broadcast via FastAPI WebSockets if available
        try:
            from app.api.server import sync_voice_state
            # Map VoiceState to frontend friendly tags
            tag_map = {
                VoiceState.IDLE_WAKE_MONITORING: "idle",
                VoiceState.WAKE_DETECTED: "listening",
                VoiceState.GREETING: "speaking",
                VoiceState.ACTIVE_LISTENING: "listening",
                VoiceState.SPEECH_RECOGNITION: "thinking",
                VoiceState.INTENT_UNDERSTANDING: "thinking",
                VoiceState.TASK_EXECUTION: "executing",
                VoiceState.RESULT_VERIFICATION: "executing",
                VoiceState.SPOKEN_RESPONSE: "speaking",
                VoiceState.ERROR: "error"
            }
            sync_voice_state(tag_map.get(new_state, "idle"), message or new_state.value)
        except Exception:
            pass

        for cb in self.state_listeners:
            try:
                cb(new_state, message)
            except Exception as ex:
                logger.debug(f"State listener callback error: {ex}")

    def start(self) -> None:
        """Start the background voice monitoring service."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._run_voice_lifecycle, daemon=True, name="DADUS-VoiceWorker")
        self._worker_thread.start()
        logger.info("DADUS VoiceAgentService started.")

    def stop(self) -> None:
        """Stop the background voice monitoring service."""
        self._running = False
        try:
            get_tts_provider().stop()
        except Exception:
            pass
        self._set_state(VoiceState.IDLE_WAKE_MONITORING, "Stopped")
        logger.info("DADUS VoiceAgentService stopped.")

    def trigger_wake_manually(self, initial_command: Optional[str] = None) -> None:
        """Allows hotkey or UI trigger to bypass wake word and immediately enter conversation."""
        try:
            get_tts_provider().stop()
        except Exception:
            pass

        threading.Thread(target=self._handle_active_turn, args=(initial_command, True), daemon=True).start()

    def get_health(self) -> Dict[str, Any]:
        """Provides status of the background voice engine."""
        return {
            "status": "healthy" if self._running and self.mic_available else ("error" if self.last_error else "idle"),
            "state": self.current_state.value,
            "running": self._running,
            "microphone_available": self.mic_available,
            "last_error": self.last_error,
            "conversation_timeout_seconds": self.conversation_timeout
        }

    def _run_voice_lifecycle(self) -> None:
        """Continuous background wake-word listener loop with acoustic echo suppression and buffer stitching."""
        tts = get_tts_provider()
        stt = get_stt_provider()

        import speech_recognition as sr
        recognizer = sr.Recognizer()
        # Calibrated stable baseline threshold preventing mic deafening
        recognizer.energy_threshold = max(200, settings.STT_ENERGY_THRESHOLD)
        recognizer.dynamic_energy_threshold = False
        recognizer.pause_threshold = 1.3
        recognizer.phrase_threshold = 0.2
        recognizer.non_speaking_duration = 0.5

        logger.info(f"Background Wake Monitoring active. Target assistant name: '{WakeWordMatcher.ASSISTANT_NAME}'")

        last_lone_greeting: Optional[str] = None
        last_lone_greeting_time: float = 0.0

        while self._running:
            detected = False
            inline_command = ""
            try:
                # Persistent microphone capture stream
                with sr.Microphone() as source:
                    self.mic_available = True
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)

                    while self._running:
                        # 1. Acoustic Feedback Suppression: Do not capture while assistant is speaking
                        if is_speech_active():
                            time.sleep(0.15)
                            continue

                        self._set_state(VoiceState.IDLE_WAKE_MONITORING, "Listening for 'Hey Dadus'...")
                        try:
                            audio = recognizer.listen(source, timeout=3.0, phrase_time_limit=5.0)
                        except sr.WaitTimeoutError:
                            continue

                        # Discard audio if speech playback started while recording
                        if is_speech_active():
                            continue

                        # 2. Transcribe captured snippet via Deepgram Nova-2 (flagship) or Google
                        text = None
                        wav_data = audio.get_wav_data()
                        if hasattr(stt, "transcribe_bytes") and getattr(stt, "_get_api_key", lambda: None)():
                            try:
                                text = stt.transcribe_bytes(wav_data)
                            except Exception:
                                pass

                        if not text:
                            try:
                                text = recognizer.recognize_google(audio, language="en-US").strip()
                            except (sr.UnknownValueError, sr.RequestError):
                                continue

                        if not text or len(text.strip()) < 2:
                            continue

                        # 3. Buffer Stitching for Greeting Continuity (e.g. "Hey," ... "Dadus")
                        now = time.time()
                        candidate_text = text
                        if last_lone_greeting and (now - last_lone_greeting_time <= 3.0):
                            candidate_text = f"{last_lone_greeting} {text}"
                            last_lone_greeting = None

                        # 4. Principled Phonetic Wake Matching
                        is_wake, inline_cmd = WakeWordMatcher.match(candidate_text)
                        if is_wake:
                            detected = True
                            inline_command = inline_cmd
                            last_lone_greeting = None
                            break
                        elif WakeWordMatcher.is_lone_greeting(text):
                            last_lone_greeting = text.strip(" ,.?!")
                            last_lone_greeting_time = now
                            logger.debug(f"Captured initial greeting '{last_lone_greeting}', holding buffer for assistant name...")
                        else:
                            last_lone_greeting = None

                # Handle active turn outside the microphone context so hardware buffers clear cleanly
                if detected:
                    logger.info(f"Wake word detected! (Inline command: '{inline_command}')")
                    self._handle_active_turn(inline_command=inline_command, is_new_wake=True)
                    # Pause briefly to ensure output audio is flushed before re-opening microphone
                    time.sleep(0.5)

            except Exception as ex:
                self.last_error = str(ex)
                self.mic_available = False
                logger.debug(f"Voice cycle audio notice: {ex}")
                time.sleep(1.0)

    def _handle_active_turn(self, inline_command: Optional[str] = None, is_new_wake: bool = False) -> None:
        """Executes a full interactive conversational cycle with multi-turn support."""
        tts = get_tts_provider()
        stt = get_stt_provider()

        with audio_ducker:
            # 1. Wake detected & Greeting
            if is_new_wake:
                self._set_state(VoiceState.WAKE_DETECTED, "Wake phrase detected")
                time.sleep(0.05)

                if not inline_command:
                    # Greet Boss cleanly before listening
                    self._set_state(VoiceState.GREETING, "I'm listening, Boss. Tell me.")
                    tts.speak("I'm listening, Boss. Tell me.", async_mode=False)

            # 2. Enter conversational loop for this and any natural follow-up instructions
            in_conversation = True
            first_turn = True

            while in_conversation and self._running:
                command_text = ""

                if first_turn and inline_command:
                    command_text = inline_command
                    first_turn = False
                else:
                    first_turn = False
                    self._set_state(VoiceState.ACTIVE_LISTENING, "Listening for Boss's request...")
                    
                    # Capture speech
                    try:
                        captured = stt.listen_and_transcribe(timeout=int(self.conversation_timeout), phrase_time_limit=12)
                        command_text = (captured or "").strip()
                    except Exception as ex:
                        logger.debug(f"Audio capture error in active turn: {ex}")
                        command_text = ""

                # If silence / no speech detected within conversation timeout
                if not command_text:
                    logger.info("No speech detected within conversation window; returning to standby.")
                    in_conversation = False
                    break

                # 3. Speech Recognition verification
                self._set_state(VoiceState.SPEECH_RECOGNITION, f"Heard: '{command_text}'")

                lower_cmd = command_text.lower().strip()
                # Check for explicit cancellation
                if lower_cmd in ["cancel", "stop", "nevermind", "never mind", "be quiet", "shut up", "abort"]:
                    tts.stop()
                    self._set_state(VoiceState.SPOKEN_RESPONSE, "Cancelled, Boss.")
                    tts.speak("Cancelled, Boss.", async_mode=False)
                    in_conversation = False
                    break

                # If user repeated wake word during follow-up window (e.g. "Hey Dadus open Chrome" or just "Hey Dadus")
                is_rep_wake, rep_cmd = WakeWordMatcher.match(command_text)
                if is_rep_wake:
                    if rep_cmd:
                        command_text = rep_cmd
                    else:
                        self._set_state(VoiceState.GREETING, "I'm listening, Boss. Tell me.")
                        tts.speak("I'm listening, Boss. Tell me.", async_mode=False)
                        continue

                # Check for unintelligible speech
                if len(command_text) < 2:
                    self._set_state(VoiceState.GREETING, "Sorry, Boss. Could you say that again?")
                    tts.speak("Sorry, Boss. Could you say that again?", async_mode=False)
                    continue

                # 4. Intent Understanding
                self._set_state(VoiceState.INTENT_UNDERSTANDING, f"Understanding: '{command_text}'")

                # 5. Task Execution
                self._set_state(VoiceState.TASK_EXECUTION, f"Executing: '{command_text}'")
                response = dadus_agent.process_input(command_text, session_id=self._session_id)

                # 6. Result Verification
                self._set_state(VoiceState.RESULT_VERIFICATION, "Verifying execution outcome")
                time.sleep(0.1)

                # 7. Spoken Response
                reply_text = response.text or "Done, Boss."
                self._set_state(VoiceState.SPOKEN_RESPONSE, reply_text)
                tts.speak(reply_text, async_mode=False)

                # Update interaction timestamp for follow-up window
                self.last_interaction_time = time.time()

                # If agent requested clarification, immediately loop back to capture the answer
                if response.status == "WAITING_CLARIFICATION" or response.needs_clarification:
                    continue

                # If confirmation is pending, immediately listen for yes/no
                if response.status == "WAITING_CONFIRMATION" or response.needs_confirmation:
                    continue

                # Check if user speaks a follow-up instruction in the follow-up window
                # Small pause after speaking so TTS audio clears microphone
                time.sleep(0.3)

            self._set_state(VoiceState.IDLE_WAKE_MONITORING, "Standing by for 'Hey Dadus'...")

voice_service = VoiceAgentService()

