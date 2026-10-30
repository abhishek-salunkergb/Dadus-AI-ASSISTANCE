"""Tests for application detection, launch, and music playback workflows."""
import pytest
from app.tools.apps import AppDetector, OpenAppTool, CloseAppTool
from app.tools.music import PlayMusicTool, MusicManager
from app.memory.memory import memory_store

def test_app_detector_known_apps():
    """Verify AppDetector identifies installed apps and aliases."""
    chrome = AppDetector.find_app("Chrome")
    assert chrome is not None
    assert "chrome" in chrome.name.lower() or "chrome" in chrome.executable_or_path.lower()

    vscode = AppDetector.find_app("VS Code")
    assert vscode is not None
    assert "visual studio code" in vscode.name.lower() or "code" in vscode.executable_or_path.lower()

    notepad = AppDetector.find_app("Notepad")
    assert notepad is not None
    assert notepad.executable_or_path == "notepad.exe"

def test_app_detector_not_found():
    """Verify AppDetector returns None for non-existent apps."""
    res = AppDetector.find_app("totally_fictional_application_9999")
    assert res is None

def test_open_app_not_installed():
    """Verify open_app tool gracefully reports uninstalled app."""
    tool = OpenAppTool()
    res = tool.execute(app_name="SuperFictionalGame2099")
    assert res.success is False
    assert "couldn't find" in res.message
    assert res.error == "APP_NOT_FOUND"

def test_music_multiple_apps_clarification():
    """
    Verify that when multiple music apps are available and no preference is set,
    play_music returns needs_clarification=True.
    """
    memory_store.forget("preferred_music_app")
    tool = PlayMusicTool()
    res = tool.execute(song="Believer")

    assert res.needs_clarification is True
    assert "Boss, I found Spotify and YouTube. Which one should I use?" in res.message
    assert res.options is not None
    assert "Spotify" in res.options
    assert "YouTube" in res.options

def test_music_explicit_application():
    """Verify specifying the application executes without clarification."""
    tool = PlayMusicTool()
    res = tool.execute(song="Believer", application="Spotify")
    assert res.needs_clarification is False
    assert res.success is True
    assert "Opening Spotify and playing Believer" in res.message

def test_music_uses_saved_preference():
    """Verify that a saved memory preference bypasses clarification."""
    memory_store.remember("preferred_music_app", "Spotify", "preference")
    tool = PlayMusicTool()
    res = tool.execute(song="Believer")

    assert res.needs_clarification is False
    assert res.success is True
    assert "Spotify" in res.message
    memory_store.forget("preferred_music_app")
