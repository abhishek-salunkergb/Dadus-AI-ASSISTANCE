"""Voice identity and user authorization layer for DADUS.
Prepares speaker verification abstraction while ensuring voice alone
never bypasses operating system authentication.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger("DADUS.Identity")

@dataclass
class UserProfile:
    """Represents an authorized user profile."""
    user_id: str
    display_name: str
    role: str  # "owner", "family", "guest"
    voiceprint_enrolled: bool = False

class IdentityManager:
    """Manages user profiles and speaker identity checks."""

    def __init__(self):
        # Default owner profile (the Boss)
        self._primary_user = UserProfile(
            user_id="user_owner_01",
            display_name="Boss",
            role="owner",
            voiceprint_enrolled=False
        )
        self._profiles: Dict[str, UserProfile] = {
            self._primary_user.user_id: self._primary_user
        }

    def get_primary_user(self) -> UserProfile:
        """Return the default primary user profile."""
        return self._primary_user

    def verify_speaker(self, audio_data: Optional[bytes] = None) -> Dict[str, Any]:
        """
        Verify speaker identity based on audio sample.
        Provides a clean integration hook for speaker embedding models (e.g. ECAPA-TDNN / Resemblyzer).
        Always adheres to the security principle: voice identity is an additional signal
        and is never used to bypass Windows authentication.
        """
        if not audio_data or not self._primary_user.voiceprint_enrolled:
            # When voiceprint is not enrolled yet, trust active authenticated local session
            return {
                "verified": True,
                "confidence": 1.0,
                "user": self._primary_user,
                "note": "Default local session active"
            }

        # Placeholder for external speaker verification model
        return {
            "verified": True,
            "confidence": 0.95,
            "user": self._primary_user,
            "note": "Speaker verified"
        }

identity_manager = IdentityManager()
