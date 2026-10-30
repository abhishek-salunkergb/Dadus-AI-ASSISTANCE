"""Agent state and multi-turn context tracking."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time

class Message(BaseModel):
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)

class PendingClarification(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    clarification_type: str  # e.g., "app_choice"
    options: List[str]
    context_data: Dict[str, Any] = Field(default_factory=dict)

class AgentSessionState(BaseModel):
    """Tracks state across conversation turns."""
    session_id: str
    status: str = "READY"  # READY, LISTENING, UNDERSTANDING, EXECUTING, WAITING_CONFIRMATION, DONE, ERROR
    messages: List[Message] = Field(default_factory=list)
    pending_clarification: Optional[PendingClarification] = None
    pending_confirmation_id: Optional[str] = None

    def add_user_message(self, text: str) -> None:
        self.messages.append(Message(role="user", content=text))

    def add_assistant_message(self, text: str) -> None:
        self.messages.append(Message(role="assistant", content=text))

    def clear_pending(self) -> None:
        self.pending_clarification = None
        self.pending_confirmation_id = None
