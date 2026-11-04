"""Tests for Phase 5 Outcome-Oriented Music Playback on YouTube and Spotify."""
import pytest
from unittest.mock import patch, MagicMock

from app.agent.agent import DadusAgent
from app.tools.music import PlayMusicTool, YouTubeResolver

@patch("app.tools.music.launch_browser_url")
def test_youtube_play_direct_video_launch(mock_launch):
    """Verify playing a song on YouTube launches the actual video watch URL, not a generic search page."""
    tool = PlayMusicTool()
    res = tool.execute(song="Believer", application="YouTube")

    assert res.success is True
    assert "Playing Believer on YouTube, Boss." in res.message
    assert res.data["application"] == "YouTube"
    assert res.data["verified"] is True
    # Verify the URL is a direct video watch URL
    assert "youtube.com/watch?v=" in res.data["url"]
    mock_launch.assert_called_once()
    assert "watch?v=" in mock_launch.call_args[0][0]

@patch("app.tools.music.launch_browser_url")
def test_youtube_play_second_result(mock_launch):
    """Verify selecting the second result plays the candidate at index 1."""
    tool = PlayMusicTool()
    res = tool.execute(song="Believer", application="YouTube", result_index=1)

    assert res.success is True
    assert res.data["result_index"] == 1
    assert "youtube.com/watch?v=" in res.data["url"]

@patch("app.tools.music.launch_browser_url")
def test_agent_routes_play_believer_on_youtube(mock_launch):
    """Verify natural language request 'play Believer on YouTube' starts direct playback."""
    agent = DadusAgent()
    resp = agent.process_input("play Believer on YouTube", session_id="test_yt_music")

    assert resp.status == "DONE"
    assert resp.tool_called == "play_music"
    assert "Believer" in resp.text
    assert "YouTube" in resp.text
    mock_launch.assert_called_once()
