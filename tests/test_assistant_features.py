"""Integration tests for assistant memory, system diagnostics, and developer workflows."""
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from app.agent.agent import dadus_agent
from app.memory.memory import memory_store

def test_memory_preference_persistence_and_query():
    """Verify storing user preferences in memory and retrieving them conversationally."""
    # 1. Store preference
    res1 = dadus_agent.process_input("Remember that I prefer Spotify.", session_id="test_memory_session")
    assert res1.status == "DONE"
    assert "Spotify" in res1.text
    assert memory_store.get_preferred_music_app() == "Spotify"

    # 2. Query preference
    res2 = dadus_agent.process_input("What music app do I prefer?", session_id="test_memory_session")
    assert res2.status == "DONE"
    assert "Spotify" in res2.text

def test_recurring_reminder_scheduling():
    """Verify recurring daily reminder phrasing parsing and storage."""
    res = dadus_agent.process_input("Remind me every day at 8 AM to study Python.", session_id="test_reminder_session")
    assert res.status == "DONE"
    assert "study Python" in res.text
    assert ("every day" in res.text or "daily" in res.text)

def test_task_creation_and_listing():
    """Verify creating a pending task and listing active tasks."""
    dadus_agent.process_input("Create a task to complete my Django project.", session_id="test_task_session")
    res = dadus_agent.process_input("What are my tasks today?", session_id="test_task_session")
    assert res.status == "DONE"
    assert "tasks" in res.text.lower()
    assert "complete my Django project" in res.text

def test_project_discovery_and_launch():
    """Verify locating a software project directory on disk and launching in code editor."""
    with patch("app.tools.projects.locate_project_folder") as mock_loc, \
         patch("subprocess.Popen") as mock_popen, \
         patch("os.startfile") as mock_sf:
        mock_loc.return_value = Path(r"C:\Projects\Django")
        res = dadus_agent.process_input("Find my Django project and open it in VS Code.", session_id="test_project_session")
        assert res.status == "DONE"
        assert "VS Code" in res.text or "Visual Studio Code" in res.text

def test_desktop_screenshot_capture():
    """Verify desktop screen capture tool invocation."""
    with patch("PIL.ImageGrab.grab") as mock_grab:
        mock_img = MagicMock()
        mock_grab.return_value = mock_img
        res = dadus_agent.process_input("Take a screenshot.", session_id="test_screenshot_session")
        assert res.status == "DONE"
        assert "screenshot" in res.text.lower()

def test_play_music_with_saved_preference():
    """Verify music playback resolves to saved preference when no app is specified."""
    memory_store.remember("preferred_music_app", "Spotify")
    with patch("webbrowser.open") as mock_wb, patch("os.startfile") as mock_sf:
        res = dadus_agent.process_input("Play relaxing music.", session_id="test_music_pref_session")
        assert res.status == "DONE"
        assert "relaxing music" in res.text.lower()
        assert "spotify" in res.text.lower()

def test_conversation_history_recall():
    """Verify session-based multi-turn conversation context recall."""
    session_id = "discussion_session"
    dadus_agent.process_input("How much RAM is currently being used?", session_id=session_id)
    dadus_agent.process_input("Play relaxing music.", session_id=session_id)

    res = dadus_agent.process_input("What were we discussing earlier?", session_id=session_id)
    assert res.status == "DONE"
    assert "earlier we were discussing" in res.text.lower()

def test_project_github_repository_lookup():
    """Verify locating local repository origin URL and opening GitHub."""
    with patch("webbrowser.open") as mock_wb:
        res = dadus_agent.process_input("Find my Python project and open its GitHub repository.", session_id="test_github_session")
        assert res.status == "DONE"
        assert "github" in res.text.lower()

def test_multi_step_plan_generation():
    """Verify multi-step planner provides structured procedural breakdown."""
    res = dadus_agent.process_input("Explain what you are doing before executing this multi-step task.", session_id="test_plan_session")
    assert res.status == "DONE"
    assert "procedure" in res.text.lower() or "plan" in res.text.lower()
    assert "step" in res.text.lower()

def test_conversational_brain_bored_and_interview():
    """Verify conversational responses for open-ended queries and coaching requests."""
    res_bored = dadus_agent.process_input("Hey Dadus, I'm bored. Suggest something.")
    assert "boss" in res_bored.text.lower()
    assert "relaxing music" in res_bored.text.lower() or "python" in res_bored.text.lower()

    res_interview = dadus_agent.process_input("I have an interview tomorrow. Help me prepare.")
    assert "interview" in res_interview.text.lower()
    assert "questions" in res_interview.text.lower() or "mock" in res_interview.text.lower()

def test_conversational_brain_open_coding_app():
    """Verify resolving natural reference to default developer editor."""
    with patch("subprocess.Popen") as mock_popen, patch("os.startfile") as mock_sf:
        res = dadus_agent.process_input("Open the application I use for coding.")
        assert res.status == "DONE"
        assert "Visual Studio Code" in res.text

def test_conversational_brain_volume_slightly_lower():
    """Verify relative volume decrease intent mapping."""
    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers") as mock_speakers:
        mock_endpoint = MagicMock()
        mock_endpoint.GetMasterVolumeLevelScalar.return_value = 0.50
        mock_speakers.return_value.EndpointVolume = mock_endpoint
        res = dadus_agent.process_input("Make the volume slightly lower.")
        assert res.status == "DONE"
        assert "lowered" in res.text.lower()

def test_conversational_brain_ram_usage():
    """Verify hardware diagnostic telemetry query."""
    res = dadus_agent.process_input("How much RAM is currently being used?")
    assert res.status == "DONE"
    assert "RAM is currently being used" in res.text

def test_conversational_brain_find_latest_pdf():
    """Verify local file search with extension filter."""
    res = dadus_agent.process_input("Find my latest PDF.")
    assert res.status == "DONE"
    assert "file" in res.text.lower() or "matching" in res.text.lower()

def test_learning_technology_memory_flow():
    """Verify learning topics roundtrip in long-term memory."""
    res1 = dadus_agent.process_input("Remember that I am learning Python.")
    assert res1.status == "DONE"

    res2 = dadus_agent.process_input("What technologies am I learning?")
    assert res2.status == "DONE"
    assert "Python" in res2.text

def test_preferred_browser_memory_flow():
    """Verify browser preference roundtrip in long-term memory."""
    res1 = dadus_agent.process_input("My preferred browser is Chrome.")
    assert res1.status == "DONE"

    res2 = dadus_agent.process_input("What is my preferred browser?")
    assert res2.status == "DONE"
    assert "Google Chrome" in res2.text
