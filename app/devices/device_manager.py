"""Connected device registry and device-specific capability router for DADUS.
Prepares the architecture for Android mobile clients, multiple connected devices,
and distributed tool execution across devices.
"""
from enum import Enum
from typing import Dict, List, Optional, Set
from datetime import datetime
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger("DADUS.Devices")

class DeviceType(str, Enum):
    WINDOWS_DESKTOP = "windows_desktop"
    ANDROID_MOBILE = "android_mobile"
    WEB_CLIENT = "web_client"
    MCP_CLIENT = "mcp_client"

class DeviceCapability(str, Enum):
    AUDIO_PLAYBACK = "audio_playback"
    MICROPHONE = "microphone"
    SCREEN_CAPTURE = "screen_capture"
    LOCAL_APP_EXECUTION = "local_app_execution"
    HARDWARE_MEDIA_KEYS = "hardware_media_keys"
    SYSTEM_NOTIFICATIONS = "system_notifications"

class ConnectedDevice(BaseModel):
    device_id: str
    name: str
    device_type: DeviceType
    capabilities: List[DeviceCapability] = Field(default_factory=list)
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    auth_token: Optional[str] = None

class DeviceManager:
    """Manages active devices connected to DADUS personal assistant hub."""

    def __init__(self):
        self._devices: Dict[str, ConnectedDevice] = {}
        # Register host Windows device by default
        self.register_device(ConnectedDevice(
            device_id="host_windows_pc",
            name="Host Windows PC",
            device_type=DeviceType.WINDOWS_DESKTOP,
            capabilities=[
                DeviceCapability.AUDIO_PLAYBACK,
                DeviceCapability.MICROPHONE,
                DeviceCapability.SCREEN_CAPTURE,
                DeviceCapability.LOCAL_APP_EXECUTION,
                DeviceCapability.HARDWARE_MEDIA_KEYS,
                DeviceCapability.SYSTEM_NOTIFICATIONS
            ]
        ))

    def register_device(self, device: ConnectedDevice) -> ConnectedDevice:
        """Register or update a connected client device."""
        device.last_active = datetime.utcnow()
        self._devices[device.device_id] = device
        logger.info(f"Registered device [{device.device_id}]: {device.name} ({device.device_type.value})")
        return device

    def get_device(self, device_id: str) -> Optional[ConnectedDevice]:
        return self._devices.get(device_id)

    def list_devices(self) -> List[ConnectedDevice]:
        return list(self._devices.values())

    def update_activity(self, device_id: str) -> None:
        if device_id in self._devices:
            self._devices[device_id].last_active = datetime.utcnow()

    def can_device_execute_tool(self, device_id: str, tool_name: str) -> bool:
        """Check if target device possesses required hardware/OS capabilities."""
        dev = self.get_device(device_id)
        if not dev:
            return True  # Fallback to host desktop

        desktop_only_tools = {
            "take_screenshot": DeviceCapability.SCREEN_CAPTURE,
            "open_app": DeviceCapability.LOCAL_APP_EXECUTION,
            "close_app": DeviceCapability.LOCAL_APP_EXECUTION,
            "pause_music": DeviceCapability.HARDWARE_MEDIA_KEYS,
            "resume_music": DeviceCapability.HARDWARE_MEDIA_KEYS,
            "skip_music_track": DeviceCapability.HARDWARE_MEDIA_KEYS,
            "set_volume": DeviceCapability.AUDIO_PLAYBACK,
            "adjust_volume": DeviceCapability.AUDIO_PLAYBACK
        }

        if tool_name in desktop_only_tools:
            required_cap = desktop_only_tools[tool_name]
            return required_cap in dev.capabilities

        return True

device_manager = DeviceManager()
