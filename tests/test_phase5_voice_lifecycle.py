"""Tests for Phase 5 Always-On Voice Service & State Machine Lifecycle."""
import time
import pytest
from unittest.mock import patch, MagicMock

from app.voice.service import VoiceAgentService, VoiceState
from app.agent.agent import DadusAgent

def test_voice_service_initial_state():
    """Verify voice service initializes in idle wake monitoring state."""
    service = VoiceAgentService()
    assert service.current_state == VoiceState.IDLE_WAKE_MONITORING
    health = service.get_health()
    assert health["state"] == VoiceState.IDLE_WAKE_MONITORING.value
    assert "status" in health

def test_voice_service_state_listener_notifications():
    """Verify state transitions trigger registered callbacks."""
    service = VoiceAgentService()
    observed_states = []

    def on_state(state, msg):
        observed_states.append((state, msg))

    service.add_state_listener(on_state)
    service._set_state(VoiceState.WAKE_DETECTED, "Detected")
    service._set_state(VoiceState.GREETING, "I'm listening, Boss. Tell me.")

    assert len(observed_states) == 2
    assert observed_states[0][0] == VoiceState.WAKE_DETECTED
    assert observed_states[1][0] == VoiceState.GREETING
    assert "I'm listening, Boss. Tell me." in observed_states[1][1]

@patch("app.voice.service.get_tts_provider")
@patch("app.voice.service.get_stt_provider")
def test_voice_active_turn_execution_flow(mock_get_stt, mock_get_tts):
    """Verify execution of full conversational turn through the state machine."""
    mock_tts = MagicMock()
    mock_get_tts.return_value = mock_tts

    mock_stt = MagicMock()
    mock_get_stt.return_value = mock_stt
    # Turn 1: user says "how much RAM is used", Turn 2: silence (ends conversation)
    mock_stt.listen_and_transcribe.side_effect = [
        "How much RAM is currently being used?",
        None
    ]

    service = VoiceAgentService()
    service._running = True
    states = []
    service.add_state_listener(lambda s, m: states.append(s))

    # Trigger turn without inline command
    service._handle_active_turn(inline_command=None, is_new_wake=True)

    # Verify key state sequence was traversed
    assert VoiceState.WAKE_DETECTED in states
    assert VoiceState.GREETING in states
    assert VoiceState.ACTIVE_LISTENING in states
    assert VoiceState.SPEECH_RECOGNITION in states
    assert VoiceState.TASK_EXECUTION in states
    assert VoiceState.RESULT_VERIFICATION in states
    assert VoiceState.SPOKEN_RESPONSE in states
    assert VoiceState.IDLE_WAKE_MONITORING in states

    # Verify initial greeting was spoken
    mock_tts.speak.assert_any_call("I'm listening, Boss. Tell me.", async_mode=False)

@patch("app.voice.service.get_tts_provider")
@patch("app.voice.service.get_stt_provider")
def test_voice_cancellation_barge_in(mock_get_stt, mock_get_tts):
    """Verify saying cancel halts execution and returns to idle."""
    mock_tts = MagicMock()
    mock_get_tts.return_value = mock_tts

    service = VoiceAgentService()
    service._running = True

    states = []
    service.add_state_listener(lambda s, m: states.append(s))

    # User immediately cancels
    service._handle_active_turn(inline_command="cancel", is_new_wake=True)

    assert VoiceState.WAKE_DETECTED in states
    assert VoiceState.SPOKEN_RESPONSE in states
    assert VoiceState.IDLE_WAKE_MONITORING in states
    mock_tts.stop.assert_called()
    mock_tts.speak.assert_any_call("Cancelled, Boss.", async_mode=False)

@patch("app.voice.service.get_tts_provider")
@patch("app.voice.service.get_stt_provider")
def test_voice_unintelligible_speech_retry(mock_get_stt, mock_get_tts):
    """Verify empty/unintelligible speech prompts retry."""
    mock_tts = MagicMock()
    mock_get_tts.return_value = mock_tts

    mock_stt = MagicMock()
    mock_get_stt.return_value = mock_stt
    mock_stt.listen_and_transcribe.side_effect = [
        "?",    # unintelligible short sound
        None   # then silence
    ]

    service = VoiceAgentService()
    service._running = True

    service._handle_active_turn(inline_command="", is_new_wake=True)
    mock_tts.speak.assert_any_call("Sorry, Boss. Could you say that again?", async_mode=False)
