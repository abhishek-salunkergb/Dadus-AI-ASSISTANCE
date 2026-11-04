"""Tests for Phase 5 Safe File & Log Cleanup with Two-Phase User Confirmation."""
import os
from pathlib import Path
import pytest

from app.agent.agent import DadusAgent
from app.tools.registry import tool_registry
from app.tools.logs import CleanLogsTool
from app.config.settings import settings

def test_clean_logs_requires_confirmation(tmp_path, monkeypatch):
    """Verify log cleanup requires two-phase user confirmation through the registry."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    temp_log = log_dir / "old_app.log.1"
    temp_log.write_text("temporary log content")

    active_log = log_dir / "dadus.log"
    active_log.write_text("active open log stream")

    monkeypatch.setattr(settings, "LOG_FILE", str(active_log))

    # Step 1: Without confirmation
    res1 = tool_registry.execute_tool(name="clean_logs", arguments={}, bypass_confirmation=False)
    assert res1.confirmation_required is True
    assert temp_log.exists()
    assert active_log.exists()

    # Step 2: With confirmation approved
    res2 = tool_registry.execute_tool(name="clean_logs", arguments={}, bypass_confirmation=True)
    assert res2.success is True
    assert res2.data["verified"] is True
    assert res2.data["deleted_count"] >= 1
    # Temporary log should now be deleted, while active log remains
    assert not temp_log.exists()
    assert active_log.exists()

def test_agent_log_cleanup_two_turn_journey(tmp_path, monkeypatch):
    """Verify full natural-language journey: 'Delete the logs' -> confirm 'Yes'."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_log = log_dir / "backup.log.bak"
    old_log.write_text("old log data")
    active_log = log_dir / "dadus.log"
    active_log.write_text("active log")

    monkeypatch.setattr(settings, "LOG_FILE", str(active_log))

    agent = DadusAgent()
    sid = "log_clean_session"

    # Turn 1: Request log cleanup
    resp1 = agent.process_input("Delete the logs.", session_id=sid)
    assert resp1.status == "WAITING_CONFIRMATION"
    assert resp1.needs_confirmation is True
    assert old_log.exists()

    # Turn 2: User confirms "yes"
    resp2 = agent.process_input("yes", session_id=sid)
    assert resp2.status == "DONE"
    assert resp2.tool_called == "clean_logs"
    assert "freed" in resp2.text.lower() or "cleanup complete" in resp2.text.lower()
    assert not old_log.exists()
