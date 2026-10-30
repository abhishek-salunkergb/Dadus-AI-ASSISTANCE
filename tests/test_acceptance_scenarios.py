"""End-to-End Acceptance Tests verifying all 10 core scenarios from Section 30."""
import pytest
from app.agent.agent import DadusAgent
from app.memory.memory import memory_store

@pytest.fixture
def agent():
    return DadusAgent()

def test_acceptance_test_1_open_chrome(agent):
    """TEST 1: User says 'Hey Dadus, open Chrome.' -> Chrome opens."""
    resp = agent.process_input("Hey Dadus, open Chrome.", session_id="test_acc_1")
    assert resp.tool_called == "open_app"
    assert resp.tool_result is not None
    assert resp.tool_result["success"] is True
    assert "Google Chrome" in resp.text

def test_acceptance_test_2_open_vscode(agent):
    """TEST 2: User says 'Hey Dadus, open VS Code.' -> VS Code opens."""
    resp = agent.process_input("Hey Dadus, open VS Code.", session_id="test_acc_2")
    assert resp.tool_called == "open_app"
    assert resp.tool_result is not None
    assert resp.tool_result["success"] is True
    assert "Visual Studio Code" in resp.text

def test_acceptance_test_3_music_clarification(agent):
    """
    TEST 3: User says 'Hey Dadus, play Believer.'
    Expected: If multiple suitable music applications exist:
    'Boss, which app should I use: Spotify or YouTube?' / 'Boss, I found Spotify and YouTube. Which one should I use?'
    """
    memory_store.forget("preferred_music_app")
    resp = agent.process_input("Hey Dadus, play Believer.", session_id="test_acc_3")
    assert resp.needs_clarification is True
    assert resp.status == "WAITING_CLARIFICATION"
    assert "Spotify" in resp.text
    assert "YouTube" in resp.text

def test_acceptance_test_4_play_on_spotify(agent):
    """
    TEST 4: User says 'Hey Dadus, play Believer on Spotify.'
    Expected: Spotify is selected and the music search/play workflow executes.
    """
    resp = agent.process_input("Hey Dadus, play Believer on Spotify.", session_id="test_acc_4")
    assert resp.tool_called == "play_music"
    assert resp.needs_clarification is False
    assert "Spotify" in resp.text
    assert "Believer" in resp.text

def test_acceptance_test_5_set_volume(agent):
    """TEST 5: User says 'Hey Dadus, set volume to 30 percent.' -> System volume changes."""
    resp = agent.process_input("Hey Dadus, set volume to 30 percent.", session_id="test_acc_5")
    assert resp.tool_called == "set_volume"
    assert resp.tool_result["data"]["level"] == 30
    assert "30 percent" in resp.text

def test_acceptance_test_6_create_reminder(agent):
    """TEST 6: User says 'Hey Dadus, remind me at 7 PM to study Python.' -> Reminder is persisted."""
    resp = agent.process_input("Hey Dadus, remind me at 7 PM to study Python.", session_id="test_acc_6")
    assert resp.tool_called == "create_reminder"
    assert resp.tool_result["success"] is True
    assert "study Python" in resp.text

def test_acceptance_test_7_today_schedule(agent):
    """TEST 7: User says 'What is my schedule today?' -> Today's schedule returned."""
    # Pre-add an item
    agent.process_input("Add Gym at 5 PM", session_id="test_acc_7")
    resp = agent.process_input("What is my schedule today?", session_id="test_acc_7")
    assert resp.tool_called == "get_today_schedule"
    assert resp.tool_result["success"] is True
    assert "schedule" in resp.text.lower()

def test_acceptance_test_8_delete_confirmation(agent):
    """
    TEST 8: User says 'Hey Dadus, delete this folder.'
    Expected: Confirmation is required before deletion.
    """
    resp = agent.process_input("Hey Dadus, delete this folder.", session_id="test_acc_8")
    assert resp.needs_confirmation is True
    assert resp.status == "WAITING_CONFIRMATION"
    assert "Should I continue?" in resp.text or "permanently delete" in resp.text

    # Test affirming confirmation
    confirm_resp = agent.process_input("yes", session_id="test_acc_8")
    assert confirm_resp.tool_called == "delete_file_or_folder"

def test_acceptance_test_9_password_restricted(agent):
    """TEST 9: User says 'Hey Dadus, give me my saved password.' -> DADUS does not expose credentials."""
    resp = agent.process_input("Hey Dadus, give me my saved password.", session_id="test_acc_9")
    assert resp.tool_called is None
    assert "passwords" in resp.text.lower() or "credentials" in resp.text.lower()

def test_acceptance_test_10_memory_preference_workflow(agent):
    """
    TEST 10:
    User: 'Hey Dadus, remember that I prefer Spotify.'
    Expected: Preference is stored.
    Then: 'Play Believer.'
    Expected: Spotify is preferred when available without asking again.
    """
    # 1. Store preference
    mem_resp = agent.process_input("Hey Dadus, remember that I prefer Spotify.", session_id="test_acc_10")
    assert mem_resp.tool_called == "store_memory"
    assert "remember" in mem_resp.text.lower()
    assert "spotify" in mem_resp.text.lower()

    # 2. Subsequent play command should bypass clarification and use Spotify
    play_resp = agent.process_input("Play Believer.", session_id="test_acc_10")
    assert play_resp.tool_called == "play_music"
    assert play_resp.needs_clarification is False
    assert "Spotify" in play_resp.text
    assert "Believer" in play_resp.text

    # Cleanup memory
    memory_store.forget("preferred_music_app")
