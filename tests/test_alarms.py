"""Tests for DADUS persistent Alarm System, Natural Language Time Parsing, and Daemon Scheduler."""
import pytest
from datetime import datetime, timedelta, time as dtime
from unittest.mock import patch, MagicMock

from app.agent.agent import DadusAgent
from app.database.database import get_db_context, init_db
from app.database.models import Alarm
from app.tools.alarms import (
    SetAlarmTool,
    ListAlarmsTool,
    CancelAlarmTool,
    ModifyAlarmTool,
    parse_natural_alarm_time,
    format_alarm_time
)
from app.productivity.alarm_daemon import AlarmDaemon


@pytest.fixture(autouse=True)
def clean_alarms_db():
    """Ensure clean alarms table before and after each test."""
    init_db()
    with get_db_context() as db:
        db.query(Alarm).delete()
    yield
    with get_db_context() as db:
        db.query(Alarm).delete()


# ==========================================
# 1. Natural Language Time Parsing Tests
# ==========================================
def test_parse_alarm_time_tomorrow_6am():
    target, err = parse_natural_alarm_time("tomorrow at 6 AM")
    assert err is None
    assert target is not None
    now = datetime.now()
    assert target.date() == (now + timedelta(days=1)).date()
    assert target.hour == 6
    assert target.minute == 0


def test_parse_alarm_time_tomorrow_630am():
    target, err = parse_natural_alarm_time("tomorrow at 6:30 AM")
    assert err is None
    assert target is not None
    assert target.hour == 6
    assert target.minute == 30


def test_parse_alarm_time_compact_stt_240_oclock():
    """Verify STT transcription anomaly '240 o'clock' (two forty) parses to hour 2, min 40."""
    target, err = parse_natural_alarm_time("240 o'clock")
    assert err is None
    assert target is not None
    assert target.minute == 40
    assert target.hour in [2, 14]


def test_parse_alarm_time_relative_minutes():
    target, err = parse_natural_alarm_time("in 20 minutes")
    assert err is None
    assert target is not None
    now = datetime.now()
    diff = (target - now).total_seconds()
    assert 1190 <= diff <= 1210


def test_parse_alarm_time_ambiguous_empty():
    target, err = parse_natural_alarm_time("")
    assert target is None
    assert "what time" in err.lower()


# ==========================================
# 2. Tool Execution & Database Persistence Tests
# ==========================================
def test_set_alarm_tool_persistence():
    tool = SetAlarmTool()
    res = tool.execute(time="tomorrow at 6 AM", label="Morning workout")

    assert res.success is True
    assert "Morning workout" in res.data["alarm"]["label"] or "alarm for tomorrow at 6:00 AM" in res.message.lower()
    alarm_id = res.data["alarm"]["id"]

    # Verify SQLite persistence
    with get_db_context() as db:
        saved = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert saved is not None
        assert saved.label == "Morning workout"
        assert saved.status == "scheduled"
        assert saved.target_time.hour == 6


def test_set_alarm_duplicate_prevention():
    tool = SetAlarmTool()
    res1 = tool.execute(time="tomorrow at 6 AM", label="Wake up")
    assert res1.success is True

    # Attempting to schedule duplicate alarm at exact same time
    res2 = tool.execute(time="tomorrow at 6 AM", label="Wake up again")
    assert res2.success is True
    assert res2.data.get("duplicate") is True
    assert "already active" in res2.message.lower()

    # Verify only 1 record exists in database
    with get_db_context() as db:
        count = db.query(Alarm).filter(Alarm.status == "scheduled").count()
        assert count == 1


def test_list_alarms_tool():
    tool = SetAlarmTool()
    tool.execute(time="tomorrow at 6 AM", label="Alarm 1")
    tool.execute(time="tomorrow at 8 AM", label="Alarm 2")

    list_tool = ListAlarmsTool()
    res = list_tool.execute()

    assert res.success is True
    assert res.data["count"] == 2
    assert "6:00 AM" in res.message
    assert "8:00 AM" in res.message


def test_cancel_alarm_tool():
    tool = SetAlarmTool()
    res1 = tool.execute(time="tomorrow at 6 AM", label="Morning Run")
    alarm_id = res1.data["alarm"]["id"]

    cancel_tool = CancelAlarmTool()
    res_cancel = cancel_tool.execute(alarm_id=alarm_id)

    assert res_cancel.success is True
    assert "cancelled" in res_cancel.message.lower()

    # Verify status in database
    with get_db_context() as db:
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert alarm.status == "cancelled"


def test_cancel_all_alarms():
    tool = SetAlarmTool()
    tool.execute(time="tomorrow at 6 AM", label="Alarm 1")
    tool.execute(time="tomorrow at 7 AM", label="Alarm 2")

    cancel_tool = CancelAlarmTool()
    res = cancel_tool.execute(cancel_all=True)

    assert res.success is True
    assert res.data["cancelled_count"] == 2

    with get_db_context() as db:
        scheduled_count = db.query(Alarm).filter(Alarm.status == "scheduled").count()
        assert scheduled_count == 0


def test_modify_alarm_tool():
    tool = SetAlarmTool()
    res = tool.execute(time="tomorrow at 6 AM", label="Old Alarm")
    alarm_id = res.data["alarm"]["id"]

    mod_tool = ModifyAlarmTool()
    res_mod = mod_tool.execute(alarm_id=alarm_id, new_time="tomorrow at 7:30 AM", new_label="Updated Alarm")

    assert res_mod.success is True
    with get_db_context() as db:
        updated = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert updated.target_time.hour == 7
        assert updated.target_time.minute == 30
        assert updated.label == "Updated Alarm"


# ==========================================
# 3. Daemon Execution, Notification & Missed Alarms Tests
# ==========================================
@patch("app.productivity.alarm_daemon.notifications.show_desktop_notification")
@patch("app.productivity.alarm_daemon.get_tts_provider")
def test_alarm_daemon_triggers_due_alarm(mock_tts, mock_notif):
    daemon = AlarmDaemon(check_interval_seconds=0.1)

    # Insert alarm due 1 second ago
    past_due = datetime.now() - timedelta(seconds=1)
    with get_db_context() as db:
        alarm = Alarm(
            label="Standup meeting",
            target_time=past_due,
            status="scheduled",
            recurrence="none"
        )
        db.add(alarm)
        db.flush()
        alarm_id = alarm.id

    # Run one check cycle
    daemon._check_due_alarms()

    # Verify state updated to 'triggered'
    with get_db_context() as db:
        updated = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert updated.status == "triggered"
        assert updated.triggered_at is not None

    # Verify notification and TTS triggered
    mock_notif.assert_called_once()
    mock_tts.return_value.speak.assert_called_once()


@patch("app.productivity.alarm_daemon.notifications.show_desktop_notification")
@patch("app.productivity.alarm_daemon.get_tts_provider")
def test_alarm_daemon_daily_recurrence(mock_tts, mock_notif):
    daemon = AlarmDaemon()
    past_due = datetime.now() - timedelta(seconds=1)
    with get_db_context() as db:
        alarm = Alarm(
            label="Daily Wakeup",
            target_time=past_due,
            status="scheduled",
            recurrence="daily"
        )
        db.add(alarm)
        db.flush()
        orig_id = alarm.id

    daemon._check_due_alarms()

    # Original marked triggered, new recurring alarm scheduled for tomorrow
    with get_db_context() as db:
        orig = db.query(Alarm).filter(Alarm.id == orig_id).first()
        assert orig.status == "triggered"

        future = db.query(Alarm).filter(Alarm.status == "scheduled", Alarm.recurrence == "daily").first()
        assert future is not None
        assert future.target_time.date() == (past_due + timedelta(days=1)).date()


@patch("app.productivity.alarm_daemon.notifications.show_desktop_notification")
@patch("app.productivity.alarm_daemon.get_tts_provider")
def test_alarm_daemon_handles_missed_alarms(mock_tts, mock_notif):
    """Verify recovery when alarms matured while the machine was shut down/asleep."""
    daemon = AlarmDaemon()
    missed_time = datetime.now() - timedelta(minutes=45)
    with get_db_context() as db:
        alarm = Alarm(
            label="Offline Alarm",
            target_time=missed_time,
            status="scheduled",
            recurrence="none"
        )
        db.add(alarm)
        db.flush()
        alarm_id = alarm.id

    daemon._check_missed_alarms()

    with get_db_context() as db:
        updated = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert updated.status == "missed"

    # Notification sent for missed alarm
    mock_notif.assert_called_once()
    assert "Missed Alarm" in mock_notif.call_args[1]["title"]


# ==========================================
# 4. End-to-End Agent Conversation Routing Tests
# ==========================================
def test_agent_routes_user_spoken_alarm():
    agent = DadusAgent()
    sid = "alarm_test_session"

    # 1. User says "Set alarm for me for 240 o'clock"
    res1 = agent.process_input("Set alarm for me for 240 o'clock", session_id=sid)
    assert res1.status == "DONE"
    assert res1.tool_called == "set_alarm"
    assert "alarm" in res1.text.lower()

    # 2. User says "Set an alarm for tomorrow at 6 AM"
    res2 = agent.process_input("Set an alarm for tomorrow at 6 AM", session_id=sid)
    assert res2.status == "DONE"
    assert res2.tool_called == "set_alarm"
    assert "6:00 AM" in res2.text or "alarm" in res2.text.lower()

    # 3. User says "List alarms"
    res3 = agent.process_input("List my alarms", session_id=sid)
    assert res3.status == "DONE"
    assert res3.tool_called == "list_alarms"
    assert "scheduled alarm" in res3.text.lower()

    # 4. User says "Cancel my alarm"
    res4 = agent.process_input("Cancel my alarm", session_id=sid)
    assert res4.status == "DONE"
    assert res4.tool_called == "cancel_alarm"
    assert "cancelled" in res4.text.lower()

