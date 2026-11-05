"""Gallery and photo viewing tools for DADUS.
Accesses real media storage and system photo viewers without simulation.
"""
from datetime import datetime
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel, permission_manager
from app.platform import platform_adapter

logger = logging.getLogger("DADUS.Gallery")


# ==========================================
# Tool 1: open_gallery
# ==========================================
class OpenGalleryInput(BaseModel):
    pass

class OpenGalleryTool(BaseTool):
    name = "open_gallery"
    description = "Opens the device photo gallery and picture library."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenGalleryInput

    def execute(self) -> ToolResult:
        if not permission_manager.is_permitted("photos_gallery"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, Photos & Gallery permission is currently disabled in your DADUS settings.",
                error="PERMISSION_DENIED"
            )

        success = platform_adapter.launch_gallery()
        if success:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Opening your photo gallery, Boss.",
                data={"launched": True}
            )
        else:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I could not open your photo gallery.",
                error="GALLERY_OPEN_FAILED"
            )


# ==========================================
# Tool 2: show_recent_photos
# ==========================================
class ShowRecentPhotosInput(BaseModel):
    limit: Optional[int] = Field(default=5, description="Maximum number of recent photos to display.")
    open_latest: Optional[bool] = Field(default=False, description="Whether to open the most recent photo in the default viewer.")

class ShowRecentPhotosTool(BaseTool):
    name = "show_recent_photos"
    description = "Retrieves and displays recent photographs and screenshots from device storage."
    permission_level = PermissionLevel.SAFE
    args_schema = ShowRecentPhotosInput

    def execute(self, limit: Optional[int] = 5, open_latest: Optional[bool] = False) -> ToolResult:
        if not permission_manager.is_permitted("photos_gallery"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, Photos & Gallery permission is disabled in your DADUS settings.",
                error="PERMISSION_DENIED"
            )

        photos = platform_adapter.get_recent_photos(limit=limit or 5)
        if not photos:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Boss, no photos were found in your Pictures or Camera Roll folder.",
                data={"photos": [], "count": 0}
            )

        photo_records: List[Dict[str, Any]] = []
        lines = []
        for p in photos:
            stat = p.stat()
            size_kb = round(stat.st_size / 1024, 1)
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y %I:%M %p")
            photo_records.append({
                "filename": p.name,
                "path": str(p),
                "size_kb": size_kb,
                "modified": mtime
            })
            lines.append(f"• {p.name} ({size_kb} KB, {mtime})")

        msg = f"Boss, here are your {len(photos)} most recent photos:\n" + "\n".join(lines)

        # Open latest if requested
        if open_latest and photos:
            platform_adapter.launch_gallery(target_image=photos[0])
            msg += f"\n\nI have opened the latest photo ('{photos[0].name}') in your viewer."

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=msg,
            data={"photos": photo_records, "count": len(photos), "latest": str(photos[0])}
        )

