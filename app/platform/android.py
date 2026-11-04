"""Android/Linux platform adapter stub for DADUS.
Maintains clean separation of platform contracts without Windows-specific dependencies.
"""
import os
import platform
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.platform.base import BasePlatformAdapter, DeviceInfo

logger = logging.getLogger("DADUS.Platform.Android")


class AndroidPlatformAdapter(BasePlatformAdapter):
    """Platform adapter for Android or mobile Linux environments."""

    def get_device_info(self) -> DeviceInfo:
        return DeviceInfo(
            os_name="Android",
            os_version=platform.version(),
            platform_release=platform.release(),
            architecture=platform.machine(),
            device_type="Mobile / Tablet",
            hostname=platform.node(),
            cpu_count=os.cpu_count() or 1,
            memory_total_gb=4.0,
            has_camera=True,
            camera_name="Android Camera HAL",
            has_microphone=True,
            microphone_count=1,
            has_battery=True,
            battery_percent=85,
            is_charging=False,
            has_bluetooth=True,
            bluetooth_device_name="Android Bluetooth Adapter",
            connected_accounts={"google": True},
            supported_capabilities=[
                "camera_access",
                "photos_gallery",
                "contacts_access",
                "phone_calling",
                "app_control"
            ]
        )

    def discover_capability_applications(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "camera": [{"app_name": "Camera", "integration_type": "android_intent", "identifier": "android.media.action.IMAGE_CAPTURE", "is_available": True, "priority": 100}],
            "calling": [{"app_name": "Dialer", "integration_type": "android_intent", "identifier": "android.intent.action.DIAL", "is_available": True, "priority": 100}],
            "gallery": [{"app_name": "Photos", "integration_type": "android_intent", "identifier": "android.intent.action.VIEW", "is_available": True, "priority": 100}],
            "email": [{"app_name": "Gmail", "integration_type": "native_api", "identifier": "https://gmail.googleapis.com", "is_available": True, "priority": 100}]
        }

    def launch_camera(self, mode: str = "photo") -> bool:
        logger.info(f"Android Intent dispatched: android.media.action.IMAGE_CAPTURE (mode={mode})")
        return True

    def launch_gallery(self, target_image: Optional[Path] = None) -> bool:
        logger.info("Android Intent dispatched: android.intent.action.VIEW (content://media/external/images)")
        return True

    def get_recent_photos(self, limit: int = 5) -> List[Path]:
        return []

    def dial_phone(self, phone_number: str) -> bool:
        logger.info(f"Android Intent dispatched: android.intent.action.DIAL (tel:{phone_number})")
        return True

    def lock_workstation(self) -> bool:
        logger.warning("Device lock on Android requires DevicePolicyManager administrative privileges.")
        return False
