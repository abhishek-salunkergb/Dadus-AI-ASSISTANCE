"""Windows System Tray Daemon for DADUS.
Allows DADUS to run silently in the background with zero visible windows,
listening for 'Hey Dadus' just like Siri on the iPhone.
"""
import os
import sys
import webbrowser
import logging
import threading
from typing import Optional, Callable
import win32gui
import win32con

from app.config.settings import settings

logger = logging.getLogger("DADUS.Tray")

# Custom window message for tray events
WM_TRAY_CALLBACK = win32con.WM_USER + 20

# Command IDs for tray menu
CMD_OPEN_UI = 101
CMD_MORNING_BRIEFING = 102
CMD_SYSTEM_STATUS = 103
CMD_EXIT = 104

class DadusSystemTray:
    """Native Windows System Tray Icon and background lifecycle manager."""

    def __init__(self):
        self.hwnd = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._on_exit_callback: Optional[Callable[[], None]] = None

    def start(self, on_exit: Optional[Callable[[], None]] = None) -> None:
        """Start the system tray icon on a dedicated background thread."""
        if self._running:
            return

        self._running = True
        self._on_exit_callback = on_exit
        self._thread = threading.Thread(target=self._run_tray_loop, daemon=True)
        self._thread.start()
        logger.info("DADUS Windows System Tray daemon started.")

    def stop(self) -> None:
        """Remove tray icon and destroy window."""
        self._running = False
        if self.hwnd:
            try:
                nid = (self.hwnd, 0)
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
                win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        logger.info("DADUS System Tray daemon stopped.")

    def _run_tray_loop(self) -> None:
        message_map = {
            win32con.WM_CLOSE: self._on_close,
            win32con.WM_DESTROY: self._on_destroy,
            win32con.WM_COMMAND: self._on_command,
            WM_TRAY_CALLBACK: self._on_tray_event,
        }

        wc = win32gui.WNDCLASS()
        wc.hInstance = win32gui.GetModuleHandle(None)
        wc.lpszClassName = "DadusSystemTrayClass"
        wc.lpfnWndProc = message_map

        try:
            class_atom = win32gui.RegisterClass(wc)
        except win32gui.error:
            # Class already registered
            class_atom = "DadusSystemTrayClass"

        # Create hidden message-only window
        self.hwnd = win32gui.CreateWindow(
            class_atom,
            "DADUS Tray",
            0,
            0, 0, 0, 0,
            0, 0,
            wc.hInstance,
            None
        )

        hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        nid = (
            self.hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            WM_TRAY_CALLBACK,
            hicon,
            "DADUS - Personal AI Operating Assistant (Active)"
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

        # Message pump
        win32gui.PumpMessages()

    def _on_close(self, hwnd, msg, wparam, lparam):
        win32gui.DestroyWindow(hwnd)
        return 0

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        nid = (self.hwnd, 0)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        win32gui.PostQuitMessage(0)
        return 0

    def _on_command(self, hwnd, msg, wparam, lparam):
        cmd_id = win32gui.LOWORD(wparam)
        if cmd_id == CMD_OPEN_UI:
            webbrowser.open(f"http://{settings.API_HOST}:{settings.API_PORT}")
        elif cmd_id == CMD_MORNING_BRIEFING:
            from app.agent.agent import dadus_agent
            from app.voice.tts import get_tts_provider
            resp = dadus_agent.process_input("Give me my morning briefing.")
            get_tts_provider().speak(resp.text)
        elif cmd_id == CMD_SYSTEM_STATUS:
            from app.agent.agent import dadus_agent
            from app.voice.tts import get_tts_provider
            resp = dadus_agent.process_input("System status")
            get_tts_provider().speak(resp.text)
        elif cmd_id == CMD_EXIT:
            logger.info("Exit requested from Windows System Tray menu.")
            if self._on_exit_callback:
                self._on_exit_callback()
            self.stop()
            os._exit(0)
        return 0

    def _on_tray_event(self, hwnd, msg, wparam, lparam):
        # Left click: open UI
        if lparam == win32con.WM_LBUTTONUP:
            webbrowser.open(f"http://{settings.API_HOST}:{settings.API_PORT}")
        # Right click: show context menu
        elif lparam == win32con.WM_RBUTTONUP:
            menu = win32gui.CreatePopupMenu()
            win32gui.AppendMenu(menu, win32con.MF_STRING, CMD_OPEN_UI, "🌐 Open Dashboard")
            win32gui.AppendMenu(menu, win32con.MF_STRING, CMD_MORNING_BRIEFING, "☀️ Morning Briefing")
            win32gui.AppendMenu(menu, win32con.MF_STRING, CMD_SYSTEM_STATUS, "💻 System Status")
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
            win32gui.AppendMenu(menu, win32con.MF_STRING, CMD_EXIT, "❌ Exit DADUS")

            pos = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON,
                pos[0], pos[1],
                0,
                self.hwnd,
                None
            )
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        return 0

dadus_tray = DadusSystemTray()
