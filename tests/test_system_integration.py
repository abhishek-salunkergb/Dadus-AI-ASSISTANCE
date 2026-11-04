"""Integration tests for Windows Audio Ducking, Lock Screen Security, Global Hotkey, and System Tray."""
import pytest
from unittest.mock import MagicMock, patch

from app.audio.ducking import AudioDucker, audio_ducker
from app.security.lock_screen import (
    is_workstation_locked,
    can_execute_on_lock_screen,
    check_lock_screen_restriction,
    SAFE_LOCK_SCREEN_TOOLS,
)
from app.system.hotkey import GlobalHotkeyListener, global_hotkey
from app.system.tray import (
    DadusSystemTray,
    dadus_tray,
    CMD_OPEN_UI,
    CMD_MORNING_BRIEFING,
    CMD_SYSTEM_STATUS,
    CMD_EXIT,
)
from app.agent.agent import dadus_agent
from app.agent.planner import task_planner, ExecutionPlan, PlanStep


# =====================================================================
# 1. Audio Ducking Tests
# =====================================================================

def test_audio_ducker_initialization():
    """Verify AudioDucker defaults and attributes."""
    ducker = AudioDucker(duck_ratio=0.3)
    assert ducker.duck_ratio == 0.3
    assert ducker._is_ducked is False
    assert ducker._original_volume is None


def test_audio_ducker_mocked_duck_and_restore():
    """Verify duck and restore modifies master volume level and restores correctly."""
    ducker = AudioDucker(duck_ratio=0.25)
    mock_volume = MagicMock()
    mock_volume.GetMasterVolumeLevelScalar.return_value = 0.8

    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers") as mock_speakers:
        mock_speakers.return_value.EndpointVolume = mock_volume

        # 1. Duck
        res = ducker.duck()
        assert res is True
        assert ducker._is_ducked is True
        assert ducker._original_volume == 0.8
        # ducked level = max(0.05, 0.8 * 0.25) = 0.2
        mock_volume.SetMasterVolumeLevelScalar.assert_called_with(pytest.approx(0.2), None)

        # 2. Idempotent duck
        res2 = ducker.duck()
        assert res2 is True

        # 3. Restore
        res_restore = ducker.restore()
        assert res_restore is True
        assert ducker._is_ducked is False
        assert ducker._original_volume is None
        mock_volume.SetMasterVolumeLevelScalar.assert_called_with(0.8, None)

        # 4. Idempotent restore
        res_restore2 = ducker.restore()
        assert res_restore2 is True


def test_audio_ducker_context_manager():
    """Verify AudioDucker works safely as a Python context manager."""
    ducker = AudioDucker(duck_ratio=0.2)
    mock_volume = MagicMock()
    mock_volume.GetMasterVolumeLevelScalar.return_value = 0.6

    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers") as mock_speakers:
        mock_speakers.return_value.EndpointVolume = mock_volume

        with ducker:
            assert ducker._is_ducked is True

        assert ducker._is_ducked is False


# =====================================================================
# 2. Lock Screen Security Tests
# =====================================================================

def test_lock_screen_safelist_coverage():
    """Verify whitelist contains safe query and playback tools but excludes OS modifications."""
    # Permitted tools
    for safe_tool in ["get_current_time", "get_daily_briefing", "list_tasks", "pause_music", "play_music", "adjust_volume"]:
        assert can_execute_on_lock_screen(safe_tool) is True

    # Blocked tools
    for unsafe_tool in ["delete_file_or_folder", "find_project_and_open", "kill_process", "open_installed_application"]:
        assert can_execute_on_lock_screen(unsafe_tool) is False


def test_lock_screen_restriction_when_locked(monkeypatch):
    """Verify refusal messages are returned only when workstation is locked."""
    monkeypatch.setattr("app.security.lock_screen.is_workstation_locked", lambda: True)

    # Safe tool permitted
    assert check_lock_screen_restriction("get_current_time") is None

    # Sensitive tool refused
    refusal = check_lock_screen_restriction("delete_file_or_folder")
    assert refusal is not None
    assert "unlock your PC" in refusal


def test_lock_screen_restriction_when_unlocked(monkeypatch):
    """Verify no restrictions apply when workstation is unlocked."""
    monkeypatch.setattr("app.security.lock_screen.is_workstation_locked", lambda: False)

    assert check_lock_screen_restriction("delete_file_or_folder") is None
    assert check_lock_screen_restriction("find_project_and_open") is None


def test_agent_enforces_lock_screen_on_direct_tools(monkeypatch):
    """Verify DADUS agent intercepts restricted tool execution if workstation is locked."""
    monkeypatch.setattr("app.security.lock_screen.is_workstation_locked", lambda: True)

    # Attempting to delete a file while locked
    res = dadus_agent.process_input("Delete test_file.txt", session_id="test_lock_session")
    assert "unlock your pc" in res.text.lower()


def test_planner_enforces_lock_screen_on_multi_step(monkeypatch):
    """Verify task planner stops execution if any step requires a restricted tool on locked PC."""
    monkeypatch.setattr("app.security.lock_screen.is_workstation_locked", lambda: True)

    plan = ExecutionPlan(
        goal="Open project and editor",
        explanation="Testing locked multi-step",
        steps=[
            PlanStep(step_number=1, tool_name="find_project_and_open", arguments={"project_name": "demo"}, description="Find project")
        ]
    )

    success, final_msg, results = task_planner.execute_plan(plan, "Find my demo project")
    assert success is False
    assert "unlock your pc" in final_msg.lower()
    assert results[0].get("error") == "lock_screen_restriction"


# =====================================================================
# 3. Global Hotkey Listener Tests
# =====================================================================

def test_global_hotkey_listener_initialization():
    """Verify hotkey listener configuration and state."""
    listener = GlobalHotkeyListener(key="D")
    assert listener.key == ord("D")
    assert listener._running is False
    assert listener._thread is None


def test_global_hotkey_lifecycle():
    """Verify hotkey start and stop."""
    listener = GlobalHotkeyListener(key="K")
    triggered = []

    def mock_cb():
        triggered.append(True)

    with patch("threading.Thread") as mock_thread:
        res = listener.start(mock_cb)
        assert res is True
        assert listener._running is True
        assert listener._callback == mock_cb

        listener.stop()
        assert listener._running is False


# =====================================================================
# 4. Windows System Tray Daemon Tests
# =====================================================================

def test_system_tray_initialization():
    """Verify tray attributes."""
    tray = DadusSystemTray()
    assert tray.hwnd is None
    assert tray._running is False
    assert tray._thread is None


def test_system_tray_command_dispatch():
    """Verify tray command handling for Dashboard, Briefing, and Status."""
    tray = DadusSystemTray()

    with patch("webbrowser.open") as mock_browser:
        tray._on_command(None, None, CMD_OPEN_UI, None)
        mock_browser.assert_called_once()

    with patch("app.agent.agent.dadus_agent.process_input") as mock_agent, \
         patch("app.voice.tts.get_tts_provider") as mock_tts:
        mock_agent.return_value = MagicMock(text="Your morning briefing is ready.")
        mock_speaker = MagicMock()
        mock_tts.return_value = mock_speaker

        tray._on_command(None, None, CMD_MORNING_BRIEFING, None)
        mock_agent.assert_called_with("Give me my morning briefing.")
        mock_speaker.speak.assert_called_with("Your morning briefing is ready.")

        tray._on_command(None, None, CMD_SYSTEM_STATUS, None)
        mock_agent.assert_called_with("System status")


# =====================================================================
# 5. Native Desktop Notifications & System Resilience Tests
# =====================================================================

def test_desktop_notifications_dispatch():
    """Verify show_desktop_notification dispatches cleanly without exceptions."""
    from app.system.notifications import show_desktop_notification
    with patch("subprocess.run") as mock_run:
        res = show_desktop_notification("Test Alert", "Reminder detail", async_mode=False)
        assert res is True
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd_args = args[0]
        assert "powershell.exe" in cmd_args[0]
        assert "Test Alert" in cmd_args[-1]


def test_database_wal_and_busy_timeout():
    """Verify database connection enables SQLite busy timeout and journal mode."""
    from app.database.database import engine
    with engine.connect() as conn:
        res = conn.exec_driver_sql("PRAGMA busy_timeout").fetchone()
        assert res is not None
        assert res[0] == 5000


def test_focus_existing_app_window_activated():
    """Verify OpenAppTool switches to active window if application is already running."""
    from app.tools.apps import OpenAppTool

    with patch("app.tools.apps.focus_existing_app", return_value=True):
        tool = OpenAppTool()
        res = tool.execute(app_name="Notepad")
        assert res.success is True
        assert res.data["mode"] == "window_focused"
        assert "Switched to" in res.message


def test_reminder_daemon_desktop_toast_called():
    """Verify ReminderDaemon invokes show_desktop_notification for due alerts."""
    from app.productivity.reminder_daemon import ReminderDaemon
    from app.database.database import get_db_context
    from app.database.models import Reminder
    from datetime import datetime, timedelta

    daemon = ReminderDaemon(check_interval_seconds=1)
    past_time = datetime.now() - timedelta(minutes=1)

    with get_db_context() as db:
        rem = Reminder(title="Test Toast Reminder", target_time=past_time, status="pending", recurrence="none")
        db.add(rem)
        db.flush()
        rem_id = rem.id

    with patch("app.system.notifications.show_desktop_notification") as mock_toast, \
         patch("app.voice.tts.get_tts_provider"):
        daemon._check_due_reminders()
        assert mock_toast.called
        call_kwargs = mock_toast.call_args[1]
        assert "Test Toast Reminder" in call_kwargs.get("message", "")

    with get_db_context() as db:
        saved = db.query(Reminder).filter(Reminder.id == rem_id).first()
        if saved:
            db.delete(saved)
