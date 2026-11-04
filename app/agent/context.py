"""Context resolution, pronoun/anaphora resolution, and conversational state reasoning for DADUS."""
import re
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta

from app.agent.state import AgentSessionState
from app.database.database import get_db_context
from app.database.models import AuditLog, TaskItem
from app.memory.memory import memory_store

logger = logging.getLogger("DADUS.ContextResolver")

class ContextResolver:
    """
    Resolves contextual references, anaphora ('open it', 'close that', 'make it louder'),
    repetition ('do the same thing again'), and meta-conversational queries.
    """

    @classmethod
    def resolve_contextual_reference(
        cls,
        text: str,
        session: AgentSessionState
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        Attempts to resolve pronoun references or repetitive instructions using active session state.
        Returns (tool_name, tool_arguments, direct_response).
        """
        clean = text.strip().rstrip(".?!")
        lower = clean.lower()

        # 1. Repetition: "do the same thing again", "repeat that", "do it again", "once more"
        if re.search(r"\b(?:do\s+(?:the\s+same(?:\s+thing)?|it)\s+again|repeat\s+that|do\s+it\s+once\s+more|once\s+again)\b", lower):
            if session.last_tool_name:
                logger.info(f"Contextual repetition resolved: re-running {session.last_tool_name}")
                return session.last_tool_name, dict(session.last_tool_args or {}), None
            return None, None, "Boss, there is no previous action to repeat yet in this session."

        # 2. Relative Volume Pronouns: "make it louder", "turn it down", "turn it up", "a bit louder"
        if re.search(r"\b(?:make\s+it|turn\s+it|a\s+bit|a\s+little)\s+(?:louder|higher|up)\b", lower):
            return "adjust_volume", {"delta": 15, "direction": "higher"}, None
        if re.search(r"\b(?:make\s+it|turn\s+it|a\s+bit|a\s+little)\s+(?:quieter|lower|down|softer)\b", lower):
            return "adjust_volume", {"delta": -15, "direction": "lower"}, None

        # 3. Application Anaphora: "close it", "close that", "kill that", "quit it"
        if re.search(r"^(?:close|quit|exit|kill|terminate|shut\s+down)\s+(?:it|that|this|the\s+app|the\s+application)$", lower):
            active_app = session.context_entities.get("active_app")
            if active_app:
                logger.info(f"Contextual close resolved: closing '{active_app}'")
                return "close_app", {"app_name": active_app}, None
            return None, None, "Boss, which application would you like me to close?"

        # 4. Application Anaphora: "open it", "launch it", "bring it back", "open that"
        if re.search(r"^(?:open|launch|start|bring\s+up)\s+(?:it|that|this|the\s+app)$", lower):
            active_app = session.context_entities.get("active_app")
            if active_app:
                logger.info(f"Contextual open resolved: opening '{active_app}'")
                return "open_app", {"app_name": active_app}, None
            return None, None, "Boss, which application would you like me to open?"

        # 5. Media Control Pronoun: "pause it", "stop it", "resume it"
        if re.search(r"^(?:pause|freeze)\s+(?:it|the\s+music|the\s+song|playback)$", lower):
            return "pause_music", {}, None
        if re.search(r"^(?:resume|continue|unpause)\s+(?:it|the\s+music|the\s+song|playback)$", lower):
            return "resume_music", {}, None

        # 6. Conversation / Email Thread Anaphora: "open that conversation", "open the thread", "open that email"
        if re.search(r"\bopen\s+(?:that|the|this)\s+(?:conversation|thread|email|message)\b", lower):
            thread_id = session.context_entities.get("active_thread_id")
            return "open_email_thread", {"thread_id": thread_id}, None

        # 7. Music Result Anaphora: "play the second result", "play the second one"
        if re.search(r"\bplay\s+the\s+(?:second|2nd)\s+(?:result|one|song|video)\b", lower):
            active_song = session.context_entities.get("active_song") or "relaxing music"
            return "play_music", {"song": active_song, "result_index": 1}, None

        return None, None, None

    @classmethod
    def resolve_meta_query(cls, text: str, session: AgentSessionState) -> Optional[str]:
        """
        Dynamically answers questions about session discussion history and past logged activities.
        """
        lower = text.lower().strip()

        # Past discussion in current session
        if re.search(r"\b(?:what\s+were\s+we\s+(?:discussing|talking\s+about)|what\s+did\s+we\s+talk\s+about|our\s+earlier\s+conversation|earlier\s+discussion)\b", lower):
            prev_user_msgs = [m.content for m in session.messages[:-1] if m.role == "user"]
            if prev_user_msgs:
                recent_topics = ", ".join([f"'{m}'" for m in prev_user_msgs[-4:]])
                return f"Boss, earlier we were discussing: {recent_topics}."
            return "Boss, in this session we haven't discussed other topics yet."

        # Past activity inquiry (yesterday / previous tasks)
        if re.search(r"\b(?:what\s+did\s+i\s+ask(?:\s+you)?(?:\s+to\s+do)?\s+yesterday|yesterday(?:'s)?\s+(?:tasks|activity|requests)|what\s+i\s+asked\s+yesterday)\b", lower):
            now = datetime.utcnow()
            yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            with get_db_context() as db:
                past_logs = db.query(AuditLog).filter(
                    AuditLog.timestamp >= yesterday_start,
                    AuditLog.timestamp < yesterday_end
                ).all()
                past_tasks = db.query(TaskItem).filter(
                    TaskItem.created_at >= yesterday_start,
                    TaskItem.created_at < yesterday_end
                ).all()

            if past_logs or past_tasks:
                items = [l.user_input for l in past_logs if l.user_input] + [t.title for t in past_tasks if t.title]
                unique_items = list(dict.fromkeys(items))[:5]
                return f"Boss, checking your activity logs from yesterday, you worked on: {', '.join(unique_items)}."
            return "Boss, checking your activity logs from yesterday, you didn't have any pending requests or automated tasks recorded."

        return None

