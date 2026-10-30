"""Tests for media playback keys and volume adjustment tools."""
from unittest.mock import patch, MagicMock
import pytest
from app.tools.media import PauseMusicTool, ResumeMusicTool, SkipMusicTrackTool, AdjustVolumeTool

def test_pause_and_resume_media_tools():
    pause_tool = PauseMusicTool()
    with patch("ctypes.windll.user32.keybd_event") as mock_kb:
        res = pause_tool.execute()
        assert res.success is True
        assert "pause" in res.message.lower()
        assert mock_kb.call_count == 2

    resume_tool = ResumeMusicTool()
    with patch("ctypes.windll.user32.keybd_event") as mock_kb:
        res = resume_tool.execute()
        assert res.success is True
        assert "resumed" in res.message.lower()
        assert mock_kb.call_count == 2

def test_skip_track_tool():
    tool = SkipMusicTrackTool()
    with patch("ctypes.windll.user32.keybd_event") as mock_kb:
        res = tool.execute()
        assert res.success is True
        assert "next song" in res.message.lower()
        assert mock_kb.call_count == 2

def test_adjust_volume_tool():
    tool = AdjustVolumeTool()
    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers") as mock_speakers:
        mock_endpoint = MagicMock()
        mock_endpoint.GetMasterVolumeLevelScalar.return_value = 0.50
        mock_speakers.return_value.EndpointVolume = mock_endpoint

        res_down = tool.execute(delta=-10, direction="lower")
        assert res_down.success is True
        assert res_down.data["new_level"] == 40
        assert "lowered to 40" in res_down.message

        res_up = tool.execute(delta=15, direction="higher")
        assert res_up.success is True
        assert res_up.data["new_level"] == 65
        assert "increased to 65" in res_up.message
