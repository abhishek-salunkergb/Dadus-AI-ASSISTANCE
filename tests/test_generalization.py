"""Comprehensive generalization tests for DADUS.
Verifies multi-turn contextual reasoning, anaphora resolution, universal clarification disambiguation,
and dynamic conversational intelligence without hardcoded test-gaming.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.agent.agent import DadusAgent
from app.memory.memory import memory_store
from app.database.database import init_db, get_db_context
from app.database.models import Contact

@pytest.fixture(autouse=True)
def setup_contacts_and_db():
    init_db()
    with get_db_context() as db:
        for name, phone in [
            ("Abhishek Salunke", "+91 98765 43210"),
            ("Abhishek Chavhan", "+91 98765 43211"),
            ("Abhishek Patil", "+91 98765 43212"),
        ]:
            if not db.query(Contact).filter(Contact.name == name).first():
                db.add(Contact(name=name, phone=phone))
        db.commit()

@patch("subprocess.Popen")
@patch("os.startfile")
def test_pronoun_resolution_close_it(mock_sf, mock_popen):
    """Verifies that 'close it' or 'close that' resolves the pronoun to the previously opened app."""
    agent = DadusAgent()
    sid = "anaphora_session_1"

    # Turn 1: Open Chrome
    res1 = agent.process_input("open Chrome", session_id=sid)
    assert res1.status == "DONE"
    assert res1.tool_called == "open_app"

    # Turn 2: Natural pronoun reference "close it"
    with patch("app.tools.apps.subprocess.run") as mock_subrun:
        mock_subrun.return_value = MagicMock(returncode=0)
        res2 = agent.process_input("close it", session_id=sid)
        assert res2.status == "DONE"
        assert res2.tool_called == "close_app"
        assert "chrome" in res2.text.lower()

@patch("subprocess.Popen")
@patch("os.startfile")
def test_pronoun_resolution_close_that_different_app(mock_sf, mock_popen):
    """Verifies that 'close that' dynamically tracks different apps across turns."""
    agent = DadusAgent()
    sid = "anaphora_session_2"

    # Turn 1: Open Notepad
    res1 = agent.process_input("open Notepad", session_id=sid)
    assert res1.status == "DONE"
    assert res1.tool_called == "open_app"

    # Turn 2: Natural pronoun reference "close that"
    with patch("app.tools.apps.subprocess.run") as mock_subrun:
        mock_subrun.return_value = MagicMock(returncode=0)
        res2 = agent.process_input("close that", session_id=sid)
        assert res2.status == "DONE"
        assert res2.tool_called == "close_app"
        assert "notepad" in res2.text.lower()

def test_relative_volume_pronouns():
    """Verifies relative volume control phrased with natural pronouns."""
    agent = DadusAgent()
    sid = "volume_pronoun_session"

    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers") as mock_spk:
        mock_endpoint = MagicMock()
        mock_endpoint.GetMasterVolumeLevelScalar.return_value = 0.40
        mock_spk.return_value.EndpointVolume = mock_endpoint

        # "make it louder"
        res_up = agent.process_input("make it louder", session_id=sid)
        assert res_up.status == "DONE"
        assert res_up.tool_called == "adjust_volume"

        # "turn it down a bit"
        res_down = agent.process_input("turn it down a bit", session_id=sid)
        assert res_down.status == "DONE"
        assert res_down.tool_called == "adjust_volume"

def test_action_repetition():
    """Verifies 'do the same thing again' repeats the previous action dynamically."""
    agent = DadusAgent()
    sid = "repeat_session"

    # Turn 1: Get system status
    res1 = agent.process_input("system status", session_id=sid)
    assert res1.status == "DONE"
    assert res1.tool_called == "get_system_status"

    # Turn 2: "do the same thing again"
    res2 = agent.process_input("do the same thing again", session_id=sid)
    assert res2.status == "DONE"
    assert res2.tool_called == "get_system_status"

def test_action_repetition_empty_session():
    """Verifies 'do it again' handles empty history gracefully."""
    agent = DadusAgent()
    sid = "empty_repeat_session"
    res = agent.process_input("repeat that", session_id=sid)
    assert "no previous action" in res.text.lower()

@patch("webbrowser.open")
@patch("os.startfile")
def test_universal_clarification_relative_choice(mock_sf, mock_wb):
    """Verifies resolving 'the other one' when presented with two clarification options."""
    agent = DadusAgent()
    sid = "relative_clarification_session"
    memory_store.forget("preferred_music_app")

    # Turn 1: Triggers clarification between Spotify and YouTube
    res1 = agent.process_input("play Believer", session_id=sid)
    assert res1.status == "WAITING_CLARIFICATION"
    assert "Spotify" in res1.options
    assert "YouTube" in res1.options

    # Turn 2: User says "the other one" (should select the second option, YouTube)
    res2 = agent.process_input("the other one", session_id=sid)
    assert res2.status == "DONE"
    assert res2.tool_called == "play_music"
    assert "YouTube" in res2.text

@patch("os.startfile")
def test_universal_clarification_ordinal_selection(mock_sf):
    """Verifies resolving ordinal reference ('the second one') during contact disambiguation."""
    agent = DadusAgent()
    sid = "ordinal_clarification_session"

    # Turn 1: Disambiguate among multiple Abhishek contacts
    res1 = agent.process_input("call abhishek", session_id=sid)
    assert res1.status == "WAITING_CLARIFICATION"

    # Turn 2: Select "the second one" (Abhishek Chavhan)
    res2 = agent.process_input("the second one", session_id=sid)
    assert res2.status == "DONE"
    assert res2.tool_called == "call_contact"
    assert "Abhishek Chavhan" in res2.text

def test_clarification_cancellation():
    """Verifies clean cancellation of pending clarification when user aborts."""
    agent = DadusAgent()
    sid = "cancel_clarification_session"

    res1 = agent.process_input("call abhishek", session_id=sid)
    assert res1.status == "WAITING_CLARIFICATION"

    res2 = agent.process_input("nevermind, cancel", session_id=sid)
    assert res2.status == "READY"
    assert "cancelled" in res2.text.lower()
    session = agent.get_or_create_session(sid)
    assert session.pending_clarification is None

def test_dynamic_conversational_synthesis():
    """Verifies dynamic responses that adapt to stored user profile and active tasks."""
    agent = DadusAgent()
    memory_store.remember("learning", "Rust")
    memory_store.remember("preferred_music_app", "Spotify")

    res = agent.process_input("Suggest something to do, feeling bored.")
    assert res.status == "DONE"
    assert "Rust" in res.text
    assert "Spotify" in res.text

    # Clean up
    memory_store.forget("learning")
    memory_store.forget("preferred_music_app")

