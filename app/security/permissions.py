"""Security and permission management for DADUS.
Enforces strict 3-tier permission model and prompt-injection resistance.
"""
from enum import Enum
from typing import Dict, Any, Tuple, Optional
import re
import logging

logger = logging.getLogger("DADUS.Security")

class PermissionLevel(str, Enum):
    """Permission levels for tools and operations."""
    SAFE = "SAFE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    RESTRICTED = "RESTRICTED"

# Blocklist of patterns representing restricted secrets and credential access
RESTRICTED_QUERY_PATTERNS = [
    r"\bpassword\b",
    r"\bpasswords\b",
    r"\bbank\b",
    r"\bbanking\b",
    r"\bcredit\s*card\b",
    r"\bapi[_\s-]?key\b",
    r"\bsecret[_\s-]?key\b",
    r"\bauth[_\s-]?token\b",
    r"\bprivate[_\s-]?key\b",
    r"\bcredential\b",
    r"\bcredentials\b",
    r"\bbypass\s+(auth|security|windows|lock)\b",
    r"\bdisable\s+(defender|antivirus|firewall)\b"
]

SENSITIVE_LOG_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+"), "Bearer [REDACTED]"),
    (re.compile(r"api[_-]?key['\":\s=]+([A-Za-z0-9_\-]{8,})", re.IGNORECASE), "api_key=[REDACTED]"),
    (re.compile(r"password['\":\s=]+([^,\s&]+)", re.IGNORECASE), "password=[REDACTED]"),
]

class SecurityInspector:
    """Evaluates requested actions and arguments against security boundaries."""

    @staticmethod
    def is_query_restricted(query: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a user query or tool argument is requesting restricted data
        such as passwords, banking credentials, or OS bypasses.
        """
        lower = query.lower()
        for pattern in RESTRICTED_QUERY_PATTERNS:
            if re.search(pattern, lower):
                return True, (
                    "Boss, I cannot access, expose, or manage passwords, "
                    "banking credentials, or system security bypasses."
                )
        return False, None

    @staticmethod
    def sanitize_log_message(message: str) -> str:
        """Mask out sensitive secrets, tokens, or passwords from logs."""
        sanitized = message
        for pattern, replacement in SENSITIVE_LOG_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    @staticmethod
    def evaluate_tool_permission(
        tool_name: str,
        base_level: PermissionLevel,
        arguments: Dict[str, Any]
    ) -> Tuple[PermissionLevel, Optional[str]]:
        """
        Evaluate effective permission level for a given tool and arguments.
        Enforces code-level guardrails regardless of LLM assertions.
        """
        # If tool is natively RESTRICTED, block immediately
        if base_level == PermissionLevel.RESTRICTED:
            return PermissionLevel.RESTRICTED, "This tool is permanently restricted for safety."

        # Scan all string arguments for restricted credential requests
        for key, val in arguments.items():
            if isinstance(val, str):
                is_restricted, reason = SecurityInspector.is_query_restricted(val)
                if is_restricted:
                    return PermissionLevel.RESTRICTED, reason

        # Extra checks for file deletions
        if tool_name in ["delete_file_or_folder", "remove_directory"]:
            target_path = str(arguments.get("path", "")).lower()
            # Protect Windows system folders permanently
            critical_paths = ["c:\\windows", "c:\\program files", "c:\\program files (x86)", "system32"]
            if any(crit in target_path for crit in critical_paths):
                return PermissionLevel.RESTRICTED, "Boss, deleting system files or OS directories is forbidden."
            return PermissionLevel.CONFIRMATION_REQUIRED, "Deletion of files or folders requires your explicit confirmation."

        # Extra checks for system power operations
        if tool_name in ["shutdown_system", "restart_system"]:
            return PermissionLevel.CONFIRMATION_REQUIRED, "Shutting down or restarting your computer requires confirmation."

        return base_level, None
