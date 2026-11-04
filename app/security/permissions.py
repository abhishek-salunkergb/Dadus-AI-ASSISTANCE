"""Security and permission management for DADUS.
Enforces strict 3-tier risk permission model, persistent granular capability controls,
and prompt-injection/OS-bypass resistance.
"""
from enum import Enum
from typing import Dict, Any, Tuple, Optional
from pathlib import Path
import json
import re
import logging
from app.config.settings import settings

logger = logging.getLogger("DADUS.Security")

class PermissionLevel(str, Enum):
    """Permission risk levels for tools and operations."""
    SAFE = "SAFE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    RESTRICTED = "RESTRICTED"


class Capability(str, Enum):
    """Granular user-configurable capabilities governing DADUS device and OS features."""
    MICROPHONE_WAKEWORD = "microphone_wakeword"
    APP_CONTROL = "app_control"
    BROWSER_AUTOMATION = "browser_automation"
    FILE_ACCESS = "file_access"
    FILE_DELETION = "file_deletion"
    SYSTEM_CONTROLS = "system_controls"
    SCREEN_CAPTURE = "screen_capture"
    DEVICE_LOCK = "device_lock"
    BACKGROUND_OPERATION = "background_operation"
    STARTUP_BOOT = "startup_boot"
    EXTERNAL_SERVICES = "external_services"
    CONTACTS_ACCESS = "contacts_access"
    PHONE_CALLING = "phone_calling"
    CAMERA_ACCESS = "camera_access"
    PHOTOS_GALLERY = "photos_gallery"
    GMAIL_ACCOUNT = "gmail_account"
    CALENDAR_ACCESS = "calendar_access"


CAPABILITY_METADATA: Dict[str, Dict[str, Any]] = {
    Capability.DEVICE_LOCK.value: {
        "name": "Device Lock",
        "description": "Allows DADUS to lock the computer workstation when requested by voice",
        "category": "Security & Device Control",
        "default": True,
    },
    Capability.APP_CONTROL.value: {
        "name": "Application Control",
        "description": "Allows DADUS to discover, launch, focus, and close installed applications",
        "category": "Application Management",
        "default": True,
    },
    Capability.BROWSER_AUTOMATION.value: {
        "name": "Browser Automation",
        "description": "Allows DADUS to open URLs and perform Google web searches",
        "category": "Web & Browser",
        "default": True,
    },
    Capability.SYSTEM_CONTROLS.value: {
        "name": "System Controls",
        "description": "Allows DADUS to adjust audio volume, mute, power states, and Bluetooth",
        "category": "Hardware & System",
        "default": True,
    },
    Capability.SCREEN_CAPTURE.value: {
        "name": "Screen Capture",
        "description": "Allows DADUS to take desktop screenshots when commanded",
        "category": "Hardware & System",
        "default": True,
    },
    Capability.FILE_ACCESS.value: {
        "name": "File Access",
        "description": "Allows DADUS to search, list, and read documents in user folders",
        "category": "File Management",
        "default": True,
    },
    Capability.FILE_DELETION.value: {
        "name": "File Deletion",
        "description": "Allows DADUS to clean logs or delete files (always requires confirmation)",
        "category": "File Management",
        "default": True,
    },
    Capability.EXTERNAL_SERVICES.value: {
        "name": "External Service Integrations",
        "description": "Allows DADUS to connect to Gmail and external APIs",
        "category": "Integrations",
        "default": True,
    },
    Capability.MICROPHONE_WAKEWORD.value: {
        "name": "Microphone & Wake-Word",
        "description": "Enables microphone capture and always-on 'Hey Dadus' detection",
        "category": "Voice & Hardware",
        "default": True,
    },
    Capability.BACKGROUND_OPERATION.value: {
        "name": "Background Operation",
        "description": "Keeps DADUS running in the Windows system tray with global hotkeys",
        "category": "Windows Lifecycle",
        "default": True,
    },
    Capability.STARTUP_BOOT.value: {
        "name": "Launch on Windows Startup",
        "description": "Automatically starts DADUS when logging into Windows",
        "category": "Windows Lifecycle",
        "default": False,
    },
    Capability.CONTACTS_ACCESS.value: {
        "name": "Contacts Access",
        "description": "Allows DADUS to view, search, and manage address book contacts",
        "category": "Personal Data & Contacts",
        "default": True,
    },
    Capability.PHONE_CALLING.value: {
        "name": "Phone & Calling",
        "description": "Allows DADUS to initiate voice phone calls via system dialer",
        "category": "Personal Data & Contacts",
        "default": True,
    },
    Capability.CAMERA_ACCESS.value: {
        "name": "Camera Access",
        "description": "Allows DADUS to access the camera hardware and record video",
        "category": "Hardware & Media",
        "default": True,
    },
    Capability.PHOTOS_GALLERY.value: {
        "name": "Photos & Gallery",
        "description": "Allows DADUS to access device pictures and recent photo libraries",
        "category": "Hardware & Media",
        "default": True,
    },
    Capability.GMAIL_ACCOUNT.value: {
        "name": "Gmail Account Access",
        "description": "Allows DADUS to read, search, and draft emails from authorized Gmail",
        "category": "External Accounts",
        "default": True,
    },
    Capability.CALENDAR_ACCESS.value: {
        "name": "Calendar & Schedule",
        "description": "Allows DADUS to view and schedule calendar events",
        "category": "Productivity",
        "default": True,
    },
}

TOOL_TO_CAPABILITY: Dict[str, str] = {
    # Device lock
    "lock_device": Capability.DEVICE_LOCK.value,
    
    # App control
    "open_app": Capability.APP_CONTROL.value,
    "close_app": Capability.APP_CONTROL.value,
    "list_installed_apps": Capability.APP_CONTROL.value,
    
    # Browser automation
    "open_browser": Capability.BROWSER_AUTOMATION.value,
    "search_web": Capability.BROWSER_AUTOMATION.value,
    "search_youtube": Capability.BROWSER_AUTOMATION.value,
    
    # File access
    "search_files": Capability.FILE_ACCESS.value,
    "read_file": Capability.FILE_ACCESS.value,
    "list_files": Capability.FILE_ACCESS.value,
    
    # File deletion (also requires confirmation)
    "delete_file_or_folder": Capability.FILE_DELETION.value,
    "remove_directory": Capability.FILE_DELETION.value,
    "clean_logs": Capability.FILE_DELETION.value,
    
    # System controls
    "set_volume": Capability.SYSTEM_CONTROLS.value,
    "mute_volume": Capability.SYSTEM_CONTROLS.value,
    "adjust_volume": Capability.SYSTEM_CONTROLS.value,
    "shutdown_system": Capability.SYSTEM_CONTROLS.value,
    "restart_system": Capability.SYSTEM_CONTROLS.value,
    "toggle_bluetooth": Capability.SYSTEM_CONTROLS.value,
    
    # Screenshots
    "take_screenshot": Capability.SCREEN_CAPTURE.value,
    
    # Camera and Gallery
    "open_camera": Capability.CAMERA_ACCESS.value,
    "record_video": Capability.CAMERA_ACCESS.value,
    "open_gallery": Capability.PHOTOS_GALLERY.value,
    "show_recent_photos": Capability.PHOTOS_GALLERY.value,

    # Contacts & Calling
    "call_contact": Capability.PHONE_CALLING.value,
    "message_contact": Capability.CONTACTS_ACCESS.value,
    "list_contacts": Capability.CONTACTS_ACCESS.value,
    "add_contact": Capability.CONTACTS_ACCESS.value,
    "delete_contact": Capability.CONTACTS_ACCESS.value,
    "import_contacts": Capability.CONTACTS_ACCESS.value,

    # Gmail Account vs Browser
    "find_recruiter_emails": Capability.GMAIL_ACCOUNT.value,
    "read_latest_email": Capability.GMAIL_ACCOUNT.value,
    "draft_email": Capability.GMAIL_ACCOUNT.value,
    "send_email": Capability.GMAIL_ACCOUNT.value,
    "open_email_thread": Capability.BROWSER_AUTOMATION.value,
    "open_gmail": Capability.BROWSER_AUTOMATION.value,

    # Calendar & Schedule
    "get_today_schedule": Capability.CALENDAR_ACCESS.value,
    "create_schedule_item": Capability.CALENDAR_ACCESS.value,
}


class PermissionManager:
    """Manages persistent capability permissions for DADUS features and tools."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or (settings.DATA_DIR / "permissions.json")
        self._permissions: Dict[str, bool] = {}
        self._load_permissions()

    def _load_permissions(self) -> None:
        """Loads permissions from disk or sets defaults."""
        defaults = {cap: meta["default"] for cap, meta in CAPABILITY_METADATA.items()}
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception as ex:
                logger.warning(f"Could not load permissions from {self.storage_path}: {ex}")

        # Sync startup_boot with autostart manager if available
        try:
            from app.system.autostart import autostart_manager
            defaults[Capability.STARTUP_BOOT.value] = autostart_manager.is_autostart_enabled()
        except Exception:
            pass

        self._permissions = defaults

    def save_permissions(self) -> None:
        """Persists permissions to disk."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._permissions, f, indent=2)
        except Exception as ex:
            logger.error(f"Failed to save permissions to {self.storage_path}: {ex}")

    def is_permitted(self, capability: str) -> bool:
        """Check if a specific capability permission is enabled."""
        cap_key = capability.value if isinstance(capability, Capability) else capability
        if cap_key == Capability.STARTUP_BOOT.value:
            try:
                from app.system.autostart import autostart_manager
                return autostart_manager.is_autostart_enabled()
            except Exception:
                pass
        return self._permissions.get(cap_key, True)

    def set_permission(self, capability: str, enabled: bool) -> bool:
        """Set a capability permission and update underlying system components."""
        cap_key = capability.value if isinstance(capability, Capability) else capability
        if cap_key not in CAPABILITY_METADATA:
            logger.warning(f"Unknown capability: {cap_key}")
            return False

        self._permissions[cap_key] = bool(enabled)

        # Trigger side effects for system-level settings
        if cap_key == Capability.STARTUP_BOOT.value:
            try:
                from app.system.autostart import autostart_manager
                if enabled:
                    autostart_manager.enable_autostart()
                else:
                    autostart_manager.disable_autostart()
            except Exception as ex:
                logger.error(f"Failed to update Windows autostart: {ex}")

        self.save_permissions()
        logger.info(f"Updated capability permission '{cap_key}' = {enabled}")
        return True

    def get_all_permissions(self) -> Dict[str, Dict[str, Any]]:
        """Return all permissions with metadata for UI presentation."""
        # Ensure latest startup_boot state
        try:
            from app.system.autostart import autostart_manager
            self._permissions[Capability.STARTUP_BOOT.value] = autostart_manager.is_autostart_enabled()
        except Exception:
            pass

        result = {}
        for cap, meta in CAPABILITY_METADATA.items():
            result[cap] = {
                "key": cap,
                "name": meta["name"],
                "description": meta["description"],
                "category": meta["category"],
                "enabled": self.is_permitted(cap)
            }
        return result

    def check_tool_capability(self, tool_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validates if the tool's required capability is currently permitted.
        Returns (True, None) if permitted, or (False, rejection_reason) if disabled.
        """
        cap = TOOL_TO_CAPABILITY.get(tool_name)
        if not cap:
            return True, None

        if not self.is_permitted(cap):
            meta = CAPABILITY_METADATA.get(cap, {})
            name = meta.get("name", cap)
            if cap == Capability.DEVICE_LOCK.value:
                return False, (
                    "Boss, the Device Lock permission is currently disabled in your DADUS settings. "
                    "Please enable Device Lock in settings to allow me to lock your computer."
                )
            return False, (
                f"Boss, the {name} permission is currently disabled in your DADUS settings. "
                f"Please enable {name} in settings to allow me to perform this action."
            )

        return True, None


permission_manager = PermissionManager()


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

UNLOCK_ATTEMPT_PATTERNS = [
    r"\b(?:unlock|un-lock)\s+(?:my\s+|the\s+)?(?:computer|pc|device|screen|workstation|windows)\b",
    r"\b(?:bypass|skip|disable)\s+(?:the\s+)?(?:lock\s*screen|windows\s*lock|screen\s*lock)\b"
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

        # Check standard restricted credentials and bypass patterns
        for pattern in RESTRICTED_QUERY_PATTERNS:
            if re.search(pattern, lower):
                return True, (
                    "Boss, I cannot access, expose, or manage passwords, "
                    "sensitive credentials, or system security bypasses."
                )

        # Explicit check for voice unlock attempts
        for pattern in UNLOCK_ATTEMPT_PATTERNS:
            if re.search(pattern, lower):
                return True, (
                    "Boss, for your security, DADUS cannot unlock your computer via voice. "
                    "Windows requires hardware biometric (Windows Hello) or password authentication directly on the lock screen."
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
        Enforces granular capability permissions and risk levels.
        """
        # 1. Granular user capability permission check (e.g. Device Lock toggle in UI)
        is_cap_allowed, cap_reason = permission_manager.check_tool_capability(tool_name)
        if not is_cap_allowed:
            return PermissionLevel.RESTRICTED, cap_reason

        # 2. If tool is natively RESTRICTED, block immediately
        if base_level == PermissionLevel.RESTRICTED:
            return PermissionLevel.RESTRICTED, "This tool is permanently restricted for safety."

        # 3. Scan all string arguments for restricted credential requests or unlock bypasses
        for key, val in arguments.items():
            if isinstance(val, str):
                is_restricted, reason = SecurityInspector.is_query_restricted(val)
                if is_restricted:
                    return PermissionLevel.RESTRICTED, reason

        # 4. Extra checks for file deletions
        if tool_name in ["delete_file_or_folder", "remove_directory"]:
            target_path = str(arguments.get("path", "")).lower()
            # Protect Windows system folders permanently
            critical_paths = ["c:\\windows", "c:\\program files", "c:\\program files (x86)", "system32"]
            if any(crit in target_path for crit in critical_paths):
                return PermissionLevel.RESTRICTED, "Boss, deleting system files or OS directories is forbidden."
            return PermissionLevel.CONFIRMATION_REQUIRED, "Deletion of files or folders requires your explicit confirmation."

        # 5. Extra checks for system power operations
        if tool_name in ["shutdown_system", "restart_system"]:
            return PermissionLevel.CONFIRMATION_REQUIRED, "Shutting down or restarting your computer requires confirmation."

        return base_level, None
