"""Camera launching and media recording tools for DADUS.
Interacts with the real operating-system camera application and hardware.
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel, permission_manager
from app.platform import platform_adapter

logger = logging.getLogger("DADUS.Camera")


# ==========================================
# Tool 1: open_camera
# ==========================================
class OpenCameraInput(BaseModel):
    mode: Optional[str] = Field(default="photo", description="Camera mode: 'photo' or 'video'.")

class OpenCameraTool(BaseTool):
    name = "open_camera"
    description = "Launches the device camera application for capturing photos or videos."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenCameraInput

    def execute(self, mode: Optional[str] = "photo") -> ToolResult:
        if not permission_manager.is_permitted("camera_access"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, Camera Access permission is currently disabled in your DADUS settings.",
                error="PERMISSION_DENIED"
            )

        success = platform_adapter.launch_camera(mode=mode or "photo")
        if success:
            mode_desc = "video recording" if mode == "video" else "taking photos"
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Opening the Camera for {mode_desc}, Boss.",
                data={"mode": mode, "launched": True}
            )
        else:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I could not launch the camera application on this device.",
                error="CAMERA_LAUNCH_FAILED"
            )


# ==========================================
# Tool 2: record_video
# ==========================================
class RecordVideoInput(BaseModel):
    pass

class RecordVideoTool(BaseTool):
    name = "record_video"
    description = "Opens the camera in video recording mode."
    permission_level = PermissionLevel.SAFE
    args_schema = RecordVideoInput

    def execute(self) -> ToolResult:
        if not permission_manager.is_permitted("camera_access"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, Camera Access permission is disabled in your DADUS settings.",
                error="PERMISSION_DENIED"
            )

        success = platform_adapter.launch_camera(mode="video")
        if success:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Opening the Camera in video mode, Boss.",
                data={"mode": "video", "launched": True}
            )
        else:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, unable to launch the video recorder on this device.",
                error="VIDEO_RECORDER_FAILED"
            )

