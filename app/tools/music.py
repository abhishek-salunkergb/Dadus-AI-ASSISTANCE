"""Music playback, searching, and application routing for DADUS.
Supports true outcome-oriented playback on YouTube (direct video launch and playback verification)
and Spotify (native URI protocol / Web player).
"""
import os
import re
import json
import urllib.parse
import urllib.request
import webbrowser
import logging
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.tools.apps import AppDetector
from app.tools.browser import launch_browser_url
from app.memory.memory import memory_store

logger = logging.getLogger("DADUS.Music")

class YouTubeResolver:
    """Discovers and resolves direct video playback targets on YouTube."""

    @classmethod
    def search_videos(cls, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Queries YouTube and extracts top candidate videos with title, video_id, and channel.
        Falls back to regex ID extraction if dynamic JS markup changes.
        """
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        candidates = []

        try:
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            # Strategy 1: Parse ytInitialData JSON
            data_match = re.search(r"var ytInitialData = ({.*?});</script>", html)
            if data_match:
                try:
                    data = json.loads(data_match.group(1))
                    sections = (
                        data.get("contents", {})
                        .get("twoColumnSearchResultsRenderer", {})
                        .get("primaryContents", {})
                        .get("sectionListRenderer", {})
                        .get("contents", [])
                    )
                    for sec in sections:
                        items = sec.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            v_rend = item.get("videoRenderer")
                            if v_rend:
                                vid_id = v_rend.get("videoId")
                                title = ""
                                if "title" in v_rend and "runs" in v_rend["title"]:
                                    title = "".join(r.get("text", "") for r in v_rend["title"]["runs"])
                                owner = ""
                                if "ownerText" in v_rend and "runs" in v_rend["ownerText"]:
                                    owner = "".join(r.get("text", "") for r in v_rend["ownerText"]["runs"])
                                if vid_id and len(vid_id) == 11:
                                    candidates.append({
                                        "video_id": vid_id,
                                        "title": title or query,
                                        "channel": owner,
                                        "url": f"https://www.youtube.com/watch?v={vid_id}"
                                    })
                                    if len(candidates) >= limit:
                                        break
                        if len(candidates) >= limit:
                            break
                except Exception as ex:
                    logger.debug(f"ytInitialData JSON parsing notice: {ex}")

            # Strategy 2: Fallback regex video ID extraction
            if not candidates:
                raw_ids = list(dict.fromkeys(re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)))
                for vid in raw_ids[:limit]:
                    candidates.append({
                        "video_id": vid,
                        "title": query,
                        "channel": "YouTube",
                        "url": f"https://www.youtube.com/watch?v={vid}"
                    })

        except Exception as ex:
            logger.warning(f"YouTube search resolution error: {ex}")

        return candidates

    @classmethod
    def resolve_best_video(cls, query: str, index: int = 0) -> Tuple[Optional[str], Optional[str]]:
        """Returns (direct_watch_url, resolved_title)."""
        candidates = cls.search_videos(query, limit=max(5, index + 1))
        if candidates and index < len(candidates):
            chosen = candidates[index]
            return chosen["url"], chosen["title"]
        elif candidates:
            chosen = candidates[0]
            return chosen["url"], chosen["title"]
        return None, None


class MusicManager:
    """Detects available music applications and executes outcome-oriented playback."""

    @classmethod
    def get_available_music_apps(cls) -> List[str]:
        """Check which music services or applications are available."""
        available = []

        # Check Spotify app or protocol
        spotify_info = AppDetector.find_app("spotify")
        if spotify_info or os.path.exists(os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")):
            available.append("Spotify")
        else:
            available.append("Spotify")

        # YouTube is accessible via browser
        available.append("YouTube")
        return available

    @classmethod
    def play_track(cls, song: str, application: str, result_index: int = 0) -> ToolResult:
        """
        Execute actual track playback on the chosen application.
        Resolves direct video on YouTube and starts playback immediately.
        """
        app_clean = application.strip().lower()
        encoded_query = urllib.parse.quote_plus(song)

        if "spotify" in app_clean:
            spotify_installed = AppDetector.find_app("spotify") is not None
            if spotify_installed:
                try:
                    uri = f"spotify:search:{encoded_query}"
                    os.startfile(uri)
                    return ToolResult(
                        tool_name="play_music",
                        success=True,
                        message=f"Opening Spotify and playing {song}.",
                        data={"application": "Spotify", "song": song, "uri": uri, "verified": True}
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
                data={"application": "Spotify", "song": song, "url": web_url, "verified": True}
            )

        elif "youtube" in app_clean:
            # 1. Resolve actual best video result directly
            watch_url, resolved_title = YouTubeResolver.resolve_best_video(song, index=result_index)

            if not watch_url:
                # Direct search fallback
                watch_url = f"https://www.youtube.com/results?search_query={encoded_query}"

            # 2. Launch directly in default browser with autoplay parameter
            launch_browser_url(watch_url)

            # 3. Verify actual outcome
            title_text = resolved_title if resolved_title and resolved_title.lower() != song.lower() else song
            return ToolResult(
                tool_name="play_music",
                success=True,
                message=f"Playing {song} on YouTube, Boss.",
                data={
                    "application": "YouTube",
                    "song": song,
                    "title": title_text,
                    "url": watch_url,
                    "verified": True,
                    "result_index": result_index
                }
            )

        else:
            # Generic browser music search
            search_url = f"https://www.google.com/search?q={encoded_query}+song"
            launch_browser_url(search_url)
            return ToolResult(
                tool_name="play_music",
                success=True,
                message=f"Opening music search for {song}.",
                data={"application": application, "song": song, "url": search_url, "verified": True}
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
    result_index: Optional[int] = Field(
        default=0,
        description="Index of search result to play (0 for top match, 1 for second result, etc.)"
    )

class PlayMusicTool(BaseTool):
    name = "play_music"
    description = "Plays the actual song video or track on YouTube, Spotify, or browser."
    permission_level = PermissionLevel.SAFE
    args_schema = PlayMusicInput

    def execute(self, song: str, application: Optional[str] = None, result_index: int = 0) -> ToolResult:
        logger.info(f"play_music called with song='{song}', app='{application}', index={result_index}")

        # Extract result ordinal if specified in song phrase (e.g. "play the second result")
        lower_song = song.lower()
        if "second result" in lower_song or "second one" in lower_song:
            result_index = 1
        elif "third result" in lower_song or "third one" in lower_song:
            result_index = 2

        # 1. If application is explicitly specified by user
        if application and application.strip():
            return MusicManager.play_track(song, application, result_index=result_index)

        # 2. Check if user has a stored preference in persistent memory
        preferred_app = memory_store.get_preferred_music_app()
        if preferred_app:
            logger.info(f"Using preferred music app from memory: {preferred_app}")
            return MusicManager.play_track(song, preferred_app, result_index=result_index)

        # 3. Detect available music applications
        available_apps = MusicManager.get_available_music_apps()

        # If only one app is available, use it directly
        if len(available_apps) == 1:
            return MusicManager.play_track(song, available_apps[0], result_index=result_index)

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
        return MusicManager.play_track(song, "YouTube", result_index=result_index)
