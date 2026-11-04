"""Windows Named Mutex single-instance protection for DADUS.
Prevents duplicate application instances from spawning and contending for audio hardware.
"""
import ctypes
import logging
from typing import Optional

logger = logging.getLogger("DADUS.SingleInstance")

ERROR_ALREADY_EXISTS = 183

class SingleInstanceLock:
    """
    Enforces a single running instance of DADUS using a Win32 Named Mutex.
    Works without administrative privileges.
    """

    def __init__(self, mutex_name: str = "Local\\DADUS_AI_AGENT_MUTEX"):
        self.mutex_name = mutex_name
        self.mutex_handle: Optional[int] = None
        self.is_already_running = False

    def acquire(self) -> bool:
        """
        Attempts to acquire the named mutex.
        Returns True if this is the only instance, or False if another instance is already active.
        """
        try:
            kernel32 = ctypes.windll.kernel32
            # CreateMutexW(security_attributes, initial_owner, name)
            self.mutex_handle = kernel32.CreateMutexW(None, True, self.mutex_name)
            last_error = kernel32.GetLastError()

            if last_error == ERROR_ALREADY_EXISTS:
                self.is_already_running = True
                logger.warning(f"Another instance of DADUS is already running with mutex '{self.mutex_name}'.")
                return False

            self.is_already_running = False
            logger.info(f"Acquired single-instance mutex '{self.mutex_name}'.")
            return True
        except Exception as ex:
            logger.error(f"Failed to create single-instance mutex: {ex}")
            # In case of platform/permissions error, do not block execution
            return True

    def release(self) -> None:
        """Release the Win32 mutex handle upon application shutdown."""
        if self.mutex_handle:
            try:
                ctypes.windll.kernel32.ReleaseMutex(self.mutex_handle)
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
                logger.info("Released single-instance mutex.")
            except Exception as ex:
                logger.debug(f"Error releasing mutex: {ex}")

single_instance = SingleInstanceLock()

