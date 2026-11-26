"""Memory retrieval helpers for injecting context into DADUS prompts."""
from typing import List
from app.memory.memory import memory_store

class MemoryRetriever:
    """Retrieves and formats memories to guide agent decisions."""

    @staticmethod
    def get_context_summary() -> str:
        """Format stored memories into a concise text block for LLM system prompts."""
        memories = [m for m in memory_store.list_all() if m.get("category") != "system_config" and not str(m.get("key", "")).startswith("__")]
        if not memories:
            return "No persistent memories saved yet."

        lines: List[str] = []
        for m in memories:
            lines.append(f"- {m['key']}: {m['value']} ({m['category']})")
        return "\n".join(lines)

    @staticmethod
    def search_relevant_memories(query: str) -> List[str]:
        """Simple keyword retrieval across stored keys and values."""
        query_words = set(query.lower().split())
        memories = [m for m in memory_store.list_all() if m.get("category") != "system_config" and not str(m.get("key", "")).startswith("__")]
        relevant: List[str] = []

        for m in memories:
            content = f"{m['key']} {m['value']}".lower()
            if any(w in content for w in query_words):
                relevant.append(f"{m['key']}: {m['value']}")
        return relevant
