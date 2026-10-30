"""Comprehensive acceptance test suite verifying all 10 Phase 3 acceptance scenarios
and conversational capabilities for DADUS agent.
"""
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from app.agent.agent import dadus_agent
from app.memory.memory import memory_store

def test_scenario_1_and_2_memory_preference_and_recall():
    """
    Scenario 1: 'Remember that I prefer Spotify.'
    Scenario 2: 'What music app do I prefer?'
    """
    # 1. Store preference
    res1 = dadus_agent.process_input("Remember that I prefer Spotify.", session_id="test_scenarios")
    assert res1.status == "DONE"
    assert "Spotify" in res1.text
    assert memory_store.get_preferred_music_app() == "Spotify"

    # 2. Query preference
    res2 = dadus_agent.process_input("What music app do I prefer?", session_id="test_scenarios")
    assert res2.status == "DONE"
    assert "Spotify" in res2.text

def test_scenario_3_recurring_reminder():
    """Scenario 3: 'Remind me every day at 8 AM to study Python.'"""
    res = dadus_agent.process_input("Remind me every day at 8 AM to study Python.", session_id="test_scenarios")
    assert res.status == "DONE"
    assert "study Python" in res.text
    assert ("every day" in res.text or "daily" in res.text)

def test_scenario_4_tasks_query():
    """Scenario 4: 'What are my tasks today?'"""
    # First create a task
    dadus_agent.process_input("Create a task to complete my Django project.", session_id="test_scenarios")
    
    # Query tasks
    res = dadus_agent.process_input("What are my tasks today?", session_id="test_scenarios")
    assert res.status == "DONE"
    assert "tasks" in res.text.lower()
    assert "complete my Django project" in res.text

def test_scenario_5_find_project_open_vscode():
    """Scenario 5: 'Find my Django project and open it in VS Code.'"""
    with patch("app.tools.projects.locate_project_folder") as mock_loc, \
         patch("subprocess.Popen") as mock_popen, \
         patch("os.startfile") as mock_sf:
        mock_loc.return_value = Path(r"C:\Projects\Django")
        res = dadus_agent.process_input("Find my Django project and open it in VS Code.", session_id="test_scenarios")
        assert res.status == "DONE"
        assert "VS Code" in res.text or "Visual Studio Code" in res.text

def test_scenario_6_take_screenshot():
    """Scenario 6: 'Take a screenshot.'"""
    with patch("PIL.ImageGrab.grab") as mock_grab:
        mock_img = MagicMock()
        mock_grab.return_value = mock_img
        res = dadus_agent.process_input("Take a screenshot.", session_id="test_scenarios")
        assert res.status == "DONE"
        assert "screenshot" in res.text.lower()

def test_scenario_7_play_relaxing_music():
    """Scenario 7: 'Play relaxing music.'"""
    memory_store.remember("preferred_music_app", "Spotify")
    with patch("webbrowser.open") as mock_wb, patch("os.startfile") as mock_sf:
        res = dadus_agent.process_input("Play relaxing music.", session_id="test_scenarios")
        assert res.status == "DONE"
        assert "relaxing music" in res.text.lower()
        assert "spotify" in res.text.lower()

def test_scenario_8_conversational_recall_earlier():
    """Scenario 8: 'What were we discussing earlier?'"""
    session_id = "discussion_session"
    # User asks something first
    dadus_agent.process_input("How much RAM is currently being used?", session_id=session_id)
    dadus_agent.process_input("Play relaxing music.", session_id=session_id)

    # Now ask about earlier conversation
    res = dadus_agent.process_input("What were we discussing earlier?", session_id=session_id)
    assert res.status == "DONE"
    assert "earlier we were discussing" in res.text.lower()

def test_scenario_9_find_project_and_open_github():
    """Scenario 9: 'Find my Python project and open its GitHub repository.'"""
    with patch("webbrowser.open") as mock_wb:
        res = dadus_agent.process_input("Find my Python project and open its GitHub repository.", session_id="test_scenarios")
        assert res.status == "DONE"
        assert "github" in res.text.lower()

def test_scenario_10_explain_plan_before_executing():
    """Scenario 10: 'Explain what you are doing before executing this multi-step task.'"""
    res = dadus_agent.process_input("Explain what you are doing before executing this multi-step task.", session_id="test_scenarios")
    assert res.status == "DONE"
    assert "procedure" in res.text.lower() or "plan" in res.text.lower()
    assert "step" in res.text.lower()

def test_conversational_brain_bored_and_interview():
    """Conversational queries: 'I'm bored' and 'Interview prep'"""
    res_bored = dadus_agent.process_input("Hey Dadus, I'm bored. Suggest something.")
    assert "boss" in res_bored.text.lower()
    assert "relaxing music" in res_bored.text.lower() or "python" in res_bored.text.lower()

    res_interview = dadus_agent.process_input("I have an interview tomorrow. Help me prepare.")
    assert "interview" in res_interview.text.lower()
    assert "questions" in res_interview.text.lower() or "mock" in res_interview.text.lower()

def test_conversational_brain_open_coding_app():
    """'Open the application I use for coding.'"""
    with patch("subprocess.Popen") as mock_popen, patch("os.startfile") as mock_sf:
        res = dadus_agent.process_input("Open the application I use for coding.")
        assert res.status == "DONE"
        assert "Visual Studio Code" in res.text

def test_conversational_brain_volume_slightly_lower():
    """'Make the volume slightly lower.'"""
    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers") as mock_speakers:
        mock_endpoint = MagicMock()
        mock_endpoint.GetMasterVolumeLevelScalar.return_value = 0.50
        mock_speakers.return_value.EndpointVolume = mock_endpoint
        res = dadus_agent.process_input("Make the volume slightly lower.")
        assert res.status == "DONE"
        assert "lowered" in res.text.lower()

def test_conversational_brain_ram_usage():
    """'How much RAM is currently being used?'"""
    res = dadus_agent.process_input("How much RAM is currently being used?")
    assert res.status == "DONE"
    assert "RAM is currently being used" in res.text

def test_conversational_brain_find_latest_pdf():
    """'Find my latest PDF.'"""
    res = dadus_agent.process_input("Find my latest PDF.")
    assert res.status == "DONE"
    assert "file" in res.text.lower() or "matching" in res.text.lower()

def test_learning_technology_memory_flow():
    """'Remember that I am learning Python.' -> 'What technologies am I learning?'"""
    res1 = dadus_agent.process_input("Remember that I am learning Python.")
    assert res1.status == "DONE"

    res2 = dadus_agent.process_input("What technologies am I learning?")
    assert res2.status == "DONE"
    assert "Python" in res2.text

def test_preferred_browser_memory_flow():
    """'My preferred browser is Chrome.' -> 'What is my preferred browser?'"""
    res1 = dadus_agent.process_input("My preferred browser is Chrome.")
    assert res1.status == "DONE"

    res2 = dadus_agent.process_input("What is my preferred browser?")
    assert res2.status == "DONE"
    assert "Google Chrome" in res2.text
