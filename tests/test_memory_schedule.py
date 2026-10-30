"""Tests for persistent SQLite memory, reminders, and daily schedule."""
import pytest
from datetime import datetime, date
from app.memory.memory import memory_store
from app.memory.retrieval import MemoryRetriever
from app.tools.reminders import CreateReminderTool, ListRemindersTool
from app.tools.schedule import CreateScheduleItemTool, GetTodayScheduleTool

def test_memory_storage_and_retrieval():
    """Verify storing and retrieving preferences."""
    memory_store.remember("preferred_editor", "VS Code", "preference")
    val = memory_store.get("preferred_editor")
    assert val == "VS Code"

    # Context summary reflects memory
    summary = MemoryRetriever.get_context_summary()
    assert "preferred_editor" in summary
    assert "VS Code" in summary

    # Forget memory
    assert memory_store.forget("preferred_editor") is True
    assert memory_store.get("preferred_editor") is None

def test_reminders_crud():
    """Verify creating and listing reminders."""
    create_tool = CreateReminderTool()
    res = create_tool.execute(title="study Python", time="7 PM")
    assert res.success is True
    assert "study Python" in res.message
    assert "target_time" in res.data

    list_tool = ListRemindersTool()
    lres = list_tool.execute(status="pending")
    assert lres.success is True
    assert "study Python" in lres.message
    assert len(lres.data["reminders"]) >= 1

def test_schedule_crud():
    """Verify adding events and reading today's schedule."""
    sched_tool = CreateScheduleItemTool()
    res = sched_tool.execute(title="Team Sync", start_time="today 11:59 PM", end_time="today 11:59 PM")
    assert res.success is True
    assert "Team Sync" in res.message

    get_tool = GetTodayScheduleTool()
    gres = get_tool.execute(target_date="today")
    assert gres.success is True
    assert "Team Sync" in gres.message
    assert len(gres.data["items"]) >= 1
