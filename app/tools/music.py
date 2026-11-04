"""Music playback, searching, and application routing for DADUS."""
import os
import urllib.parse
import webbrowser
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.tools.apps import AppDetector
from app.tools.browser import launch_browser_url
from app.memory.memory import memory_store

logger = logging.getLogger("DADUS.Music")

class MusicManager:
    """Detects available music applications and resolves playback routes."""

    @classmethod
    def get_available_music_apps(cls) -> List[str]:
        """
        Check which music services or applications are available.
        Spotify is considered available if the app is installed or Spotify Web/Protocol is usable.
        YouTube is always available via default web browser.
        """
        available = []

        # Check Spotify app or protocol
        spotify_info = AppDetector.find_app("spotify")
        # Also check standard Spotify protocol / web
        if spotify_info or os.path.exists(os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")):
            available.append("Spotify")
        else:
            # On modern desktop, Spotify is accessible via web or app
            available.append("Spotify")

        # YouTube and YouTube Music are accessible via browser
        available.append("YouTube")
        return available

    @classmethod
    def play_track(cls, song: str, application: str) -> ToolResult:
        """Execute playback or search on the chosen application."""
        app_clean = application.strip().lower()
        encoded_query = urllib.parse.quote_plus(song)

        if "spotify" in app_clean:
            # Only use native URI protocol if Spotify desktop client is actually installed
            spotify_installed = AppDetector.find_app("spotify") is not None
            if spotify_installed:
                try:
                    uri = f"spotify:search:{encoded_query}"
                    os.startfile(uri)
                    return ToolResult(
                        tool_name="play_music",
                        success=True,
                        message=f"Opening Spotify and playing {song}.",
                        data={"application": "Spotify", "song": song, "uri": uri}
                    )
                except Exception as ex:
                    logger.warning(f"Spotify URI protocol failed: {ex}")

            # Fallback to Spotify Web player
            web_url = f"https://open.spotify.com/search/{encoded_query}"
            launch_browser_url(web_url)
            return ToolResult(
                tool_name="play_music",
                success=True,
                message=f"Opening Spotify and playing {song}.",
                data={"application": "Spotify", "song": song, "url": web_url}
            )

        elif "youtube" in app_clean:
            # YouTube search / play URL
            yt_url = f"https://www.youtube.com/results?search_query={encoded_query}"
            launch_browser_url(yt_url)
            return ToolResult(
                tool_name="play_music",
                success=True,
                message=f"Opening YouTube and playing {song}.",
                data={"application": "YouTube", "song": song, "url": yt_url}
            )

        else:
            # Generic browser music search
            search_url = f"https://www.google.com/search?q={encoded_query}+song"
            launch_browser_url(search_url)
            return ToolResult(
                tool_name="play_music",
                success=True,
                message=f"Opening music search for {song}.",
                data={"application": application, "song": song, "url": search_url}
            )

# ==========================================
# Tool: play_music
# ==========================================
class PlayMusicInput(BaseModel):
    song: str = Field(description="Name of the song, artist, or music track to play, e.g. 'Believer'")
    application: Optional[str] = Field(
        default=None,
        description="Music application to use, e.g. 'Spotify', 'YouTube'. If omitted, Dadus will check preference or available apps."
    )

class PlayMusicTool(BaseTool):
    name = "play_music"
    description = "Plays or searches a song on Spotify, YouTube, or browser."
    permission_level = PermissionLevel.SAFE
    args_schema = PlayMusicInput

    def execute(self, song: str, application: Optional[str] = None) -> ToolResult:
        logger.info(f"play_music called with song='{song}', app='{application}'")

        # 1. If application is explicitly specified by user
        if application and application.strip():
            return MusicManager.play_track(song, application)

        # 2. Check if user has a stored preference in persistent memory
        preferred_app = memory_store.get_preferred_music_app()
        if preferred_app:
            logger.info(f"Using preferred music app from memory: {preferred_app}")
            return MusicManager.play_track(song, preferred_app)

        # 3. Detect available music applications
        available_apps = MusicManager.get_available_music_apps()

        # If only one app is available, use it directly
        if len(available_apps) == 1:
            return MusicManager.play_track(song, available_apps[0])

        # If multiple apps are available, ask clarification
        if len(available_apps) > 1:
            options_str = " and ".join(available_apps)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, I found {options_str}. Which one should I use?",
                needs_clarification=True,
                options=available_apps,
                data={"pending_action": "play_music", "song": song, "available_apps": available_apps}
            )

        # Fallback to YouTube
        return MusicManager.play_track(song, "YouTube")
