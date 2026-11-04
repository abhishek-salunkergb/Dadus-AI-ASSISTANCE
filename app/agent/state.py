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
    context_entities: Dict[str, Any] = Field(default_factory=dict)
    last_tool_name: Optional[str] = None
    last_tool_args: Optional[Dict[str, Any]] = None
    last_tool_result: Optional[Dict[str, Any]] = None

    def add_user_message(self, text: str) -> None:
        self.messages.append(Message(role="user", content=text))

    def add_assistant_message(self, text: str) -> None:
        self.messages.append(Message(role="assistant", content=text))

    def clear_pending(self) -> None:
        self.pending_clarification = None
        self.pending_confirmation_id = None

    def record_tool_action(self, tool_name: str, arguments: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> None:
        """Dynamically tracks recently manipulated entities for contextual pronoun/anaphora resolution."""
        self.last_tool_name = tool_name
        self.last_tool_args = dict(arguments) if arguments else {}
        self.last_tool_result = dict(result) if result else {}

        # Track active application
        app_cand = arguments.get("app_name") or arguments.get("application")
        if not app_cand and result and isinstance(result.get("data"), dict):
            app_cand = result["data"].get("app_name") or result["data"].get("application") or result["data"].get("name")
        if app_cand and isinstance(app_cand, str):
            self.context_entities["active_app"] = app_cand

        # Track active song/media
        song_cand = arguments.get("song") or (result.get("data", {}).get("song") if result and isinstance(result.get("data"), dict) else None)
        if song_cand and isinstance(song_cand, str):
            self.context_entities["active_song"] = song_cand

        # Track active file/path
        file_cand = arguments.get("path") or arguments.get("file_path")
        if file_cand and isinstance(file_cand, str):
            self.context_entities["active_file"] = file_cand

        # Track active software project
        proj_cand = arguments.get("project_name")
        if proj_cand and isinstance(proj_cand, str):
            self.context_entities["active_project"] = proj_cand

        # Track active contact
        contact_cand = arguments.get("contact_name")
        if contact_cand and isinstance(contact_cand, str):
            self.context_entities["active_contact"] = contact_cand

        # Track active email thread
        thread_cand = arguments.get("thread_id")
        if not thread_cand and result and isinstance(result.get("data"), dict):
            latest_t = result["data"].get("latest_thread")
            if isinstance(latest_t, dict):
                thread_cand = latest_t.get("thread_id")
        if thread_cand and isinstance(thread_cand, str):
            self.context_entities["active_thread_id"] = thread_cand
