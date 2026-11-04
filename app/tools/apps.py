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
from app.security.permissions import PermissionLevel, permission_manager

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
    _cached_apps: Optional[Dict[str, AppInfo]] = None
    _cache_time: float = 0.0
    _CACHE_TTL_SECONDS: float = 600.0

    @classmethod
    def get_installed_apps(cls, force_refresh: bool = False) -> Dict[str, AppInfo]:
        """Scans registry, start menu, and PATH to index installed applications with fast caching."""
        import time
        now = time.time()
        if not force_refresh and cls._cached_apps is not None and (now - cls._cache_time < cls._CACHE_TTL_SECONDS):
            return cls._cached_apps

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

        cls._cached_apps = apps
        cls._cache_time = now
        return apps

    @classmethod
    def find_app(cls, query: str) -> Optional[AppInfo]:
        """Fuzzy and alias match an application name."""
        clean_q = query.strip().lower()

        # Instant check for well-known Windows system tools (0.00001s)
        if clean_q in SYSTEM_APPS:
            return AppInfo(name=clean_q.title(), executable_or_path=SYSTEM_APPS[clean_q], source="system")

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

# Well-known web services for automatic browser fallback when desktop app is not installed
WEB_APP_URLS = {
    "youtube": "https://www.youtube.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "prime video": "https://www.primevideo.com",
    "prime": "https://www.primevideo.com",
    "amazon": "https://www.amazon.com",
    "gmail": "https://mail.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "chatgpt": "https://chatgpt.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitch": "https://www.twitch.tv",
    "spotify": "https://open.spotify.com",
    "discord": "https://discord.com/app",
    "telegram": "https://web.telegram.org",
    "canva": "https://www.canva.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
}

def focus_existing_app(app_name: str, executable_or_path: Optional[str] = None) -> bool:
    """
    Attempts to bring an existing running application window to the foreground.
    Prioritizes WScript.Shell AppActivate by window title or process ID.
    Returns True if an existing window was successfully focused, False if a fresh launch is needed.
    """
    clean_target = (Path(executable_or_path).stem if executable_or_path else app_name).lower().strip()

    # 1. Quick AppActivate attempt with application title / name
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        if shell.AppActivate(app_name):
            logger.info(f"Existing window for '{app_name}' brought to foreground via AppActivate.")
            return True
        if executable_or_path:
            stem = Path(executable_or_path).stem
            if stem.lower() != app_name.lower() and shell.AppActivate(stem):
                logger.info(f"Existing window for executable '{stem}' brought to foreground.")
                return True
    except Exception as ex:
        logger.debug(f"Title-based AppActivate check failed: {ex}")

    # 2. Check active running processes and activate via PID
    try:
        import psutil
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        target_stem = clean_target.replace(".exe", "")
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            pname = (proc.info.get('name') or '').lower()
            if target_stem and (pname == f"{target_stem}.exe" or pname == target_stem):
                pid = proc.info['pid']
                if shell.AppActivate(pid):
                    logger.info(f"Existing process PID {pid} ({pname}) brought to foreground.")
                    return True
    except Exception as ex:
        logger.debug(f"PID-based AppActivate failed: {ex}")

    return False

# ==========================================
# Tool: open_app
# ==========================================
class OpenAppInput(BaseModel):
    app_name: str = Field(description="Name of the application to open, e.g. 'Google Chrome', 'VS Code', 'Spotify', 'YouTube'")

class OpenAppTool(BaseTool):
    name = "open_app"
    description = "Opens an application on Windows. Prioritizes native desktop app first; if not installed, automatically opens in browser."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenAppInput

    def execute(self, app_name: str) -> ToolResult:
        if not permission_manager.is_permitted("app_control"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, the Application Control permission is currently disabled in your DADUS settings. Please enable Application Control in settings to allow me to open applications.",
                error="PERMISSION_DENIED"
            )

        clean_name = app_name.strip().lower()
        logger.info(f"Executing open_app for '{app_name}'")

        # 1. Instant check for well-known web services (0.0001s: YouTube, Netflix, ChatGPT, WhatsApp, etc.)
        if clean_name in WEB_APP_URLS:
            fallback_url = WEB_APP_URLS[clean_name]
            try:
                from app.tools.browser import launch_browser_url
                launch_browser_url(fallback_url)
                return self._build_success_result(app_name, "browser_fallback", fallback_url)
            except Exception as web_ex:
                logger.error(f"Failed to open browser for '{app_name}': {web_ex}")

        # 2. Local Windows desktop application check (cached, 0.0001s)
        app_info = AppDetector.find_app(app_name)
        if not app_info:
            resolved = shutil.which(app_name)
            if resolved:
                app_info = AppInfo(name=app_name, executable_or_path=resolved, source="path")

        # If found as a local app, check if already running or launch it asynchronously!
        if app_info:
            target = app_info.executable_or_path

            # If application window is already running, switch to it instead of spawning duplicate processes
            if focus_existing_app(app_info.name, target):
                return self._build_success_result(app_info.name, "window_focused", target)

            try:
                # Direct verified launch
                if target.lower().endswith(".lnk") or os.path.exists(target):
                    os.startfile(target)
                else:
                    subprocess.Popen([target], shell=False)

                import time
                time.sleep(0.3)
                return self._build_success_result(app_info.name, "desktop_app", target)
            except Exception as ex:
                logger.warning(f"Local app launch failed for '{app_name}', attempting browser fallback: {ex}")

        # 3. Partial Web App matching or Search Fallback
        fallback_url = None
        for key, url in WEB_APP_URLS.items():
            if key in clean_name or clean_name in key:
                fallback_url = url
                break

        if not fallback_url:
            # If query looks like a domain name (e.g. "google.com")
            if "." in clean_name and not clean_name.endswith(".exe"):
                fallback_url = f"https://{clean_name}"
            elif any(w in clean_name for w in ["search", "web", "site"]):
                fallback_url = f"https://www.google.com/search?q={clean_name}"

        if fallback_url:
            try:
                from app.tools.browser import launch_browser_url
                launch_browser_url(fallback_url)
                return self._build_success_result(app_name, "browser_fallback", fallback_url)
            except Exception as web_ex:
                logger.error(f"Failed to open browser for '{app_name}': {web_ex}")

        return ToolResult(
            tool_name=self.name,
            success=False,
            message=f"Boss, I couldn't find '{app_name}' installed as an app or as a recognized web service.",
            error="APP_NOT_FOUND"
        )

    def _build_success_result(self, app_name: str, mode: str, target: str) -> ToolResult:
        # Standard clean app launch response: opens directly without asking redundant questions
        if mode == "browser_fallback":
            msg = f"Opening {app_name.title()} in your browser, boss."
        elif mode == "window_focused":
            msg = f"Switched to {app_name.title()}, boss."
        else:
            msg = f"Opening {app_name.title()}, boss."
        url_target = target if (isinstance(target, str) and (target.startswith("http://") or target.startswith("https://"))) else None
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=msg,
            data={"app_name": app_name, "target": target, "mode": mode, "url": url_target}
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
        if not permission_manager.is_permitted("app_control"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, the Application Control permission is currently disabled in your DADUS settings. Please enable Application Control in settings to allow me to close applications.",
                error="PERMISSION_DENIED"
            )

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
