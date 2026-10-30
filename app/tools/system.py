"""System control tools for Windows (volume, screenshot, system info, lock)."""
import os
import sys
import ctypes
from datetime import datetime
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field
import psutil
from PIL import ImageGrab

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.config.settings import settings

logger = logging.getLogger("DADUS.System")

# ==========================================
# Tool: set_volume
# ==========================================
class SetVolumeInput(BaseModel):
    level: int = Field(description="Volume level percentage from 0 to 100", ge=0, le=100)

class SetVolumeTool(BaseTool):
    name = "set_volume"
    description = "Sets system audio volume to a percentage between 0 and 100."
    permission_level = PermissionLevel.SAFE
    args_schema = SetVolumeInput

    def execute(self, level: int) -> ToolResult:
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if not speakers or not speakers.EndpointVolume:
                raise RuntimeError("No active speaker endpoint found")

            scalar = max(0.0, min(1.0, level / 100.0))
            speakers.EndpointVolume.SetMasterVolumeLevelScalar(scalar, None)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Set volume to {level} percent.",
                data={"level": level}
            )
        except Exception as ex:
            logger.error(f"Failed to set volume: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't adjust the system volume.",
                error=str(ex)
            )

# ==========================================
# Tool: mute_volume
# ==========================================
class MuteVolumeInput(BaseModel):
    mute: bool = Field(default=True, description="True to mute, False to unmute")

class MuteVolumeTool(BaseTool):
    name = "mute_volume"
    description = "Mutes or unmutes the system audio."
    permission_level = PermissionLevel.SAFE
    args_schema = MuteVolumeInput

    def execute(self, mute: bool = True) -> ToolResult:
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if not speakers or not speakers.EndpointVolume:
                raise RuntimeError("No active speaker endpoint found")

            speakers.EndpointVolume.SetMute(1 if mute else 0, None)
            action_str = "Muted" if mute else "Unmuted"
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"{action_str} system audio.",
                data={"muted": mute}
            )
        except Exception as ex:
            logger.error(f"Failed to toggle mute: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't change the mute setting.",
                error=str(ex)
            )

# ==========================================
# Tool: take_screenshot
# ==========================================
class TakeScreenshotInput(BaseModel):
    filename: Optional[str] = Field(default=None, description="Optional custom filename for the screenshot")

class TakeScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = "Takes a screenshot of the primary screen and saves it."
    permission_level = PermissionLevel.SAFE
    args_schema = TakeScreenshotInput

    def execute(self, filename: Optional[str] = None) -> ToolResult:
        try:
            shots_dir = settings.DATA_DIR / "screenshots"
            shots_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = filename or f"screenshot_{timestamp}.png"
            if not fname.lower().endswith(".png"):
                fname += ".png"

            save_path = shots_dir / fname
            screenshot = ImageGrab.grab()
            screenshot.save(str(save_path))

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Screenshot captured, boss.",
                data={"path": str(save_path), "filename": fname}
            )
        except Exception as ex:
            logger.error(f"Failed to capture screenshot: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't take a screenshot.",
                error=str(ex)
            )

# ==========================================
# Tool: get_current_time
# ==========================================
class GetCurrentTimeInput(BaseModel):
    pass

class GetCurrentTimeTool(BaseTool):
    name = "get_current_time"
    description = "Returns current date, time, and day of the week."
    permission_level = PermissionLevel.SAFE
    args_schema = GetCurrentTimeInput

    def execute(self) -> ToolResult:
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d, %Y")
        msg = f"Boss, it is {time_str} on {date_str}."
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=msg,
            data={"time": time_str, "date": date_str, "iso": now.isoformat()}
        )

# ==========================================
# Tool: get_system_status
# ==========================================
class GetSystemStatusInput(BaseModel):
    pass

class GetSystemStatusTool(BaseTool):
    name = "get_system_status"
    description = "Returns CPU usage, RAM utilization, battery status, and disk space."
    permission_level = PermissionLevel.SAFE
    args_schema = GetSystemStatusInput

    def execute(self) -> ToolResult:
        try:
            cpu_pct = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")

            battery_info = "Desktop / AC power"
            try:
                bat = psutil.sensors_battery()
                if bat:
                    charging = "charging" if bat.power_plugged else "discharging"
                    battery_info = f"{bat.percent}% ({charging})"
            except Exception:
                pass

            msg = (
                f"Boss, CPU is at {cpu_pct}%, memory is at {mem.percent}%, "
                f"battery is at {battery_info}, and C: drive has {disk.free // (2**30)} GB free."
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data={
                    "cpu_percent": cpu_pct,
                    "ram_percent": mem.percent,
                    "battery": battery_info,
                    "disk_free_gb": disk.free // (2**30)
                }
            )
        except Exception as ex:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't retrieve the system status.",
                error=str(ex)
            )

# ==========================================
# Tool: lock_device
# ==========================================
class LockDeviceInput(BaseModel):
    pass

class LockDeviceTool(BaseTool):
    name = "lock_device"
    description = "Locks the Windows workstation screen."
    permission_level = PermissionLevel.SAFE
    args_schema = LockDeviceInput

    def execute(self) -> ToolResult:
        try:
            ctypes.windll.user32.LockWorkStation()
            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Locking device, boss.",
                data={"locked": True}
            )
        except Exception as ex:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't lock the workstation.",
                error=str(ex)
            )
