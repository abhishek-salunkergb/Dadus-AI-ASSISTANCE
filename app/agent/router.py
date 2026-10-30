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
        Follows all DADUS capabilities and natural conversational requirements.
        """
        from app.memory.memory import memory_store

        clean = text.strip().rstrip(".?!")
        lower = clean.lower()

        # Strip wake phrase if present, while preserving original casing in 'clean'
        for wp in ["hey dadus", "dadus", "ok dadus", "hi dadus"]:
            if lower.startswith(wp):
                prefix_len = len(wp)
                clean = clean[prefix_len:].lstrip(", ").strip()
                lower = clean.lower()
                break

        # -------------------------------------------------------------
        # 1. Conversational Brain & Coaching
        # -------------------------------------------------------------
        if any(p in lower for p in ["i'm bored", "im bored", "suggest something", "feeling bored"]):
            return None, (
                "Boss, if you're looking for something engaging: we could make progress on your "
                "Python project, play some relaxing music on Spotify, or run through your tasks. "
                "What sounds good?"
            )

        if "interview" in lower and any(p in lower for p in ["prepare", "tomorrow", "help me", "practice", "ready"]):
            return None, (
                "Boss, congratulations on the interview! Let's get you prepared. Would you like to "
                "practice technical questions on Python and system design, run through a mock behavioral Q&A, "
                "or review your project highlights?"
            )

        # -------------------------------------------------------------
        # 2. Memory Storage & Updates (Store preferences, facts, topics)
        # -------------------------------------------------------------
        # Music preference: "Remember that I prefer Spotify"
        mem_prefer_match = re.search(r"remember\s+that\s+i\s+prefer\s+([a-zA-Z0-9_\s]+)", clean, re.IGNORECASE)
        if mem_prefer_match:
            app_pref = mem_prefer_match.group(1).strip(" .?!'\"").title()
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "preferred_music_app", "value": app_pref, "category": "preference"}
            ), None

        # Learning tech: "Remember that I am learning Python", "Remember that I'm learning Django"
        mem_learn_match = re.search(r"remember\s+(?:that\s+)?(?:i\s+am|i'm)\s+learning\s+([a-zA-Z0-9_\s#+]+)", clean, re.IGNORECASE)
        if mem_learn_match:
            tech = mem_learn_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "learning", "value": tech, "category": "topic"}
            ), None

        # Browser preference: "My preferred browser is Chrome", "Remember that I prefer Chrome"
        browser_match = re.search(r"(?:remember\s+(?:that\s+)?)?(?:my\s+)?preferred\s+browser\s+(?:is\s+)?([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if browser_match and "what" not in lower:
            b = browser_match.group(1).strip(" .?!'\"").title()
            if "Chrome" in b:
                b = "Google Chrome"
            return PlannedToolCall(
                tool_name="store_memory",
                arguments={"key": "preferred_browser", "value": b, "category": "preference"}
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

        # -------------------------------------------------------------
        # 3. Conversational Long-Term Memory Answering
        # -------------------------------------------------------------
        # Check if this is a direct question about memories
        mem_answer = memory_store.answer_memory_query(clean)
        if mem_answer:
            return None, mem_answer

        # -------------------------------------------------------------
        # 4. Media Playback Controls & Relative Volume
        # -------------------------------------------------------------
        # Pause / Resume / Skip
        if lower in ["pause", "pause music", "pause the music", "stop music", "stop the music"]:
            return PlannedToolCall(tool_name="pause_music", arguments={}), None

        if lower in ["resume", "resume music", "resume the music", "unpause"]:
            return PlannedToolCall(tool_name="resume_music", arguments={}), None

        if any(p in lower for p in ["skip this song", "skip the song", "skip song", "skip track", "next song", "next track"]):
            return PlannedToolCall(tool_name="skip_music_track", arguments={}), None

        # Relative Volume adjustments: "make the volume slightly lower", "increase the volume"
        if any(p in lower for p in ["volume slightly lower", "slightly lower", "lower the volume", "volume lower", "turn it down", "turn down the volume", "softer"]):
            return PlannedToolCall(
                tool_name="adjust_volume",
                arguments={"delta": -10, "direction": "lower"}
            ), None

        if any(p in lower for p in ["increase the volume", "volume higher", "turn it up", "turn up the volume", "louder", "volume up"]):
            return PlannedToolCall(
                tool_name="adjust_volume",
                arguments={"delta": 10, "direction": "higher"}
            ), None

        # -------------------------------------------------------------
        # 5. Productivity: Tasks, Reminders & Daily Briefing
        # -------------------------------------------------------------
        # Daily Briefing: "give me my morning briefing", "morning briefing"
        if any(p in lower for p in ["morning briefing", "daily briefing", "give me my briefing", "my briefing"]):
            return PlannedToolCall(tool_name="get_daily_briefing", arguments={}), None

        # Tasks: "what are my tasks today?", "what tasks do I have today?"
        if any(p in lower for p in ["what are my tasks today", "what tasks do i have today", "tasks today", "my tasks", "list tasks", "show tasks"]):
            return PlannedToolCall(tool_name="list_tasks", arguments={"status": "pending"}), None

        # Create Task: "create a task to complete my Django project"
        task_create_match = re.search(r"(?:create|add)\s+(?:a\s+)?task\s+(?:to\s+)?(.+)", clean, re.IGNORECASE)
        if task_create_match:
            task_title = task_create_match.group(1).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="create_task",
                arguments={"title": task_title, "priority": "medium"}
            ), None

        # Complete Task: "complete task 1", "mark task complete"
        comp_task_match = re.search(r"(?:complete|finish|mark)\s+task\s+([0-9a-zA-Z\s]+)", clean, re.IGNORECASE)
        if comp_task_match:
            return PlannedToolCall(
                tool_name="complete_task",
                arguments={"task_id_or_title": comp_task_match.group(1).strip()}
            ), None

        # Recurring Reminder: "Remind me every day at 8 AM to study Python"
        rec_remind = re.search(r"remind\s+me\s+(?:(every\s+day\s+at\s+[0-9:\sAPMapm]+|daily\s+at\s+[0-9:\sAPMapm]+|every\s+morning\s+at\s+[0-9:\sAPMapm]+))\s+to\s+(.+)", clean, re.IGNORECASE)
        if rec_remind:
            r_time = rec_remind.group(1).strip()
            r_title = rec_remind.group(2).strip(" .?!'\"")
            return PlannedToolCall(
                tool_name="create_reminder",
                arguments={"title": r_title, "time": r_time}
            ), None

        # Standard Reminder: "Remind me at 7 PM to study Python"
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

        # -------------------------------------------------------------
        # 6. Projects, GitHub & Developer Workflow
        # -------------------------------------------------------------
        # "Open the application I use for coding"
        if any(p in lower for p in ["application i use for coding", "app i use for coding", "app for coding", "what i use to code", "my coding app", "my code editor"]):
            ed = memory_store.get_preferred_code_editor() or "Visual Studio Code"
            return PlannedToolCall(
                tool_name="open_app",
                arguments={"app_name": ed}
            ), None

        # "Find my Python project and open its GitHub repository"
        if "github" in lower and any(p in lower for p in ["project", "repo", "repository", "open its"]):
            project_match = re.search(r"(?:find|open)\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)(?:\s+project)?(?:'s|\s+and\s+open|\s+open|\s+its)?\s+github", clean, re.IGNORECASE)
            proj_name = project_match.group(1).strip() if project_match else "Python"
            if proj_name.lower() in ["my", "the", ""]:
                proj_name = "Python"
            return PlannedToolCall(
                tool_name="open_project_github",
                arguments={"project_name": proj_name}
            ), None

        # "Find my Django project and open it in VS Code"
        proj_open_match = re.search(r"find\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)(?:\s+project)?\s+and\s+open(?:\s+it)?\s+in\s+([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if proj_open_match:
            p_name = proj_open_match.group(1).strip()
            p_editor = proj_open_match.group(2).strip()
            if "code" in p_editor.lower():
                p_editor = "Visual Studio Code"
            return PlannedToolCall(
                tool_name="find_project_and_open",
                arguments={"project_name": p_name, "editor": p_editor}
            ), None

        # "Open my Python project"
        open_proj_match = re.search(r"open\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)\s+project", clean, re.IGNORECASE)
        if open_proj_match:
            p_name = open_proj_match.group(1).strip()
            return PlannedToolCall(
                tool_name="find_project_and_open",
                arguments={"project_name": p_name, "editor": "Visual Studio Code"}
            ), None

        # -------------------------------------------------------------
        # 7. File Search & Latest Files
        # -------------------------------------------------------------
        if "latest" in lower and any(ext in lower for ext in ["pdf", "file", "doc", "document", "sheet"]):
            pattern = "*.pdf" if "pdf" in lower else "*.*"
            return PlannedToolCall(
                tool_name="search_files",
                arguments={"query": f"latest {pattern}"}
            ), None

        # -------------------------------------------------------------
        # 8. Web & YouTube Searches
        # -------------------------------------------------------------
        # "Open YouTube and search for Python tutorials"
        yt_and_search = re.search(r"open\s+youtube\s+and\s+search\s+(?:for\s+)?(.+)", clean, re.IGNORECASE)
        if yt_and_search:
            q = yt_and_search.group(1).strip(" .?!'\"")
            return PlannedToolCall(tool_name="search_youtube", arguments={"query": q}), None

        yt_search = re.search(r"search\s+youtube\s+for\s+(.+)", lower)
        if yt_search:
            return PlannedToolCall(tool_name="search_youtube", arguments={"query": yt_search.group(1).strip()}), None

        web_search = re.search(r"search\s+(?:the\s+web\s+|google\s+)?for\s+(.+)", lower)
        if web_search:
            return PlannedToolCall(tool_name="search_web", arguments={"query": web_search.group(1).strip()}), None

        # -------------------------------------------------------------
        # 9. Application Launch & Close
        # -------------------------------------------------------------
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

        close_app_match = re.search(r"\b(?:close|quit|exit|kill|terminate)\s+(?:the\s+|google\s+)?([a-zA-Z0-9\s\.\-_]+)", clean, re.IGNORECASE)
        if close_app_match:
            candidate = close_app_match.group(1).strip(" .?!'\"")
            candidate = re.sub(r"\b(please|for me|app|application)\b", "", candidate, flags=re.IGNORECASE).strip(" .?!'\"")
            if candidate.lower() not in ["window", "tab", "system"]:
                return PlannedToolCall(
                    tool_name="close_app",
                    arguments={"app_name": candidate}
                ), None

        # -------------------------------------------------------------
        # 10. Music Playback
        # -------------------------------------------------------------
        # "Play Believer on Spotify"
        music_on_match = re.search(r"(?:play|put on)\s+(.+?)\s+on\s+([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
        if music_on_match:
            song = music_on_match.group(1).strip(" .?!'\"").title()
            app = music_on_match.group(2).strip(" .?!'\"").title()
            return PlannedToolCall(
                tool_name="play_music",
                arguments={"song": song, "application": app}
            ), None

        # "Play relaxing music", "Play Arijit Singh", "Play my favourite songs"
        music_match = re.search(r"(?:play|put on)\s+(.+)", clean, re.IGNORECASE)
        if music_match:
            raw_song = music_match.group(1).strip(" .?!'\"")
            if raw_song.lower() in ["music", "some music"]:
                raw_song = "Believer"
            return PlannedToolCall(
                tool_name="play_music",
                arguments={"song": raw_song.title(), "application": None}
            ), None

        # -------------------------------------------------------------
        # 11. System Audio & Volume
        # -------------------------------------------------------------
        vol_match = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})(?:\s*%)?", lower)
        if vol_match:
            level = int(vol_match.group(1))
            return PlannedToolCall(
                tool_name="set_volume",
                arguments={"level": min(100, max(0, level))}
            ), None

        if "unmute" in lower:
            return PlannedToolCall(tool_name="mute_volume", arguments={"mute": False}), None
        if "mute" in lower:
            return PlannedToolCall(tool_name="mute_volume", arguments={"mute": True}), None

        # -------------------------------------------------------------
        # 12. Schedule & Events
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # 13. System Status, Hardware & Screenshots
        # -------------------------------------------------------------
        if "screenshot" in lower or "capture screen" in lower:
            return PlannedToolCall(tool_name="take_screenshot", arguments={}), None

        if any(q in lower for q in ["what time", "what is the time", "what's the time", "current time", "the time", "tell me the time"]):
            return PlannedToolCall(tool_name="get_current_time", arguments={}), None

        if any(p in lower for p in ["system status", "computer status", "cpu usage", "how much ram", "ram is currently", "ram used"]):
            return PlannedToolCall(tool_name="get_system_status", arguments={}), None

        if "lock" in lower and any(w in lower for w in ["screen", "pc", "computer", "device", "workstation"]):
            return PlannedToolCall(tool_name="lock_device", arguments={}), None

        # -------------------------------------------------------------
        # 14. File & Folder Operations (Confirmation Required)
        # -------------------------------------------------------------
        del_match = re.search(r"\bdelete\s+(?:the\s+)?(?:folder|file|directory)?\s*(.+)", lower)
        if del_match:
            path_arg = del_match.group(1).strip(" .?!'\"")
            if not path_arg or path_arg in ["this folder", "this"]:
                path_arg = str(settings.DATA_DIR / "scratch")
            return PlannedToolCall(
                tool_name="delete_file_or_folder",
                arguments={"path": path_arg}
            ), None

        # -------------------------------------------------------------
        # 15. Greetings & Conversational Fallback
        # -------------------------------------------------------------
        if lower in ["hello", "hi", "hey", "good morning", "good evening", "are you there"]:
            return None, "Yes, boss? How can I help you?"

        return None, "I'm ready, boss. You can ask me to open apps, play music, set reminders, manage tasks, or check your schedule."

intent_router = IntentRouter()
