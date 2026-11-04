"""Windows Workstation Lock Screen detector and security enforcer for DADUS.
Ensures DADUS can answer safe voice queries (time, schedule, music) while locked,
without compromising security or bypassing Windows authentication.
"""
import ctypes
import logging
from typing import Optional, Set

logger = logging.getLogger("DADUS.LockScreen")

# Set of tool names safe to execute while workstation is locked
SAFE_LOCK_SCREEN_TOOLS: Set[str] = {
    "get_current_time",
    "get_daily_briefing",
    "list_tasks",
    "get_today_schedule",
    "list_reminders",
    "pause_music",
    "resume_music",
    "skip_music_track",
    "adjust_volume",
    "set_volume",
    "play_music",
}

def is_workstation_locked() -> bool:
    """Check if Windows desktop workstation is currently locked."""
    try:
        user32 = ctypes.windll.user32
        # DESKTOP_SWITCHDESKTOP = 0x0100
        desk = user32.OpenInputDesktop(0, False, 0x0100)
        if desk == 0:
            return True
        user32.CloseDesktop(desk)
        return False
    except Exception as ex:
        logger.debug(f"Could not check desktop lock status: {ex}")
        return False

def can_execute_on_lock_screen(tool_name: Optional[str]) -> bool:
    """Return True if tool is permitted while PC is locked."""
    if not tool_name:
        return True
    return tool_name.lower() in SAFE_LOCK_SCREEN_TOOLS

def check_lock_screen_restriction(tool_name: Optional[str]) -> Optional[str]:
    """Return refusal message if workstation is locked and tool is restricted."""
    if not is_workstation_locked():
        return None

    if tool_name and not can_execute_on_lock_screen(tool_name):
        logger.warning(f"Blocked tool '{tool_name}' because Windows workstation is locked")
        return "Boss, please unlock your PC first to perform this action for your security."

    return None
