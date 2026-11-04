"""Global system-wide hotkey listener for DADUS.
Allows summoning DADUS from anywhere in Windows (e.g. Alt + Shift + D)
just like holding the iPhone Side Button for Siri.
"""
import ctypes
import ctypes.wintypes
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger("DADUS.Hotkey")

# Windows message constants
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_SHIFT = 0x0004
HOTKEY_ID = 1001

class GlobalHotkeyListener:
    """Listens for a global Windows hotkey across all applications."""

    def __init__(self, key: str = "D", modifiers: int = MOD_ALT | MOD_SHIFT):
        self.key = ord(key.upper())
        self.modifiers = modifiers
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self._callback: Optional[Callable[[], None]] = None

    def start(self, callback: Callable[[], None]) -> bool:
        """Start listening for the global hotkey on a background thread."""
        if self._running:
            return True

        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        logger.info("Global hotkey registered: Alt + Shift + D")
        return True

    def stop(self) -> None:
        """Stop listening and unregister hotkey."""
        self._running = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        logger.info("Global hotkey unregistered.")

    def _message_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        # Register hotkey on this thread's message queue
        success = user32.RegisterHotKey(0, HOTKEY_ID, self.modifiers, self.key)
        if not success:
            logger.warning("Could not register global hotkey (might be occupied by another app)")
            return

        try:
            msg = ctypes.wintypes.MSG()
            while self._running:
                # GetMessage blocks until a message arrives
                res = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if res <= 0:
                    break

                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    logger.info("Global hotkey triggered!")
                    if self._callback:
                        threading.Thread(target=self._callback, daemon=True).start()

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(0, HOTKEY_ID)

global_hotkey = GlobalHotkeyListener()
