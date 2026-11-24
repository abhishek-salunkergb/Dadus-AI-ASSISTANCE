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
    LockDeviceTool,
    ToggleBluetoothTool
)
from app.tools.files import SearchFilesTool, DeleteFileOrFolderTool
from app.tools.reminders import CreateReminderTool, ListRemindersTool
from app.tools.alarms import SetAlarmTool, ListAlarmsTool, CancelAlarmTool, ModifyAlarmTool
from app.tools.schedule import GetTodayScheduleTool, CreateScheduleItemTool
from app.tools.memory_tools import StoreMemoryTool, ForgetMemoryTool
from app.tools.tasks import CreateTaskTool, ListTasksTool, CompleteTaskTool, DeleteTaskTool, GetDailyBriefingTool
from app.tools.media import PauseMusicTool, ResumeMusicTool, SkipMusicTrackTool, AdjustVolumeTool
from app.tools.projects import OpenFolderTool, FindProjectAndOpenTool, OpenProjectGitHubTool
from app.tools.contacts import (
    CallContactTool,
    MessageContactTool,
    ListContactsTool,
    AddContactTool,
    DeleteContactTool,
    ImportContactsTool,
    FindContactTool
)
from app.tools.camera import OpenCameraTool, RecordVideoTool
from app.tools.gallery import OpenGalleryTool, ShowRecentPhotosTool
from app.tools.gmail import (
    OpenGmailTool,
    FindRecruiterEmailsTool,
    OpenEmailThreadTool,
    ReadLatestEmailTool,
    DraftEmailTool,
    SendEmailTool
)
from app.tools.logs import CleanLogsTool
from app.tools.workstation import SaveWorkstationStateTool, RestoreWorkstationStateTool

def register_default_tools(registry: ToolRegistry = tool_registry) -> None:
    """Register all standard DADUS tools."""
    tools = [
        # Contacts & Communication
        FindContactTool(),
        CallContactTool(),
        MessageContactTool(),
        ListContactsTool(),
        AddContactTool(),
        DeleteContactTool(),
        ImportContactsTool(),
        # Desktop Applications
        OpenAppTool(),
        CloseAppTool(),
        ListInstalledAppsTool(),
        # Music & Media
        PlayMusicTool(),
        PauseMusicTool(),
        ResumeMusicTool(),
        SkipMusicTrackTool(),
        # Browser & Search
        OpenBrowserTool(),
        SearchWebTool(),
        SearchYouTubeTool(),
        # Windows System & Hardware
        SetVolumeTool(),
        AdjustVolumeTool(),
        MuteVolumeTool(),
        TakeScreenshotTool(),
        GetCurrentTimeTool(),
        GetSystemStatusTool(),
        LockDeviceTool(),
        ToggleBluetoothTool(),
        # Files & Projects
        SearchFilesTool(),
        DeleteFileOrFolderTool(),
        OpenFolderTool(),
        FindProjectAndOpenTool(),
        OpenProjectGitHubTool(),
        # Alarms, Reminders & Schedule
        SetAlarmTool(),
        ListAlarmsTool(),
        CancelAlarmTool(),
        ModifyAlarmTool(),
        CreateReminderTool(),
        ListRemindersTool(),
        GetTodayScheduleTool(),
        CreateScheduleItemTool(),
        # Productivity & Tasks
        CreateTaskTool(),
        ListTasksTool(),
        CompleteTaskTool(),
        DeleteTaskTool(),
        GetDailyBriefingTool(),
        # Long-Term Memory
        StoreMemoryTool(),
        ForgetMemoryTool(),
        # Gmail & Email Assistant
        OpenGmailTool(),
        FindRecruiterEmailsTool(),
        OpenEmailThreadTool(),
        ReadLatestEmailTool(),
        DraftEmailTool(),
        SendEmailTool(),
        # Camera & Gallery
        OpenCameraTool(),
        RecordVideoTool(),
        OpenGalleryTool(),
        ShowRecentPhotosTool(),
        # Safe Log & Maintenance
        CleanLogsTool(),
        # Workstation State Snapshots
        SaveWorkstationStateTool(),
        RestoreWorkstationStateTool()
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
