"""Dynamic conversational reasoning and contextual advice synthesizer for DADUS.
Provides rich, non-hardcoded conversational intelligence using active memories, tasks, and system context.
"""
import re
import logging
from typing import Optional, Dict, Any, Tuple
from app.memory.memory import memory_store
from app.database.database import get_db_context
from app.database.models import TaskItem

logger = logging.getLogger("DADUS.Conversational")

class ConversationalSynthesizer:
    """
    Synthesizes natural, context-aware responses for open-ended conversational turns,
    advice, learning guidance, and interview preparation.
    """

    @classmethod
    def synthesize_response(cls, text: str) -> Optional[str]:
        """
        Evaluates open-ended conversational requests and synthesizes a natural response.
        Returns response string if applicable, or None to fall through to tool execution.
        """
        lower = text.lower().strip()

        # 1. Boredom / suggestion / engagement requests
        if re.search(r"\b(?:bored|feeling\s+bored|suggest\s+something|what\s+should\s+i\s+do|nothing\s+to\s+do)\b", lower):
            tech = memory_store.get("learning") or "Python"
            pref_music = memory_store.get_preferred_music_app() or "Spotify"
            
            with get_db_context() as db:
                pending_count = db.query(TaskItem).filter(TaskItem.status == "pending").count()

            task_phrase = f", or review your {pending_count} pending tasks" if pending_count > 0 else ", or run through your tasks"
            return (
                f"Boss, if you're looking for something engaging: we could make progress on your "
                f"{tech} project, play some relaxing music on {pref_music}{task_phrase}. "
                f"What sounds good?"
            )

        # 2. Career / Interview coaching requests
        if re.search(r"\b(?:interview|job\s+interview|mock\s+interview|prepare\s+for\s+an\s+interview)\b", lower):
            tech = memory_store.get("learning") or "Python"
            return (
                f"Boss, congratulations on the interview! Let's get you prepared. Would you like to "
                f"practice technical questions on {tech} and system design, run through a mock behavioral Q&A, "
                f"or review your project highlights?"
            )

        # 3. Dynamic memory / preference Q&A
        mem_answer = memory_store.answer_memory_query(text)
        if mem_answer:
            return mem_answer

        return None
