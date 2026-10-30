"""Persistent memory management for DADUS.
Stores and retrieves user preferences, facts, projects, and identity notes using SQLite.
"""
from typing import Optional, Dict, List, Any, Tuple
import logging
import re
from datetime import datetime
from app.database.database import get_db_context
from app.database.models import MemoryItem

logger = logging.getLogger("DADUS.Memory")

class MemoryStore:
    """Manages persistent structured long-term memories."""

    CATEGORIES = ["preference", "fact", "project", "topic", "identity", "sensitive"]

    def remember(self, key: str, value: str, category: str = "preference") -> Dict[str, Any]:
        """Save or update a memory item."""
        clean_key = key.strip().lower()
        clean_val = value.strip()
        cat = category if category in self.CATEGORIES else "preference"

        with get_db_context() as db:
            item = db.query(MemoryItem).filter(MemoryItem.key == clean_key).first()
            if item:
                item.value = clean_val
                item.category = cat
                item.updated_at = datetime.utcnow()
                logger.info(f"Updated memory [{clean_key}]: {clean_val}")
            else:
                item = MemoryItem(key=clean_key, value=clean_val, category=cat)
                db.add(item)
                logger.info(f"Created memory [{clean_key}]: {clean_val}")
            db.flush()
            return item.to_dict()

    def get(self, key: str) -> Optional[str]:
        """Retrieve memory value by key."""
        clean_key = key.strip().lower()
        with get_db_context() as db:
            item = db.query(MemoryItem).filter(MemoryItem.key == clean_key).first()
            return item.value if item else None

    def forget(self, key: str) -> bool:
        """Remove a memory item by key or fuzzy pattern."""
        clean_key = key.strip().lower()
        with get_db_context() as db:
            item = db.query(MemoryItem).filter(MemoryItem.key == clean_key).first()
            if not item:
                # Try finding by substring match
                item = db.query(MemoryItem).filter(MemoryItem.key.contains(clean_key)).first()
            if item:
                db.delete(item)
                logger.info(f"Deleted memory [{item.key}]")
                return True
            return False

    def list_all(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stored memories, optionally filtered by category."""
        with get_db_context() as db:
            query = db.query(MemoryItem)
            if category:
                query = query.filter(MemoryItem.category == category)
            items = query.order_by(MemoryItem.updated_at.desc()).all()
            return [it.to_dict() for it in items]

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search memories across keys and values."""
        clean_q = query.strip().lower()
        with get_db_context() as db:
            items = db.query(MemoryItem).all()
            matches = []
            for it in items:
                if clean_q in it.key.lower() or clean_q in it.value.lower():
                    matches.append(it.to_dict())
            return matches

    def get_preferred_music_app(self) -> Optional[str]:
        """Helper to get user's preferred music app if stored."""
        for key in ["preferred_music_app", "music_app", "preferred_music_player", "favorite_music_app"]:
            val = self.get(key)
            if val:
                return val
        # Check all memories for mention of preferred music
        with get_db_context() as db:
            items = db.query(MemoryItem).all()
            for it in items:
                k, v = it.key.lower(), it.value.lower()
                if "prefer" in k or "prefer" in v or "music" in k:
                    if "spotify" in v or "spotify" in k:
                        return "Spotify"
                    if "youtube" in v or "youtube" in k:
                        return "YouTube"
        return None

    def get_preferred_browser(self) -> Optional[str]:
        """Helper to get user's preferred web browser if stored."""
        for key in ["preferred_browser", "browser", "default_browser"]:
            val = self.get(key)
            if val:
                return val
        matches = self.search("browser")
        for m in matches:
            v = m["value"].lower()
            if "chrome" in v:
                return "Google Chrome"
            if "edge" in v:
                return "Microsoft Edge"
            if "firefox" in v:
                return "Firefox"
        return None

    def get_preferred_code_editor(self) -> Optional[str]:
        """Helper to get user's preferred coding editor/IDE."""
        for key in ["preferred_editor", "code_editor", "editor", "ide"]:
            val = self.get(key)
            if val:
                return val
        matches = self.search("code") + self.search("editor")
        for m in matches:
            v = m["value"].lower()
            if "vs code" in v or "vscode" in v or "visual studio code" in v:
                return "Visual Studio Code"
            if "cursor" in v:
                return "Cursor"
        return "Visual Studio Code"

    def answer_memory_query(self, query: str) -> Optional[str]:
        """
        Synthesizes a natural conversational answer to questions about stored memories.
        Handles:
        - "What music app do I prefer?"
        - "What technologies am I learning?"
        - "What is my preferred browser?"
        - "What do you know about my projects?"
        """
        lower = query.lower()
        if lower.startswith("remember") or "remember that" in lower or "preferred browser is" in lower or lower.startswith("forget"):
            return None

        # Music app preference
        if any(w in lower for w in ["music app", "music player", "prefer music", "music preference", "favorite music"]):
            app = self.get_preferred_music_app()
            if app:
                return f"Boss, you prefer {app}."
            return "Boss, you haven't told me a preferred music app yet."

        # Learning / Technologies
        if any(w in lower for w in ["technologies", "technology", "learning", "programming", "languages"]):
            matches = self.search("learn") + self.search("python") + self.search("tech")
            if matches:
                topics = [m["value"] for m in matches]
                unique_topics = list(dict.fromkeys(topics))
                return f"Boss, according to your stored memories, you are learning {', '.join(unique_topics)}."
            # Also check generic note
            note = self.get("learning") or self.get("technologies_learning")
            if note:
                return f"Boss, you are learning {note}."
            return "Boss, you haven't mentioned what technologies you are learning yet."

        # Browser preference
        if "browser" in lower and any(w in lower for w in ["prefer", "favorite", "default", "what"]):
            b = self.get_preferred_browser()
            if b:
                return f"Boss, your preferred browser is {b}."
            return "Boss, you haven't specified a preferred browser yet."

        # Coding editor
        if any(w in lower for w in ["code editor", "editor", "ide"]):
            ed = self.get_preferred_code_editor()
            return f"Boss, your primary code editor is {ed}."

        # General list of memories
        if any(w in lower for w in ["what do you remember", "what do you know about me", "list my memories", "my memories"]):
            all_mem = self.list_all()
            if not all_mem:
                return "Boss, I don't have any saved memories yet."
            lines = [f"• {m['key']}: {m['value']} ({m['category']})" for m in all_mem[:10]]
            return "Here is what I remember about you, boss:\n" + "\n".join(lines)

        return None

memory_store = MemoryStore()
