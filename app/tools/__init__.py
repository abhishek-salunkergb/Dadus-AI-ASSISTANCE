"""Tools package for DADUS.
Initializes and registers all tools with the central registry.
"""
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import ToolRegistry, tool_registry

from app.tools.apps import OpenAppTool, CloseAppTool, ListInstalledAppsTool
from app.tools.music import PlayMusicTool
from app.tools.browser import OpenBrowserTool, SearchWebTool, SearchYouTubeTool
from app.tools.system import (
    SetVolumeTool,
    MuteVolumeTool,
    TakeScreenshotTool,
    GetCurrentTimeTool,
    GetSystemStatusTool,
    LockDeviceTool
)
from app.tools.files import SearchFilesTool, DeleteFileOrFolderTool
from app.tools.reminders import CreateReminderTool, ListRemindersTool
from app.tools.schedule import GetTodayScheduleTool, CreateScheduleItemTool
from app.tools.memory_tools import StoreMemoryTool, ForgetMemoryTool

def register_default_tools(registry: ToolRegistry = tool_registry) -> None:
    """Register all standard DADUS tools."""
    tools = [
        OpenAppTool(),
        CloseAppTool(),
        ListInstalledAppsTool(),
        PlayMusicTool(),
        OpenBrowserTool(),
        SearchWebTool(),
        SearchYouTubeTool(),
        SetVolumeTool(),
        MuteVolumeTool(),
        TakeScreenshotTool(),
        GetCurrentTimeTool(),
        GetSystemStatusTool(),
        LockDeviceTool(),
        SearchFilesTool(),
        DeleteFileOrFolderTool(),
        CreateReminderTool(),
        ListRemindersTool(),
        GetTodayScheduleTool(),
        CreateScheduleItemTool(),
        StoreMemoryTool(),
        ForgetMemoryTool()
    ]
    for tool in tools:
        registry.register(tool)

# Automatically register default tools on import
register_default_tools()

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "tool_registry",
    "register_default_tools"
]
