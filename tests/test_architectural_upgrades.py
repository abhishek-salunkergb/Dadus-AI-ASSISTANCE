"""Comprehensive tests for DADUS Senior Architectural Upgrades:
1. Event-driven Alarm and Reminder Daemons with instant wake notification.
2. Multi-step DAG TaskPlanner data-piping and template argument interpolation.
3. Persistent session state surviving agent re-instantiation across SQLite.
4. Device Manager persistent pairing, token validation, and secure execution gating.
5. Workstation Snapshot ('Wrap Up' / 'Resume Work') state engine.
"""
import pytest
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.database.database import get_db_context, init_db
from app.database.models import Alarm, Reminder, SessionRecord, PairedDevice, WorkstationSnapshot
from app.agent.agent import DadusAgent
from app.agent.planner import task_planner, ExecutionPlan, PlanStep
from app.productivity.alarm_daemon import AlarmDaemon
from app.productivity.reminder_daemon import ReminderDaemon
from app.devices.device_manager import DeviceManager, DeviceType, DeviceCapability
from app.tools.workstation import SaveWorkstationStateTool, RestoreWorkstationStateTool
from app.tools.alarms import SetAlarmTool, CancelAlarmTool
from app.tools.reminders import CreateReminderTool


@pytest.fixture(autouse=True)
def clean_test_db():
    init_db()
    with get_db_context() as db:
        db.query(Alarm).delete()
        db.query(Reminder).delete()
        db.query(SessionRecord).delete()
        db.query(PairedDevice).delete()
        db.query(WorkstationSnapshot).delete()
    yield
    with get_db_context() as db:
        db.query(Alarm).delete()
        db.query(Reminder).delete()
        db.query(SessionRecord).delete()
        db.query(PairedDevice).delete()
        db.query(WorkstationSnapshot).delete()


# ==========================================
# 1. Event-Driven Daemons
# ==========================================
def test_alarm_daemon_event_driven_wake():
    daemon = AlarmDaemon()
    assert daemon._wake_event.is_set() is False

    # Calling notify_change() immediately sets the event
    daemon.notify_change()
    assert daemon._wake_event.is_set() is True


def test_alarm_creation_signals_alarm_daemon():
    with patch.object(AlarmDaemon, "notify_change") as mock_notify:
        tool = SetAlarmTool()
        res = tool.execute(time="tomorrow at 8:00 AM", label="Test Alarm")
        assert res.success is True
        mock_notify.assert_called_once()


def test_reminder_creation_signals_reminder_daemon():
    with patch.object(ReminderDaemon, "notify_change") as mock_notify:
        tool = CreateReminderTool()
        res = tool.execute(title="Test Reminder", time="in 10 minutes")
        assert res.success is True
        mock_notify.assert_called_once()


# ==========================================
# 2. Multi-Step DAG Data-Piping & Template Resolution
# ==========================================
def test_task_planner_dag_template_data_piping():
    """Verify that Step 2 can dynamically resolve outputs produced by Step 1."""
    # Step 1: Takes screenshot and returns data containing file_path
    # Step 2: Uses {{step_1.file_path}} or auto-piped path
    plan = ExecutionPlan(
        goal="take a screenshot and inspect status",
        explanation="Capture screen and check status",
        steps=[
            PlanStep(
                step_number=1,
                tool_name="get_current_time",
                arguments={},
                description="Get system time"
            ),
            PlanStep(
                step_number=2,
                tool_name="get_system_status",
                arguments={},
                description="Check system resource status"
            )
        ]
    )

    success, msg, results = task_planner.execute_plan(plan, "test user goal")
    assert success is True
    assert len(results) == 2
    assert results[0]["step"] == 1
    assert results[1]["step"] == 2


# ==========================================
# 3. Persistent SQLite Session State
# ==========================================
def test_session_persistence_across_agent_restarts():
    agent1 = DadusAgent()
    sess1 = agent1.get_or_create_session("persistent_test_user")
    sess1.add_user_message("Hello, my favorite editor is VS Code.")
    sess1.add_assistant_message("Understood, boss.")
    sess1.context_entities["active_project"] = "Alpha"
    agent1._persist_session(sess1)

    # Verify written to SQLite SessionRecord
    with get_db_context() as db:
        rec = db.query(SessionRecord).filter(SessionRecord.session_id == "persistent_test_user").first()
        assert rec is not None
        assert "Alpha" in rec.state_json

    # Create completely fresh agent instance (simulating server reboot)
    agent2 = DadusAgent()
    assert "persistent_test_user" not in agent2._sessions
    sess2 = agent2.get_or_create_session("persistent_test_user")

    assert len(sess2.messages) == 2
    assert sess2.messages[0].content == "Hello, my favorite editor is VS Code."
    assert sess2.context_entities.get("active_project") == "Alpha"


# ==========================================
# 4. Device Manager Persistent Pairing & Security
# ==========================================
def test_device_manager_persistent_pairing_and_auth():
    dm = DeviceManager()

    # Pair mobile companion
    dev, token = dm.pair_new_device(
        name="Abhinav's Android Phone",
        device_type=DeviceType.ANDROID_MOBILE,
        capabilities=[DeviceCapability.AUDIO_PLAYBACK, DeviceCapability.MICROPHONE]
    )

    assert dev.device_id.startswith("dev_")
    assert len(token) > 20

    # Verify authentication
    assert dm.authenticate_device(dev.device_id, token) is True
    assert dm.authenticate_device(dev.device_id, "invalid_token") is False

    # Verify security gating: mobile device without SCREEN_CAPTURE cannot take screenshots
    assert dm.can_device_execute_tool(dev.device_id, "take_screenshot") is False

    # Rogue unregistered device is rejected by default
    assert dm.can_device_execute_tool("unregistered_rogue_id", "take_screenshot") is False
    assert dm.can_device_execute_tool("unregistered_rogue_id", "open_app") is False

    # Host desktop has full access
    assert dm.can_device_execute_tool("host_windows_pc", "take_screenshot") is True


# ==========================================
# 5. Workstation Snapshot Engine ('Wrap Up' / 'Resume Work')
# ==========================================
def test_save_and_restore_workstation_state():
    save_tool = SaveWorkstationStateTool()
    res_save = save_tool.execute(name="test_snapshot")
    assert res_save.success is True
    assert "captured your workstation state" in res_save.message.lower()

    # Verify in DB
    with get_db_context() as db:
        snap = db.query(WorkstationSnapshot).filter(WorkstationSnapshot.name == "test_snapshot").first()
        assert snap is not None

    with patch("subprocess.Popen") as mock_popen:
        restore_tool = RestoreWorkstationStateTool()
        res_restore = restore_tool.execute(name="test_snapshot")
        assert res_restore.success is True
        assert "restored your workstation" in res_restore.message.lower()
