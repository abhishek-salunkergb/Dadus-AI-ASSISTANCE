"""System integration package for DADUS."""
from app.system.tray import dadus_tray
from app.system.hotkey import global_hotkey
from app.system.notifications import notify_user
from app.system.single_instance import single_instance
from app.system.autostart import autostart_manager

__all__ = [
    "dadus_tray",
    "global_hotkey",
    "notify_user",
    "single_instance",
    "autostart_manager"
]
