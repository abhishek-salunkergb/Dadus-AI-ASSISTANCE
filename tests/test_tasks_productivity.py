"""Tests for personal productivity, tasks, recurring reminders, and briefing."""
from datetime import datetime, timedelta
import pytest
from app.tools.tasks import CreateTaskTool, ListTasksTool, CompleteTaskTool, GetDailyBriefingTool
from app.tools.reminders import CreateReminderTool
from app.productivity.reminder_daemon import ReminderDaemon
from app.database.database import get_db_context
from app.database.models import TaskItem, Reminder

def test_create_and_list_tasks():
    create_tool = CreateTaskTool()
    res = create_tool.execute(title="Complete DADUS Architecture Review", priority="high")
    assert res.success is True
    assert "Task created" in res.message
    assert res.data["priority"] == "high"

    list_tool = ListTasksTool()
    res_list = list_tool.execute(status="pending")
    assert res_list.success is True
    assert any("Complete DADUS Architecture Review" in t["title"] for t in res_list.data["tasks"])

def test_complete_task():
    create_tool = CreateTaskTool()
    res = create_tool.execute(title="Refactor Media Controller", priority="medium")
    task_id = res.data["id"]

    comp_tool = CompleteTaskTool()
    res_comp = comp_tool.execute(task_id_or_title=str(task_id))
    assert res_comp.success is True
    assert "Marked task" in res_comp.message

    # Verify not in pending
    list_tool = ListTasksTool()
    res_list = list_tool.execute(status="pending")
    assert not any(t["id"] == task_id for t in res_list.data["tasks"])

def test_daily_briefing():
    tool = GetDailyBriefingTool()
    res = tool.execute()
    assert res.success is True
    assert "boss" in res.message.lower()
    assert "task_count" in res.data
    assert "schedule_count" in res.data

def test_recurring_reminder_creation():
    tool = CreateReminderTool()
    res = tool.execute(title="Study AI Research", time="every day at 8 AM")
    assert res.success is True
    assert res.data["recurrence"] == "daily"
    assert "every day" in res.message or "daily" in res.message

def test_reminder_daemon_missed_and_due():
    # Insert a due recurring reminder directly into DB
    now = datetime.now()
    past_time = now - timedelta(minutes=10)
    with get_db_context() as db:
        r = Reminder(
            title="Daemon Test Missed Reminder",
            target_time=past_time,
            status="pending",
            recurrence="daily"
        )
        db.add(r)
        db.flush()
        rem_id = r.id

    daemon = ReminderDaemon(check_interval_seconds=1)
    daemon._check_missed_reminders()

    with get_db_context() as db:
        updated = db.query(Reminder).filter(Reminder.id == rem_id).first()
        # Should have advanced to next day
        assert updated.target_time > now
        assert updated.last_notified_at is not None
        # Clean up
        db.delete(updated)
