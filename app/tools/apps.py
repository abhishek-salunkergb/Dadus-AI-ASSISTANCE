"""Application detection, launching, and process termination for Windows."""
import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import psutil

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel

logger = logging.getLogger("DADUS.Apps")

# Well-known Windows system application commands
SYSTEM_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "paint": "mspaint.exe",
    "snipping tool": "snippingtool.exe"
}

class AppInfo(BaseModel):
    name: str
    executable_or_path: str
    source: str  # registry, start_menu, system, path

class AppDetector:
    """Discovers installed desktop applications across Windows."""

    @staticmethod
    def get_installed_apps() -> Dict[str, AppInfo]:
        """Scans registry, start menu, and PATH to index installed applications."""
        apps: Dict[str, AppInfo] = {}

        # 1. System apps
        for name, exe in SYSTEM_APPS.items():
            apps[name.lower()] = AppInfo(name=name.title(), executable_or_path=exe, source="system")

        # 2. Windows Start Menu shortcuts (.lnk files)
        start_menu_dirs = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs")
        ]
        for sdir in start_menu_dirs:
            if os.path.exists(sdir):
                for root, _, files in os.walk(sdir):
                    for file in files:
                        if file.lower().endswith(".lnk"):
                            shortcut_name = file[:-4].strip()
                            full_path = os.path.join(root, file)
                            lower_name = shortcut_name.lower()
                            if lower_name not in apps:
                                apps[lower_name] = AppInfo(
                                    name=shortcut_name,
                                    executable_or_path=full_path,
                                    source="start_menu"
                                )

        # 3. Windows Registry (Uninstall keys)
        try:
            import winreg
            hives = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
            ]
            for hive, subkey in hives:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                skey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, skey_name) as skey:
                                    try:
                                        display_name, _ = winreg.QueryValueEx(skey, "DisplayName")
                                        if display_name:
                                            # Try to get InstallLocation or DisplayIcon
                                            exe_path = ""
                                            try:
                                                icon, _ = winreg.QueryValueEx(skey, "DisplayIcon")
                                                if icon and icon.lower().endswith(".exe"):
                                                    exe_path = icon.split(",")[0].strip('"')
                                            except OSError:
                                                pass

                                            lower_dn = display_name.lower()
                                            if lower_dn not in apps:
                                                apps[lower_dn] = AppInfo(
                                                    name=display_name,
                                                    executable_or_path=exe_path or display_name,
                                                    source="registry"
                                                )
                                    except OSError:
                                        pass
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass

        # 4. Standard PATH lookup for developer tools
        dev_tools = ["code", "cursor", "git", "python", "node", "npm", "wt", "spotify"]
        for tool in dev_tools:
            found = shutil.which(tool)
            if found:
                apps[tool.lower()] = AppInfo(name=tool.title(), executable_or_path=found, source="path")

        # 5. Common Spotify / Chrome / VS Code fallback locations
        special_paths = {
            "spotify": [
                os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
                r"C:\Program Files\Spotify\Spotify.exe"
            ],
            "google chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
            ],
            "visual studio code": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                r"C:\Program Files\Microsoft VS Code\Code.exe"
            ],
            "cursor": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe")
            ]
        }
        for name, paths in special_paths.items():
            for p in paths:
                if os.path.exists(p):
                    apps[name] = AppInfo(name=name.title(), executable_or_path=p, source="special")
                    break

        return apps

    @classmethod
    def find_app(cls, query: str) -> Optional[AppInfo]:
        """Fuzzy and alias match an application name."""
        clean_q = query.strip().lower()
        apps = cls.get_installed_apps()

        # Direct exact match
        if clean_q in apps:
            return apps[clean_q]

        # Common aliases
        aliases = {
            "chrome": "google chrome",
            "vscode": "visual studio code",
            "vs code": "visual studio code",
            "code editor": "visual studio code",
            "editor": "visual studio code",
            "code": "visual studio code",
            "spotify": "spotify",
            "edge": "microsoft edge",
            "calc": "calculator",
            "explorer": "file explorer"
        }
        if clean_q in aliases:
            target = aliases[clean_q]
            if target in apps:
                return apps[target]

        # Substring / partial match
        for key, info in apps.items():
            if clean_q in key or key in clean_q or clean_q in info.name.lower():
                return info

        return None

# ==========================================
# Tool: open_app
# ==========================================
class OpenAppInput(BaseModel):
    app_name: str = Field(description="Name of the application to open, e.g. 'Google Chrome', 'VS Code', 'Spotify'")

class OpenAppTool(BaseTool):
    name = "open_app"
    description = "Opens a desktop application on Windows (e.g. Chrome, VS Code, Spotify, Notepad, Calculator)."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenAppInput

    def execute(self, app_name: str) -> ToolResult:
        logger.info(f"Executing open_app for '{app_name}'")
        app_info = AppDetector.find_app(app_name)

        if not app_info:
            # Fallback: check if executable exists directly on PATH
            resolved = shutil.which(app_name)
            if resolved:
                app_info = AppInfo(name=app_name, executable_or_path=resolved, source="path")

        if not app_info:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't find '{app_name}' installed on your system.",
                error="APP_NOT_FOUND"
            )

        target = app_info.executable_or_path
        try:
            if target.lower().endswith(".lnk") or os.path.exists(target):
                os.startfile(target)
            else:
                subprocess.Popen([target], shell=False)

            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Opening {app_info.name}.",
                data={"app_name": app_info.name, "target": target}
            )
        except Exception as ex:
            logger.error(f"Failed to launch app '{app_name}': {ex}")
            # Try os.startfile as fallback for shell commands
            try:
                os.startfile(app_name)
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message=f"Opening {app_info.name}.",
                    data={"app_name": app_info.name}
                )
            except Exception:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=f"Boss, I couldn't open {app_name}.",
                    error=str(ex)
                )

# ==========================================
# Tool: close_app
# ==========================================
class CloseAppInput(BaseModel):
    app_name: str = Field(description="Name of the application to close, e.g. 'Chrome', 'Notepad'")

class CloseAppTool(BaseTool):
    name = "close_app"
    description = "Closes a running desktop application on Windows."
    permission_level = PermissionLevel.SAFE
    args_schema = CloseAppInput

    def execute(self, app_name: str) -> ToolResult:
        clean_name = app_name.strip().lower()
        target_patterns = [clean_name]

        # Aliases for process names
        alias_proc = {
            "chrome": ["chrome.exe"],
            "google chrome": ["chrome.exe"],
            "vs code": ["code.exe"],
            "vscode": ["code.exe"],
            "visual studio code": ["code.exe"],
            "spotify": ["spotify.exe"],
            "notepad": ["notepad.exe"],
            "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
            "edge": ["msedge.exe"],
            "microsoft edge": ["msedge.exe"]
        }
        if clean_name in alias_proc:
            target_patterns.extend(alias_proc[clean_name])

        closed_count = 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                pname = proc.info['name'].lower() if proc.info['name'] else ""
                if any(p in pname for p in target_patterns):
                    proc.terminate()
                    closed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if closed_count > 0:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Closed {app_name}.",
                data={"closed_processes": closed_count}
            )
        else:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, {app_name} is not currently running.",
                data={"closed_processes": 0}
            )

# ==========================================
# Tool: list_installed_apps
# ==========================================
class ListAppsInput(BaseModel):
    filter: Optional[str] = Field(default=None, description="Optional text filter to search for applications")

class ListInstalledAppsTool(BaseTool):
    name = "list_installed_apps"
    description = "Lists installed desktop applications on the system."
    permission_level = PermissionLevel.SAFE
    args_schema = ListAppsInput

    def execute(self, filter: Optional[str] = None) -> ToolResult:
        apps = AppDetector.get_installed_apps()
        app_list = []
        filter_lower = filter.lower() if filter else None

        for key, info in sorted(apps.items(), key=lambda x: x[1].name):
            if filter_lower and filter_lower not in key and filter_lower not in info.name.lower():
                continue
            app_list.append(info.name)

        unique_apps = sorted(list(set(app_list)))
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Found {len(unique_apps)} applications.",
            data={"apps": unique_apps[:50]}  # limit output for readability
        )
