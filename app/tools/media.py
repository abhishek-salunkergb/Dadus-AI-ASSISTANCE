"""Media playback controls and relative volume adjustments for Windows."""
import ctypes
import logging
from typing import Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.tools.system import SetVolumeTool

logger = logging.getLogger("DADUS.Media")

# Windows Virtual Key Codes for Media
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

def _send_media_key(vk_code: int) -> None:
    """Send Windows keybd_event for hardware media control."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    except Exception as ex:
        logger.error(f"Failed to send media key {vk_code}: {ex}")

# ==========================================
# Tool: pause_music
# ==========================================
class PauseMusicInput(BaseModel):
    pass

class PauseMusicTool(BaseTool):
    name = "pause_music"
    description = "Pauses or toggles active media playback on Windows (Spotify, YouTube, browser)."
    permission_level = PermissionLevel.SAFE
    args_schema = PauseMusicInput

    def execute(self) -> ToolResult:
        _send_media_key(VK_MEDIA_PLAY_PAUSE)
        return ToolResult(
            tool_name=self.name,
            success=True,
            message="Toggled playback pause, boss."
        )

# ==========================================
# Tool: resume_music
# ==========================================
class ResumeMusicInput(BaseModel):
    pass

class ResumeMusicTool(BaseTool):
    name = "resume_music"
    description = "Resumes paused media playback on Windows."
    permission_level = PermissionLevel.SAFE
    args_schema = ResumeMusicInput

    def execute(self) -> ToolResult:
        _send_media_key(VK_MEDIA_PLAY_PAUSE)
        return ToolResult(
            tool_name=self.name,
            success=True,
            message="Resumed playback, boss."
        )

# ==========================================
# Tool: skip_music_track
# ==========================================
class SkipTrackInput(BaseModel):
    pass

class SkipMusicTrackTool(BaseTool):
    name = "skip_music_track"
    description = "Skips to the next media track on Windows."
    permission_level = PermissionLevel.SAFE
    args_schema = SkipTrackInput

    def execute(self) -> ToolResult:
        _send_media_key(VK_MEDIA_NEXT_TRACK)
        return ToolResult(
            tool_name=self.name,
            success=True,
            message="Skipped to next song, boss."
        )

# ==========================================
# Tool: adjust_volume
# ==========================================
class AdjustVolumeInput(BaseModel):
    delta: int = Field(description="Amount to adjust volume by, e.g. -10 for slightly lower, +15 for louder", default=-10)
    direction: Optional[str] = Field(default=None, description="'up', 'down', 'higher', 'lower'")

class AdjustVolumeTool(BaseTool):
    name = "adjust_volume"
    description = "Adjusts system volume relatively (e.g. slightly lower, louder, softer)."
    permission_level = PermissionLevel.SAFE
    args_schema = AdjustVolumeInput

    def execute(self, delta: int = -10, direction: Optional[str] = None) -> ToolResult:
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if not speakers or not speakers.EndpointVolume:
                raise RuntimeError("No audio endpoint")

            current_scalar = speakers.EndpointVolume.GetMasterVolumeLevelScalar()
            current_pct = int(round(current_scalar * 100))

            change = delta
            if direction in ["down", "lower", "softer"] and change > 0:
                change = -change
            elif direction in ["up", "higher", "louder"] and change < 0:
                change = abs(change)

            new_level = max(0, min(100, current_pct + change))
            speakers.EndpointVolume.SetMasterVolumeLevelScalar(new_level / 100.0, None)

            action_desc = "lowered" if change < 0 else "increased"
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Volume {action_desc} to {new_level} percent, boss.",
                data={"old_level": current_pct, "new_level": new_level, "change": change}
            )
        except Exception as ex:
            logger.error(f"Failed to adjust volume: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't adjust the volume.",
                error=str(ex)
            )
