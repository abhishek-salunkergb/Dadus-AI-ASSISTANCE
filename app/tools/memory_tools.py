"""Memory and preference tools for DADUS agent."""
import logging
from typing import Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.memory.memory import memory_store

logger = logging.getLogger("DADUS.MemoryTools")

# ==========================================
# Tool: store_memory
# ==========================================
class StoreMemoryInput(BaseModel):
    key: str = Field(description="Key or category of the memory, e.g. 'preferred_music_app', 'coffee_order'")
    value: str = Field(description="Value to remember, e.g. 'Spotify', 'Black with oat milk'")
    category: Optional[str] = Field(default="preference", description="Category: 'preference', 'fact', 'identity'")

class StoreMemoryTool(BaseTool):
    name = "store_memory"
    description = "Remembers a user preference or fact for future interactions."
    permission_level = PermissionLevel.SAFE
    args_schema = StoreMemoryInput

    def execute(self, key: str, value: str, category: Optional[str] = "preference") -> ToolResult:
        item = memory_store.remember(key, value, category or "preference")
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"I'll remember that you prefer {value}, boss." if "prefer" in key.lower() else f"I've remembered that, boss.",
            data=item
        )

# ==========================================
# Tool: forget_memory
# ==========================================
class ForgetMemoryInput(BaseModel):
    key: str = Field(description="Key of the memory to forget, e.g. 'preferred_music_app'")

class ForgetMemoryTool(BaseTool):
    name = "forget_memory"
    description = "Removes a previously stored preference or fact from memory."
    permission_level = PermissionLevel.SAFE
    args_schema = ForgetMemoryInput

    def execute(self, key: str) -> ToolResult:
        removed = memory_store.forget(key)
        if removed:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"I've forgotten that preference, boss.",
                data={"key": key}
            )
        else:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, I didn't have any saved memory matching '{key}'.",
                data={"key": key}
            )
