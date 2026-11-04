"""Intent classification and structured tool determination for DADUS.
Supports both OpenAI-compatible tool calling and an offline deterministic parser.
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

WAKE_PREFIXES = ["hey dadus", "dadus", "ok dadus", "hi dadus"]


class PlannedToolCall:
    def __init__(self, tool_name: str, arguments: Dict[str, Any], direct_response: Optional[str] = None):
        self.tool_name = tool_name
        self.arguments = arguments
        self.direct_response = direct_response


class IntentRouter:
    """Routes user input to structured tool calls via LLM tool calling or semantic heuristic parsing."""

    def route_intent(self, user_text: str, conversation_history: List[Dict[str, str]]) -> Tuple[Optional[PlannedToolCall], Optional[str]]:
        """
        Determines the intended tool call and arguments from natural language input.
        Returns a tuple of (PlannedToolCall, direct_text_response).
        """
        clean_text = user_text.strip().rstrip(".?!")

        # 1. Security policy check for sensitive credential requests
        is_restricted, reason = SecurityInspector.is_query_restricted(clean_text)
        if is_restricted:
            return None, reason

        # 2. Fast-path deterministic parsing for high-frequency commands
        fast_call, fast_reply = self._fast_path_parse(clean_text)
        if fast_call or fast_reply:
            return fast_call, fast_reply

        # 3. LLM tool-calling if API key is configured
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.strip() and not settings.OPENAI_API_KEY.startswith("your_"):
            try:
                llm_call = self._call_llm(clean_text, conversation_history)
                if llm_call:
                    return llm_call, None
            except Exception as ex:
                logger.warning(f"LLM tool calling error, falling back to local heuristic parser: {ex}")

        # 4. Local heuristic parser for offline reliability
        return self._semantic_parse(clean_text)

    def _strip_wake_prefix(self, text: str) -> Tuple[str, str]:
        """Strip leading wake phrase while preserving original casing and trimmed lowercase version."""
        clean = text.strip().rstrip(".?!")
        lower = clean.lower()
        for wp in WAKE_PREFIXES:
            if lower.startswith(wp):
                prefix_len = len(wp)
                clean = clean[prefix_len:].lstrip(", ").strip()
                lower = clean.lower()
                break
        return clean, lower

    def _fast_path_parse(self, text: str) -> Tuple[Optional[PlannedToolCall], Optional[str]]:
        """Deterministic resolution for high-frequency unambiguous desktop operations."""
        clean, lower = self._strip_wake_prefix(text)

        # Compound command: "open <app> and play <song>"
        yt_and_play = re.search(r"open\s+youtube\s+and\s+(?:play|put\s+on|listen\s+to)\s+(?:song\s+)?(.+)", clean, re.IGNORECASE)
        if yt_and_play:
            song_name = yt_and_play.group(1).strip(" .?!'\"")
            song_name = re.sub(r"\s+(?:song|track|video)\s*$", "", song_name, flags=re.IGNORECASE).strip()
            return PlannedToolCall(tool_name="play_music", arguments={"song": song_name, "application": "YouTube"}), None

        spotify_and_play = re.search(r"open\s+spotify\s+and\s+(?:play|put\s+on|listen\s+to)\s+(?:song\s+)?(.+)", clean, re.IGNORECASE)
        if spotify_and_play:
            song_name = spotify_and_play.group(1).strip(" .?!'\"")
            song_name = re.sub(r"\s+(?:song|track)\s*$", "", song_name, flags=re.IGNORECASE).strip()
            return PlannedToolCall(tool_name="play_music", arguments={"song": song_name, "application": "Spotify"}), None

        # Direct explicit music routing: "play <song> on <service>"
        music_on_match = re.search(r"(?:play|put on)\s+(.+?)\s+on\s+(spotify|youtube)", clean, re.IGNORECASE)
        if music_on_match:
            song = music_on_match.group(1).strip(" .?!'\"").title()
            app = music_on_match.group(2).strip(" .?!'\"").title()
            return PlannedToolCall(tool_name="play_music", arguments={"song": song, "application": app}), None

        # Compound command: "open youtube and search for <query>"
        yt_and_search = re.search(r"open\s+youtube\s+and\s+search\s+(?:for\s+)?(.+)", clean, re.IGNORECASE)
        if yt_and_search:
            q = yt_and_search.group(1).strip(" .?!'\"")
            return PlannedToolCall(tool_name="search_youtube", arguments={"query": q}), None

        # Reference to primary coding editor
        if any(p in lower for p in ["application i use for coding", "app i use for coding", "app for coding", "what i use to code", "my coding app", "my code editor"]):
            from app.memory.memory import memory_store
            editor = memory_store.get_preferred_code_editor() or "Visual Studio Code"
            return PlannedToolCall(tool_name="open_app", arguments={"app_name": editor}), None

        # Direct application launches
        open_direct = re.match(r"^(?:open|launch|start|bring up)\s+(?:the\s+|my\s+|google\s+)?([a-zA-Z0-9\s\.\-_]+)$", clean, re.IGNORECASE)
        if open_direct:
            cand = open_direct.group(1).strip(" .?!'\"")
            cand_clean = re.sub(r"\b(please|for me|app|application)\b", "", cand, flags=re.IGNORECASE).strip(" .?!'\"")
            if cand_clean and not any(w in cand_clean.lower() for w in ["and", "with", "project", "github", "task", "file", "reminder", "music", "song", "camera", "briefing", "coding", "use for"]):
                if cand_clean.lower() in ["code editor", "editor", "ide"]:
                    cand_clean = "Visual Studio Code"
                elif cand_clean.lower() in ["browser", "web browser"]:
                    cand_clean = "Google Chrome"
                formatted_name = cand_clean.title() if len(cand_clean) > 4 else cand_clean.upper()
                return PlannedToolCall(tool_name="open_app", arguments={"app_name": formatted_name}), None

        return None, None

    def _call_llm(self, user_text: str, conversation_history: List[Dict[str, str]]) -> Optional[PlannedToolCall]:
        """Invoke OpenAI-compatible chat completions with function tools."""
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS
        )

        messages = [{"role": "system", "content": get_system_prompt()}]
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
        """Maps natural language intent to concrete tool execution calls."""
        from app.memory.memory import memory_store

        clean, lower = self._strip_wake_prefix(text)

        # Conversational guidance and dynamic synthesis
        from app.agent.conversational import ConversationalSynthesizer
        conv_reply = ConversationalSynthesizer.synthesize_response(clean)
        if conv_reply:
            return None, conv_reply

        # Memory storage & preferences
        mem_prefer_match = re.search(r"remember\s+that\s+i\s+prefer\s+([a-zA-Z0-9_\s]+)", clean, re.IGNORECASE)
        if mem_prefer_match:
            app_pref = mem_prefer_match.group(1).strip(" .?!'\"").title()
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "preferred_music_app", "value": app_pref, "category": "preference"}
            ), None

        mem_learn_match = re.search(r"remember\s+(?:that\s+)?(?:i\s+am|i'm)\s+learning\s+([a-zA-Z0-9_\s#+]+)", clean, re.IGNORECASE)
        if mem_learn_match:
            tech = mem_learn_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "learning", "value": tech, "category": "topic"}
            ), None

        browser_match = re.search(r"(?:remember\s+(?:that\s+)?)?(?:my\s+)?preferred\s+browser\s+(?:is\s+)?([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if browser_match and "what" not in lower:
            b = browser_match.group(1).strip(" .?!'\"").title()
            if "Chrome" in b:
                b = "Google Chrome"
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "preferred_browser", "value": b, "category": "preference"}
            ), None

        mem_match = re.search(r"remember\s+(?:that\s+)?(.+)", clean, re.IGNORECASE)
        if mem_match and "schedule" not in lower and "remind" not in lower:
            content = mem_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "user_note", "value": content, "category": "fact"}
            ), None

        forget_match = re.search(r"forget\s+(?:that\s+i\s+prefer\s+|that\s+)?([a-zA-Z0-9_\s]+)", clean, re.IGNORECASE)
        if forget_match:
            target = forget_match.group(1).strip(" .?!'\"")
            key = "preferred_music_app" if "spotify" in target.lower() or "music" in target.lower() else target
            return PlannedToolCall(tool_name="forget_memory", arguments={"key": key}), None

        # Conversational memory recall
        mem_answer = memory_store.answer_memory_query(clean)
        if mem_answer:
            return None, mem_answer

        # Speech / Assistant Stop Command
        if lower in ["stop", "stop talking", "stop reading", "be quiet", "shut up", "quiet", "cancel", "halt"]:
            from app.voice.tts import get_tts_provider
            try:
                get_tts_provider().stop()
            except Exception:
                pass
            return None, "Stopped, boss."

        # Media playback controls
        if lower in ["pause", "pause music", "pause the music", "stop music", "stop the music"]:
            return PlannedToolCall(tool_name="pause_music", arguments={}), None

        if lower in ["resume", "resume music", "resume the music", "unpause"]:
            return PlannedToolCall(tool_name="resume_music", arguments={}), None

        if any(p in lower for p in ["skip this song", "skip the song", "skip song", "skip track", "next song", "next track"]):
            return PlannedToolCall(tool_name="skip_music_track", arguments={}), None

        if any(p in lower for p in ["volume slightly lower", "slightly lower", "lower the volume", "volume lower", "turn it down", "turn down the volume", "softer"]):
            return PlannedToolCall(tool_name="adjust_volume", arguments={"delta": -10, "direction": "lower"}), None

        if any(p in lower for p in ["increase the volume", "volume higher", "turn it up", "turn up the volume", "louder", "volume up"]):
            return PlannedToolCall(tool_name="adjust_volume", arguments={"delta": 10, "direction": "higher"}), None

        # Tasks, briefings & reminders
        if any(p in lower for p in ["morning briefing", "daily briefing", "give me my briefing", "my briefing"]):
            return PlannedToolCall(tool_name="get_daily_briefing", arguments={}), None

        if any(p in lower for p in ["what are my tasks today", "what tasks do i have today", "tasks today", "my tasks", "list tasks", "show tasks"]):
            return PlannedToolCall(tool_name="list_tasks", arguments={"status": "pending"}), None

        task_create_match = re.search(r"(?:create|add)\s+(?:a\s+)?task\s+(?:to\s+)?(.+)", clean, re.IGNORECASE)
        if task_create_match:
            task_title = task_create_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(tool_name="create_task", arguments={"title": task_title, "priority": "medium"}), None

        comp_task_match = re.search(r"(?:complete|finish|mark)\s+task\s+([0-9a-zA-Z\s]+)", clean, re.IGNORECASE)
        if comp_task_match:
            return PlannedToolCall(tool_name="complete_task", arguments={"task_id_or_title": comp_task_match.group(1).strip()}), None

        del_task_match = re.search(r"(?:delete|remove|clear|drop)\s+task\s+(.+)", clean, re.IGNORECASE)
        if del_task_match:
            task_target = del_task_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(tool_name="delete_task", arguments={"task_id_or_title": task_target}), None

        rec_remind = re.search(r"remind\s+me\s+(?:(every\s+day\s+at\s+[0-9:\sAPMapm]+|daily\s+at\s+[0-9:\sAPMapm]+|every\s+morning\s+at\s+[0-9:\sAPMapm]+))\s+to\s+(.+)", clean, re.IGNORECASE)
        if rec_remind:
            r_time = rec_remind.group(1).strip()
            r_title = rec_remind.group(2).strip(" .?!'\"")
            return PlannedToolCall(tool_name="create_reminder", arguments={"title": r_title, "time": r_time}), None

        remind_match = re.search(r"remind\s+me\s+(?:at\s+([0-9:\sAPMapm]+)\s+)?to\s+(.+?)(?:\s+at\s+([0-9:\sAPMapm]+))?$", clean, re.IGNORECASE)
        if remind_match:
            time_part = (remind_match.group(1) or remind_match.group(3) or "in 1 hour").strip(" .?!'\"")
            title_part = remind_match.group(2).strip(" .?!'\"")
            return PlannedToolCall(tool_name="create_reminder", arguments={"title": title_part, "time": time_part}), None

        if "list reminders" in lower or "show reminders" in lower or "my reminders" in lower:
            return PlannedToolCall(tool_name="list_reminders", arguments={"status": "pending"}), None

        # Developer workflows & project operations
        if any(p in lower for p in ["application i use for coding", "app i use for coding", "app for coding", "what i use to code", "my coding app", "my code editor"]):
            editor = memory_store.get_preferred_code_editor() or "Visual Studio Code"
            return PlannedToolCall(tool_name="open_app", arguments={"app_name": editor}), None

        if "github" in lower and any(p in lower for p in ["project", "repo", "repository", "open its"]):
            project_match = re.search(r"(?:find|open)\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)(?:\s+project)?(?:'s|\s+and\s+open|\s+open|\s+its)?\s+github", clean, re.IGNORECASE)
            proj_name = project_match.group(1).strip() if project_match else "Python"
            if proj_name.lower() in ["my", "the", ""]:
                proj_name = "Python"
            return PlannedToolCall(tool_name="open_project_github", arguments={"project_name": proj_name}), None

        proj_open_match = re.search(r"find\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)(?:\s+project)?\s+and\s+open(?:\s+it)?\s+in\s+([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if proj_open_match:
            p_name = proj_open_match.group(1).strip()
            p_editor = proj_open_match.group(2).strip()
            if "code" in p_editor.lower():
                p_editor = "Visual Studio Code"
            return PlannedToolCall(tool_name="find_project_and_open", arguments={"project_name": p_name, "editor": p_editor}), None

        open_proj_match = re.search(r"open\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)\s+project", clean, re.IGNORECASE)
        if open_proj_match:
            p_name = open_proj_match.group(1).strip()
            return PlannedToolCall(tool_name="find_project_and_open", arguments={"project_name": p_name, "editor": "Visual Studio Code"}), None

        # File searches
        if "latest" in lower and any(ext in lower for ext in ["pdf", "file", "doc", "document", "sheet"]):
            pattern = "*.pdf" if "pdf" in lower else "*.*"
            return PlannedToolCall(tool_name="search_files", arguments={"query": f"latest {pattern}"}), None

        # Search queries
        yt_search = re.search(r"search\s+youtube\s+for\s+(.+)", lower)
        if yt_search:
            return PlannedToolCall(tool_name="search_youtube", arguments={"query": yt_search.group(1).strip()}), None

        web_search = re.search(r"search\s+(?:the\s+web\s+|google\s+)?for\s+(.+)", lower)
        if web_search:
            return PlannedToolCall(tool_name="search_web", arguments={"query": web_search.group(1).strip()}), None

        # Contacts & communication
        call_match = re.search(r"^(?:please\s+)?(?:call|phone|make\s+a\s+call\s+to|dial)\s+(.+)", clean, re.IGNORECASE)
        if call_match:
            c_name = call_match.group(1).strip(" .?!'\"")
            c_name = re.sub(r"\b(please|for me|now)\b", "", c_name, flags=re.IGNORECASE).strip(" .?!'\"")
            if c_name:
                return PlannedToolCall(tool_name="call_contact", arguments={"contact_name": c_name}), None

        msg_match = re.search(r"^(?:please\s+)?(?:message|text|send\s+a\s+message\s+to|chat\s+with)\s+(.+)", clean, re.IGNORECASE)
        if msg_match:
            c_name = msg_match.group(1).strip(" .?!'\"")
            c_name = re.sub(r"\b(please|for me|now)\b", "", c_name, flags=re.IGNORECASE).strip(" .?!'\"")
            if c_name:
                return PlannedToolCall(tool_name="message_contact", arguments={"contact_name": c_name}), None

        if any(p in lower for p in ["list contacts", "show contacts", "my contacts", "who are my contacts", "all contacts"]):
            return PlannedToolCall(tool_name="list_contacts", arguments={}), None

        # Application lifecycle
        open_app_match = re.search(r"\b(?:open|launch|start|run|bring up)\s+(?:the\s+|my\s+|google\s+)?([a-zA-Z0-9\s\.\-_]+)", clean, re.IGNORECASE)
        if open_app_match:
            candidate = open_app_match.group(1).strip(" .?!'\"")
            candidate = re.sub(r"\b(please|for me|app|application)\b", "", candidate, flags=re.IGNORECASE).strip(" .?!'\"")
            if candidate.lower() in ["code editor", "editor", "ide"]:
                candidate = "Visual Studio Code"
            elif candidate.lower() in ["browser", "web browser"]:
                candidate = "Google Chrome"

            if not candidate.lower().startswith("music") and candidate.lower() != "song":
                return PlannedToolCall(
                    tool_name="open_app",
                    arguments={"app_name": candidate.title() if len(candidate) > 4 else candidate.upper()}
                ), None

        close_app_match = re.search(r"\b(?:close|quit|exit|kill|terminate)\s+(?:the\s+|google\s+)?([a-zA-Z0-9\s\.\-_]+)", clean, re.IGNORECASE)
        if close_app_match:
            candidate = close_app_match.group(1).strip(" .?!'\"")
            candidate = re.sub(r"\b(please|for me|app|application)\b", "", candidate, flags=re.IGNORECASE).strip(" .?!'\"")
            if candidate.lower() not in ["window", "tab", "system"]:
                return PlannedToolCall(tool_name="close_app", arguments={"app_name": candidate}), None

        # Music playback
        music_on_match = re.search(r"(?:play|put on)\s+(.+?)\s+on\s+([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if music_on_match:
            song = music_on_match.group(1).strip(" .?!'\"").title()
            app = music_on_match.group(2).strip(" .?!'\"").title()
            return PlannedToolCall(tool_name="play_music", arguments={"song": song, "application": app}), None

        music_match = re.search(r"(?:play|put on)\s+(.+)", clean, re.IGNORECASE)
        if music_match:
            raw_song = music_match.group(1).strip(" .?!'\"")
            if raw_song.lower() in ["music", "some music"]:
                raw_song = "relaxing music"
            return PlannedToolCall(tool_name="play_music", arguments={"song": raw_song.title(), "application": None}), None

        # System volume controls
        vol_match = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})(?:\s*%)?", lower)
        if vol_match:
            level = int(vol_match.group(1))
            return PlannedToolCall(tool_name="set_volume", arguments={"level": min(100, max(0, level))}), None

        if "unmute" in lower:
            return PlannedToolCall(tool_name="mute_volume", arguments={"mute": False}), None
        if "mute" in lower:
            return PlannedToolCall(tool_name="mute_volume", arguments={"mute": True}), None

        # Scheduling
        if "schedule" in lower:
            target_date = "tomorrow" if "tomorrow" in lower else "today"
            return PlannedToolCall(tool_name="get_today_schedule", arguments={"target_date": target_date}), None

        sched_add = re.search(r"(?:add|schedule)\s+(.+?)\s+(?:at|for)\s+([0-9:\sAPMapm]+)", clean, re.IGNORECASE)
        if sched_add:
            title = sched_add.group(1).strip(" .?!'\"").title()
            stime = sched_add.group(2).strip(" .?!'\"")
            return PlannedToolCall(tool_name="create_schedule_item", arguments={"title": title, "start_time": stime}), None

        # Hardware diagnostics & screen capture
        if "screenshot" in lower or "capture screen" in lower:
            return PlannedToolCall(tool_name="take_screenshot", arguments={}), None

        if any(q in lower for q in ["what time", "what is the time", "what's the time", "current time", "the time", "tell me the time"]):
            return PlannedToolCall(tool_name="get_current_time", arguments={}), None

        if any(p in lower for p in ["system status", "computer status", "cpu usage", "how much ram", "ram is currently", "ram used"]):
            return PlannedToolCall(tool_name="get_system_status", arguments={}), None

        if "lock" in lower and any(w in lower for w in ["screen", "pc", "computer", "device", "workstation"]):
            return PlannedToolCall(tool_name="lock_device", arguments={}), None

        # Log cleanup operations (safe two-phase confirmation)
        if any(p in lower for p in ["delete the logs", "clean up the logs", "clean the logs", "clear the logs", "clean logs", "delete logs", "clear logs"]):
            return PlannedToolCall(tool_name="clean_logs", arguments={}), None

        # Intelligent Gmail operations
        if any(p in lower for p in ["go to gmail", "open gmail", "launch gmail", "check gmail", "view gmail"]):
            return PlannedToolCall(tool_name="open_gmail", arguments={}), None

        if "recruiter" in lower or ("job" in lower and any(w in lower for w in ["email", "reply", "response", "replies", "update"])):
            return PlannedToolCall(tool_name="find_recruiter_emails", arguments={}), None

        if any(p in lower for p in ["open that conversation", "open the conversation", "open that email", "open this thread"]):
            return PlannedToolCall(tool_name="open_email_thread", arguments={}), None

        # Destructive file operations
        del_match = re.search(r"\bdelete\s+(?:the\s+)?(?:folder|file|directory)?\s*(.+)", lower)
        if del_match:
            path_arg = del_match.group(1).strip(" .?!'\"")
            if not path_arg or path_arg in ["this folder", "this"]:
                path_arg = str(settings.DATA_DIR / "scratch")
            return PlannedToolCall(tool_name="delete_file_or_folder", arguments={"path": path_arg}), None

        # Conversational fallback
        if lower in ["hello", "hi", "hey", "good morning", "good evening", "are you there"]:
            return None, "Yes, boss? How can I help you?"

        return None, "I'm ready, boss. You can ask me to open apps, play music, set reminders, manage tasks, or check your schedule."


intent_router = IntentRouter()
