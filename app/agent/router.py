"""Intent routing and structured tool determination for DADUS.
Supports both OpenAI-compatible LLMs and an intelligent offline Semantic Parser.
"""
import re
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from app.config.settings import settings
from app.tools.registry import tool_registry
from app.security.permissions import SecurityInspector
from app.agent.prompts import get_system_prompt

logger = logging.getLogger("DADUS.Router")

class PlannedToolCall:
    def __init__(self, tool_name: str, arguments: Dict[str, Any], direct_response: Optional[str] = None):
        self.tool_name = tool_name
        self.arguments = arguments
        self.direct_response = direct_response

class IntentRouter:
    """Routes user input to structured tool calls via LLM or semantic parsing."""

    def route_intent(self, user_text: str, conversation_history: List[Dict[str, str]]) -> Tuple[Optional[PlannedToolCall], Optional[str]]:
        """
        Determines the intended tool call and arguments from natural language.
        Returns (PlannedToolCall, direct_text_response).
        """
        clean_text = user_text.strip().rstrip(".?!")

        # 1. First-pass Security Check for restricted credential requests
        is_restricted, reason = SecurityInspector.is_query_restricted(clean_text)
        if is_restricted:
            return None, reason

        # 2. If OpenAI / LLM key is configured, try LLM tool calling
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.strip() and not settings.OPENAI_API_KEY.startswith("your_"):
            try:
                llm_call = self._call_llm(clean_text, conversation_history)
                if llm_call:
                    return llm_call, None
            except Exception as ex:
                logger.warning(f"LLM tool calling encountered error, falling back to semantic parser: {ex}")

        # 3. Intelligent Semantic Fallback Parser (guarantees offline & local reliability)
        return self._semantic_parse(clean_text)

    def _call_llm(self, user_text: str, conversation_history: List[Dict[str, str]]) -> Optional[PlannedToolCall]:
        """Invoke OpenAI-compatible chat completions with function tools."""
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS
        )

        messages = [{"role": "system", "content": get_system_prompt()}]
        # Append recent history
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_text})

        tools = tool_registry.get_openai_tools()

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            temperature=settings.LLM_TEMPERATURE
        )

        choice = response.choices[0].message
        if choice.tool_calls:
            tcall = choice.tool_calls[0]
            tname = tcall.function.name
            targs = json.loads(tcall.function.arguments) if tcall.function.arguments else {}
            return PlannedToolCall(tool_name=tname, arguments=targs)

        if choice.content:
            return PlannedToolCall(tool_name="", arguments={}, direct_response=choice.content)

        return None

    def _semantic_parse(self, text: str) -> Tuple[Optional[PlannedToolCall], Optional[str]]:
        """
        Understands natural language requests and maps them directly to structured tools.
        Follows Section 3 & 10 requirements.
        """
        clean = text.strip().rstrip(".?!")
        lower = clean.lower()

        # Strip wake phrase if present, while preserving original casing in 'clean'
        for wp in ["hey dadus", "dadus", "ok dadus", "hi dadus"]:
            if lower.startswith(wp):
                prefix_len = len(wp)
                clean = clean[prefix_len:].lstrip(", ").strip()
                lower = clean.lower()
                break

        # 1. Memory preferences: "Remember that I prefer Spotify"
        mem_prefer_match = re.search(r"remember\s+that\s+i\s+prefer\s+([a-zA-Z0-9_\s]+)", clean, re.IGNORECASE)
        if mem_prefer_match:
            app_pref = mem_prefer_match.group(1).strip(" .?!'\"").title()
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "preferred_music_app", "value": app_pref, "category": "preference"}
            ), None

        # General remember: "Remember that X is Y"
        mem_match = re.search(r"remember\s+(?:that\s+)?(.+)", clean, re.IGNORECASE)
        if mem_match and "schedule" not in lower and "remind" not in lower:
            content = mem_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "user_note", "value": content, "category": "fact"}
            ), None

        # Forget memory: "Forget that I prefer Spotify"
        forget_match = re.search(r"forget\s+(?:that\s+i\s+prefer\s+|that\s+)?([a-zA-Z0-9_\s]+)", clean, re.IGNORECASE)
        if forget_match:
            target = forget_match.group(1).strip(" .?!'\"")
            key = "preferred_music_app" if "spotify" in target.lower() or "music" in target.lower() else target
            return PlannedToolCall(
                tool_name="forget_memory",
                arguments={"key": key}
            ), None

        # 2. Open Application: "Open Chrome", "Launch Chrome", "Can you open Google Chrome?", "Open VS Code", "Open my code editor"
        open_app_match = re.search(r"\b(?:open|launch|start|run|bring up)\s+(?:the\s+|my\s+|google\s+)?([a-zA-Z0-9\s\.\-_]+)", clean, re.IGNORECASE)
        if open_app_match:
            candidate = open_app_match.group(1).strip(" .?!'\"")
            candidate = re.sub(r"\b(please|for me|app|application)\b", "", candidate, flags=re.IGNORECASE).strip(" .?!'\"")

            # Disambiguate generic categories
            if candidate.lower() in ["code editor", "editor", "ide"]:
                candidate = "Visual Studio Code"
            elif candidate.lower() in ["browser", "web browser"]:
                candidate = "Google Chrome"

            # Check if this is a music request like "play X"
            if not candidate.lower().startswith("music") and candidate.lower() not in ["song", "youtube"]:
                return PlannedToolCall(
                    tool_name="open_app",
                    arguments={"app_name": candidate.title() if len(candidate) > 4 else candidate.upper()}
                ), None

        # 3. Close Application: "Close Chrome", "Exit Notepad"
        close_app_match = re.search(r"\b(?:close|quit|exit|kill|terminate)\s+(?:the\s+|google\s+)?([a-zA-Z0-9\s\.\-_]+)", clean, re.IGNORECASE)
        if close_app_match:
            candidate = close_app_match.group(1).strip(" .?!'\"")
            candidate = re.sub(r"\b(please|for me|app|application)\b", "", candidate, flags=re.IGNORECASE).strip(" .?!'\"")
            if candidate.lower() not in ["window", "tab", "system"]:
                return PlannedToolCall(
                    tool_name="close_app",
                    arguments={"app_name": candidate}
                ), None

        # 4. Play Music: "Play Believer on Spotify", "Play Believer", "Put on Believer"
        music_on_match = re.search(r"(?:play|put on)\s+(.+?)\s+on\s+([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if music_on_match:
            song = music_on_match.group(1).strip(" .?!'\"").title()
            app = music_on_match.group(2).strip(" .?!'\"").title()
            return PlannedToolCall(
                tool_name="play_music",
                arguments={"song": song, "application": app}
            ), None

        music_match = re.search(r"(?:play|put on)\s+(.+)", clean, re.IGNORECASE)
        if music_match:
            song = music_match.group(1).strip(" .?!'\"")
            if song.lower() in ["music", "some music"]:
                song = "Believer"
            else:
                song = song.title()
            return PlannedToolCall(
                tool_name="play_music",
                arguments={"song": song, "application": None}
            ), None

        # 5. Volume: "Set volume to 30 percent", "Set volume to 30", "Volume 30"
        vol_match = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})(?:\s*%)?", lower)
        if vol_match:
            level = int(vol_match.group(1))
            return PlannedToolCall(
                tool_name="set_volume",
                arguments={"level": min(100, max(0, level))}
            ), None

        # Mute / Unmute
        if "unmute" in lower:
            return PlannedToolCall(tool_name="mute_volume", arguments={"mute": False}), None
        if "mute" in lower:
            return PlannedToolCall(tool_name="mute_volume", arguments={"mute": True}), None

        # 6. Reminders: "Remind me at 7 PM to study Python"
        remind_match = re.search(r"remind\s+me\s+(?:at\s+([0-9:\sAPMapm]+)\s+)?to\s+(.+?)(?:\s+at\s+([0-9:\sAPMapm]+))?$", clean, re.IGNORECASE)
        if remind_match:
            time_part = (remind_match.group(1) or remind_match.group(3) or "in 1 hour").strip(" .?!'\"")
            title_part = remind_match.group(2).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="create_reminder",
                arguments={"title": title_part, "time": time_part}
            ), None

        if "list reminders" in lower or "show reminders" in lower or "my reminders" in lower:
            return PlannedToolCall(tool_name="list_reminders", arguments={"status": "pending"}), None

        # 7. Schedule: "What is my schedule today?", "Add gym at 5 PM"
        if "schedule" in lower:
            target_date = "today"
            if "tomorrow" in lower:
                target_date = "tomorrow"
            return PlannedToolCall(
                tool_name="get_today_schedule",
                arguments={"target_date": target_date}
            ), None

        sched_add = re.search(r"(?:add|schedule)\s+(.+?)\s+(?:at|for)\s+([0-9:\sAPMapm]+)", clean, re.IGNORECASE)
        if sched_add:
            title = sched_add.group(1).strip(" .?!'\"").title()
            stime = sched_add.group(2).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="create_schedule_item",
                arguments={"title": title, "start_time": stime}
            ), None

        # 8. Screenshot: "Take a screenshot", "Capture screen"
        if "screenshot" in lower or "capture screen" in lower:
            return PlannedToolCall(tool_name="take_screenshot", arguments={}), None

        # 9. Time: "What time is it?", "What is the time?"
        if any(q in lower for q in ["what time", "what is the time", "what's the time", "current time", "the time", "tell me the time"]):
            return PlannedToolCall(tool_name="get_current_time", arguments={}), None

        # 10. System Status: "System status", "How is my computer"
        if "system status" in lower or "computer status" in lower or "cpu usage" in lower:
            return PlannedToolCall(tool_name="get_system_status", arguments={}), None

        # 11. Lock Device: "Lock my PC", "Lock the screen", "Lock device"
        if "lock" in lower and any(w in lower for w in ["screen", "pc", "computer", "device", "workstation"]):
            return PlannedToolCall(tool_name="lock_device", arguments={}), None

        # 12. Delete File / Folder: "Delete this folder", "Delete file X"
        del_match = re.search(r"\bdelete\s+(?:the\s+)?(?:folder|file|directory)?\s*(.+)", lower)
        if del_match:
            path_arg = del_match.group(1).strip(" .?!'\"")
            if not path_arg or path_arg in ["this folder", "this"]:
                path_arg = str(settings.DATA_DIR / "scratch")
            return PlannedToolCall(
                tool_name="delete_file_or_folder",
                arguments={"path": path_arg}
            ), None

        # 13. Search Web / YouTube
        yt_search = re.search(r"search\s+youtube\s+for\s+(.+)", lower)
        if yt_search:
            return PlannedToolCall(tool_name="search_youtube", arguments={"query": yt_search.group(1).strip()}), None

        web_search = re.search(r"search\s+(?:the\s+web\s+|google\s+)?for\s+(.+)", lower)
        if web_search:
            return PlannedToolCall(tool_name="search_web", arguments={"query": web_search.group(1).strip()}), None

        # 14. Friendly conversational greetings
        if lower in ["hello", "hi", "hey", "good morning", "good evening", "are you there"]:
            return None, "Yes, boss? How can I help you?"

        # Fallback default response
        return None, "I'm ready, boss. You can ask me to open apps, play music, set reminders, or check your schedule."

intent_router = IntentRouter()
