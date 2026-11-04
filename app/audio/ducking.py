"""Windows audio ducking manager for DADUS.
Automatically ducks background media/music when DADUS wakes up, exactly like Siri.
"""
import logging
import threading
from typing import Optional

logger = logging.getLogger("DADUS.AudioDucking")

class AudioDucker:
    """Manages temporary lowering (ducking) and restoration of Windows master audio."""

    def __init__(self, duck_ratio: float = 0.25):
        self.duck_ratio = duck_ratio
        self._original_volume: Optional[float] = None
        self._is_ducked: bool = False
        self._lock = threading.Lock()

    def duck(self) -> bool:
        """Lower master volume to duck ratio so microphone captures voice clearly."""
        with self._lock:
            if self._is_ducked:
                return True

            try:
                from pycaw.pycaw import AudioUtilities
                speakers = AudioUtilities.GetSpeakers()
                vol = speakers.EndpointVolume
                self._original_volume = vol.GetMasterVolumeLevelScalar()

                # Calculate ducked level (at least 5%, at most original * duck_ratio)
                ducked_level = max(0.05, self._original_volume * self.duck_ratio)
                vol.SetMasterVolumeLevelScalar(ducked_level, None)
                self._is_ducked = True
                logger.debug(f"Audio ducked from {self._original_volume:.2f} to {ducked_level:.2f}")
                return True
            except Exception as ex:
                logger.debug(f"Audio ducking not available: {ex}")
                return False

    def restore(self) -> bool:
        """Restore master volume back to original level."""
        with self._lock:
            if not self._is_ducked or self._original_volume is None:
                return True

            try:
                from pycaw.pycaw import AudioUtilities
                speakers = AudioUtilities.GetSpeakers()
                vol = speakers.EndpointVolume
                vol.SetMasterVolumeLevelScalar(self._original_volume, None)
                logger.debug(f"Audio restored to {self._original_volume:.2f}")
                self._is_ducked = False
                self._original_volume = None
                return True
            except Exception as ex:
                logger.debug(f"Audio restoration failed: {ex}")
                self._is_ducked = False
                return False

    def __enter__(self):
        self.duck()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.restore()

audio_ducker = AudioDucker()
