"""Tests for Phase 5 Windows System Lifecycle, Single-Instance Lock, and Autostart."""
from unittest.mock import patch, MagicMock
import pytest

from app.system.single_instance import SingleInstanceLock, ERROR_ALREADY_EXISTS
from app.system.autostart import WindowsAutostartManager

def test_single_instance_lock_first_acquire():
    """Verify single instance lock acquires successfully when no other instance exists."""
    lock = SingleInstanceLock(mutex_name="Local\\TEST_DADUS_MUTEX_1")
    acquired = lock.acquire()
    assert acquired is True
    assert lock.is_already_running is False
    lock.release()

@patch("ctypes.windll.kernel32.GetLastError")
def test_single_instance_lock_duplicate_detection(mock_error):
    """Verify second instance detects existing mutex and returns False."""
    mock_error.return_value = ERROR_ALREADY_EXISTS
    lock = SingleInstanceLock(mutex_name="Local\\TEST_DADUS_MUTEX_2")
    acquired = lock.acquire()
    assert acquired is False
    assert lock.is_already_running is True
    lock.release()

def test_autostart_command_construction():
    """Verify construction of silent background startup command."""
    cmd = WindowsAutostartManager.get_launch_command(tray_mode=True)
    assert "run.py" in cmd
    assert "--tray" in cmd

@patch("winreg.OpenKey")
@patch("winreg.QueryValueEx")
def test_autostart_check_enabled(mock_query, mock_open):
    """Verify checking autostart status in Windows registry."""
    mock_query.return_value = ("python run.py --tray", 1)
    enabled = WindowsAutostartManager.is_autostart_enabled()
    assert enabled is True
