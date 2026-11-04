"""Integration tests for core voice & desktop assistant workflows."""
import pytest
from app.agent.agent import DadusAgent
from app.memory.memory import memory_store

@pytest.fixture
def agent():
    return DadusAgent()

def test_open_app_launches_chrome(agent):
    """Verify application launcher intent recognizes and launches Google Chrome."""
    resp = agent.process_input("Hey Dadus, open Chrome.", session_id="test_open_chrome")
    assert resp.tool_called == "open_app"
    assert resp.tool_result is not None
    assert resp.tool_result["success"] is True
    assert "Google Chrome" in resp.text

def test_open_app_launches_vscode(agent):
    """Verify application launcher intent recognizes and launches Visual Studio Code."""
    resp = agent.process_input("Hey Dadus, open VS Code.", session_id="test_open_vscode")
    assert resp.tool_called == "open_app"
    assert resp.tool_result is not None
    assert resp.tool_result["success"] is True
    assert "Visual Studio Code" in resp.text

def test_music_disambiguation_when_multiple_apps_available(agent):
    """Verify agent requests clarification when user requests music without a target app or saved preference."""
    memory_store.forget("preferred_music_app")
    resp = agent.process_input("Hey Dadus, play Believer.", session_id="test_disambiguate_music")
    assert resp.needs_clarification is True
    assert resp.status == "WAITING_CLARIFICATION"
    assert "Spotify" in resp.text
    assert "YouTube" in resp.text

def test_play_music_explicit_platform_routing(agent):
    """Verify direct music playback intent when platform is explicitly specified."""
    resp = agent.process_input("Hey Dadus, play Believer on Spotify.", session_id="test_explicit_spotify")
    assert resp.tool_called == "play_music"
    assert resp.needs_clarification is False
    assert "Spotify" in resp.text
    assert "Believer" in resp.text

def test_system_volume_adjustment(agent):
    """Verify natural language system volume level controls."""
    resp = agent.process_input("Hey Dadus, set volume to 30 percent.", session_id="test_volume_control")
    assert resp.tool_called == "set_volume"
    assert resp.tool_result["data"]["level"] == 30
    assert "30 percent" in resp.text

def test_create_natural_language_reminder(agent):
    """Verify time-based reminder parsing and database persistence."""
    resp = agent.process_input("Hey Dadus, remind me at 7 PM to study Python.", session_id="test_reminder")
    assert resp.tool_called == "create_reminder"
    assert resp.tool_result["success"] is True
    assert "study Python" in resp.text

def test_retrieve_daily_schedule(agent):
    """Verify schedule retrieval intent and formatting."""
    agent.process_input("Add Gym at 5 PM", session_id="test_schedule")
    resp = agent.process_input("What is my schedule today?", session_id="test_schedule")
    assert resp.tool_called == "get_today_schedule"
    assert resp.tool_result["success"] is True
    assert "schedule" in resp.text.lower()

def test_destructive_action_requires_explicit_confirmation(agent):
    """Verify destructive actions require two-phase user confirmation before execution."""
    resp = agent.process_input("Hey Dadus, delete this folder.", session_id="test_confirm_delete")
    assert resp.needs_confirmation is True
    assert resp.status == "WAITING_CONFIRMATION"
    assert "Should I continue?" in resp.text or "permanently delete" in resp.text

    # Affirming confirmation executes the pending action
    confirm_resp = agent.process_input("yes", session_id="test_confirm_delete")
    assert confirm_resp.tool_called == "delete_file_or_folder"

def test_restricted_credential_query_rejection(agent):
    """Verify security policy unconditionally denies requests for credentials or secrets."""
    resp = agent.process_input("Hey Dadus, give me my saved password.", session_id="test_credentials_blocked")
    assert resp.tool_called is None
    assert "passwords" in resp.text.lower() or "credentials" in resp.text.lower()

def test_preference_learning_bypasses_clarification(agent):
    """Verify stored user preferences bypass disambiguation questions on subsequent runs."""
    # 1. Store preference
    mem_resp = agent.process_input("Hey Dadus, remember that I prefer Spotify.", session_id="test_pref_bypass")
    assert mem_resp.tool_called == "store_memory"
    assert "remember" in mem_resp.text.lower()
    assert "spotify" in mem_resp.text.lower()

    # 2. Subsequent play command should bypass clarification and use Spotify
    play_resp = agent.process_input("Play Believer.", session_id="test_pref_bypass")
    assert play_resp.tool_called == "play_music"
    assert play_resp.needs_clarification is False
    assert "Spotify" in play_resp.text
    assert "Believer" in play_resp.text

    # Cleanup memory
    memory_store.forget("preferred_music_app")

def test_voice_stop_command_interruption(agent):
    """Verify stop/quiet commands halt assistant output and reset state."""
    resp = agent.process_input("Hey Dadus, stop", session_id="test_stop_command")
    assert "stopped" in resp.text.lower()
    assert resp.status in ["DONE", "READY"]

def test_natural_language_delete_task(agent):
    """Verify deleting a task via natural language routing."""
    agent.process_input("Create a task to audit database backups.", session_id="test_del_task")
    del_resp = agent.process_input("Delete task audit database backups.", session_id="test_del_task")
    assert del_resp.tool_called == "delete_task"
    assert "deleted" in del_resp.text.lower()
