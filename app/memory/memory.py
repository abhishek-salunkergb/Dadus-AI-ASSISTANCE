"""Persistent memory management for DADUS.
Stores and retrieves user preferences, facts, and identity notes using SQLite.
"""
from typing import Optional, Dict, List, Any
import logging
from datetime import datetime
from app.database.database import get_db_context
from app.database.models import MemoryItem

logger = logging.getLogger("DADUS.Memory")

class MemoryStore:
    """Manages persistent structured memories."""

    def remember(self, key: str, value: str, category: str = "preference") -> Dict[str, Any]:
        """Save or update a memory item."""
        clean_key = key.strip().lower()
        clean_val = value.strip()
        with get_db_context() as db:
            item = db.query(MemoryItem).filter(MemoryItem.key == clean_key).first()
            if item:
                item.value = clean_val
                item.category = category
                item.updated_at = datetime.utcnow()
                logger.info(f"Updated memory [{clean_key}]: {clean_val}")
            else:
                item = MemoryItem(key=clean_key, value=clean_val, category=category)
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

memory_store = MemoryStore()
