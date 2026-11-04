"""Windows startup configuration manager for DADUS.
Enables or disables automatic startup on user login via the HKCU Windows Registry.
Never requires administrator privileges.
"""
import sys
import os
import winreg
import logging
from pathlib import Path
from app.config.settings import settings

logger = logging.getLogger("DADUS.Autostart")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "DADUS_AI_Agent"

class WindowsAutostartManager:
    """Manages Windows startup registry entry for DADUS."""

    @classmethod
    def get_launch_command(cls, tray_mode: bool = True) -> str:
        """Constructs the executable command line for startup."""
        python_exe = sys.executable
        # If pythonw.exe exists in the same directory, prefer it for silent background launch
        pythonw = Path(python_exe).parent / "pythonw.exe"
        runner_exe = str(pythonw) if pythonw.exists() else python_exe

        run_script = Path(__file__).resolve().parent.parent.parent / "run.py"
        flag = "--tray" if tray_mode else ""
        return f'"{runner_exe}" "{run_script}" {flag}'.strip()

    @classmethod
    def is_autostart_enabled(cls) -> bool:
        """Check if DADUS is registered in the Windows Run key."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(val)
        except FileNotFoundError:
            return False
        except Exception as ex:
            logger.debug(f"Error checking autostart registry: {ex}")
            return False

    @classmethod
    def enable_autostart(cls, tray_mode: bool = True) -> bool:
        """Register DADUS to start on Windows user login."""
        command = cls.get_launch_command(tray_mode=tray_mode)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            logger.info(f"Enabled autostart on Windows login: {command}")
            return True
        except Exception as ex:
            logger.error(f"Failed to enable Windows autostart: {ex}")
            return False

    @classmethod
    def disable_autostart(cls) -> bool:
        """Remove DADUS from the Windows Run key."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    logger.info("Disabled autostart from Windows login.")
                    return True
                except FileNotFoundError:
                    return True
        except Exception as ex:
            logger.error(f"Failed to disable Windows autostart: {ex}")
            return False

autostart_manager = WindowsAutostartManager()

