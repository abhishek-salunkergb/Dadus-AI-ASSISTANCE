"""Controlled web browser automation and search tools for DADUS."""
import webbrowser
import urllib.parse
import logging
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel

logger = logging.getLogger("DADUS.Browser")

# ==========================================
# Tool: open_browser
# ==========================================
class OpenBrowserInput(BaseModel):
    url: str = Field(description="URL to open in the default web browser, e.g. 'https://github.com'")

class OpenBrowserTool(BaseTool):
    name = "open_browser"
    description = "Opens a web URL in the user's default browser."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenBrowserInput

    def execute(self, url: str) -> ToolResult:
        clean_url = url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            clean_url = f"https://{clean_url}"

        try:
            webbrowser.open(clean_url)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Opening browser to {clean_url}.",
                data={"url": clean_url}
            )
        except Exception as ex:
            logger.error(f"Failed to open browser URL {clean_url}: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't open {clean_url} in the browser.",
                error=str(ex)
            )

# ==========================================
# Tool: search_web
# ==========================================
class SearchWebInput(BaseModel):
    query: str = Field(description="Search query to search on Google, e.g. 'latest AI news'")

class SearchWebTool(BaseTool):
    name = "search_web"
    description = "Searches the web for a query using the default browser."
    permission_level = PermissionLevel.SAFE
    args_schema = SearchWebInput

    def execute(self, query: str) -> ToolResult:
        encoded = urllib.parse.quote_plus(query.strip())
        search_url = f"https://www.google.com/search?q={encoded}"
        try:
            webbrowser.open(search_url)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Searching the web for '{query}'.",
                data={"query": query, "url": search_url}
            )
        except Exception as ex:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't perform the search for '{query}'.",
                error=str(ex)
            )

# ==========================================
# Tool: search_youtube
# ==========================================
class SearchYouTubeInput(BaseModel):
    query: str = Field(description="Video or topic to search on YouTube, e.g. 'Python tutorials'")

class SearchYouTubeTool(BaseTool):
    name = "search_youtube"
    description = "Searches YouTube for videos matching the query."
    permission_level = PermissionLevel.SAFE
    args_schema = SearchYouTubeInput

    def execute(self, query: str) -> ToolResult:
        encoded = urllib.parse.quote_plus(query.strip())
        yt_url = f"https://www.youtube.com/results?search_query={encoded}"
        try:
            webbrowser.open(yt_url)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Searching YouTube for '{query}'.",
                data={"query": query, "url": yt_url}
            )
        except Exception as ex:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't open YouTube search for '{query}'.",
                error=str(ex)
            )
