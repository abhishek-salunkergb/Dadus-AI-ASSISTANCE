"""Confirmation workflow manager for sensitive DADUS operations."""
import uuid
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("DADUS.Confirmations")

@dataclass
class PendingAction:
    """Represents a sensitive tool call awaiting explicit user confirmation."""
    id: str
    tool_name: str
    arguments: Dict[str, Any]
    prompt_message: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)
    status: str = "pending"  # pending, confirmed, rejected, expired

class ConfirmationManager:
    """In-memory thread-safe confirmation manager with automatic expiration."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds
        self._pending_actions: Dict[str, PendingAction] = {}
        self._latest_pending_id: Optional[str] = None

    def request_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        prompt_message: str
    ) -> PendingAction:
        """Create and register a pending action needing user approval."""
        self._cleanup_expired()
        action_id = str(uuid.uuid4())[:8]
        action = PendingAction(
            id=action_id,
            tool_name=tool_name,
            arguments=arguments,
            prompt_message=prompt_message,
            created_at=time.time(),
            expires_at=time.time() + self.timeout_seconds
        )
        self._pending_actions[action_id] = action
        self._latest_pending_id = action_id
        logger.info(f"Registered confirmation request [{action_id}] for tool '{tool_name}'")
        return action

    def get_latest_pending(self) -> Optional[PendingAction]:
        """Return the most recently created pending action, if still valid."""
        self._cleanup_expired()
        if self._latest_pending_id and self._latest_pending_id in self._pending_actions:
            action = self._pending_actions[self._latest_pending_id]
            if action.status == "pending":
                return action
        return None

    def get_action(self, action_id: str) -> Optional[PendingAction]:
        """Retrieve action by ID."""
        self._cleanup_expired()
        return self._pending_actions.get(action_id)

    def resolve_action(self, action_id: str, confirmed: bool) -> Optional[PendingAction]:
        """Resolve a pending confirmation."""
        action = self._pending_actions.get(action_id)
        if not action or action.status != "pending":
            return None

        if time.time() > action.expires_at:
            action.status = "expired"
            return None

        action.status = "confirmed" if confirmed else "rejected"
        if self._latest_pending_id == action_id and not confirmed:
            self._latest_pending_id = None
        return action

    def has_pending(self) -> bool:
        """Check if any valid action is awaiting confirmation."""
        return self.get_latest_pending() is not None

    def _cleanup_expired(self) -> None:
        """Purge expired requests."""
        now = time.time()
        for aid, action in list(self._pending_actions.items()):
            if now > action.expires_at and action.status == "pending":
                action.status = "expired"

confirmation_manager = ConfirmationManager()
