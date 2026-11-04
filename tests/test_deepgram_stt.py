"""Tests for Deepgram Nova-2 Speech-to-Text integration."""
import pytest
from unittest.mock import patch, MagicMock
from app.voice.stt import DeepgramSTT, get_stt_provider


def test_deepgram_provider_factory():
    """Verify that get_stt_provider('deepgram') instantiates DeepgramSTT."""
    stt = get_stt_provider("deepgram")
    assert isinstance(stt, DeepgramSTT)
    assert stt.model == "nova-2"


def test_deepgram_transcribe_bytes_success():
    """Test successful audio transcription using Deepgram Nova-2."""
    stt = DeepgramSTT(api_key="test_deepgram_valid_key_12345", model="nova-2")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Open Chrome and search for Python developer jobs",
                            "confidence": 0.99
                        }
                    ]
                }
            ]
        }
    }

    dummy_audio_bytes = b"RIFF....WAVEfmt...."

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = stt.transcribe_bytes(dummy_audio_bytes)

        assert result == "Open Chrome and search for Python developer jobs"
        assert mock_post.called

        # Verify API URL, headers, and params
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.deepgram.com/v1/listen"
        assert call_args[1]["headers"]["Authorization"] == "Token test_deepgram_valid_key_12345"
        assert call_args[1]["headers"]["Content-Type"] == "audio/wav"
        assert call_args[1]["params"]["model"] == "nova-2"
        assert "Dadus:3" in call_args[1]["params"]["keywords"]


def test_deepgram_fallback_when_api_key_missing(tmp_path):
    """When DEEPGRAM_API_KEY is not configured, transcribe_file should fallback gracefully without crashing."""
    stt = DeepgramSTT(api_key=None)

    dummy_file = tmp_path / "sample.wav"
    dummy_file.write_bytes(b"dummy wav data")

    with patch("app.voice.stt.SpeechRecognitionSTT.transcribe_file", return_value="fallback recognized text") as mock_sr:
        result = stt.transcribe_file(str(dummy_file))
        assert result == "fallback recognized text"


def test_deepgram_handles_api_error():
    """When Deepgram returns a non-200 HTTP code, transcribe_bytes handles it safely."""
    stt = DeepgramSTT(api_key="valid_token_xyz")

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Invalid credentials"

    with patch("requests.post", return_value=mock_resp):
        result = stt.transcribe_bytes(b"dummy audio")
        assert result is None
