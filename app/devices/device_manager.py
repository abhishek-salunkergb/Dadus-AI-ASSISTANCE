"""Registry and capability management for connected client devices."""
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
import json
import secrets
import logging
from pydantic import BaseModel, Field

from app.database.database import get_db_context
from app.database.models import PairedDevice

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
    """Manages active and persistent devices connected to DADUS personal assistant hub."""

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
        ), persist=False)
        self._load_paired_devices_from_db()

    def _load_paired_devices_from_db(self) -> None:
        """Loads persistently paired devices from database on system startup."""
        try:
            with get_db_context() as db:
                rows = db.query(PairedDevice).all()
                for r in rows:
                    try:
                        caps = [DeviceCapability(c) for c in json.loads(r.capabilities_json or "[]")]
                        dev_type = DeviceType(r.device_type)
                        dev = ConnectedDevice(
                            device_id=r.device_id,
                            name=r.name,
                            device_type=dev_type,
                            capabilities=caps,
                            registered_at=r.created_at or datetime.utcnow(),
                            last_active=r.last_active or datetime.utcnow(),
                            ip_address=r.ip_address,
                            auth_token=r.auth_token
                        )
                        self._devices[dev.device_id] = dev
                    except Exception as ex:
                        logger.debug(f"Could not load paired device [{r.device_id}]: {ex}")
        except Exception as ex:
            logger.debug(f"Device database query skipped: {ex}")

    def register_device(self, device: ConnectedDevice, persist: bool = True) -> ConnectedDevice:
        """Register or update a connected client device with persistent database synchronization."""
        device.last_active = datetime.utcnow()
        self._devices[device.device_id] = device

        if persist:
            try:
                with get_db_context() as db:
                    existing = db.query(PairedDevice).filter(PairedDevice.device_id == device.device_id).first()
                    caps_json = json.dumps([c.value for c in device.capabilities])
                    if existing:
                        existing.name = device.name
                        existing.device_type = device.device_type.value
                        existing.capabilities_json = caps_json
                        existing.auth_token = device.auth_token
                        existing.ip_address = device.ip_address
                        existing.last_active = device.last_active
                    else:
                        new_dev = PairedDevice(
                            device_id=device.device_id,
                            name=device.name,
                            device_type=device.device_type.value,
                            capabilities_json=caps_json,
                            auth_token=device.auth_token,
                            ip_address=device.ip_address,
                            created_at=device.registered_at,
                            last_active=device.last_active
                        )
                        db.add(new_dev)
                    db.flush()
            except Exception as ex:
                logger.debug(f"Error persisting device [{device.device_id}]: {ex}")

        logger.info(f"Registered device [{device.device_id}]: {device.name} ({device.device_type.value})")
        return device

    def pair_new_device(
        self,
        name: str,
        device_type: DeviceType,
        capabilities: Optional[List[DeviceCapability]] = None,
        ip_address: Optional[str] = None
    ) -> Tuple[ConnectedDevice, str]:
        """Pairs a new client device and generates a cryptographically secure authentication token."""
        raw_token = secrets.token_urlsafe(32)
        dev_id = f"dev_{secrets.token_hex(6)}"
        caps = capabilities or []

        dev = ConnectedDevice(
            device_id=dev_id,
            name=name,
            device_type=device_type,
            capabilities=caps,
            auth_token=raw_token,
            ip_address=ip_address
        )
        self.register_device(dev, persist=True)
        return dev, raw_token

    def authenticate_device(self, device_id: str, auth_token: str) -> bool:
        """Validates incoming token against stored cryptographic digest."""
        dev = self.get_device(device_id)
        if not dev or not dev.auth_token:
            return False
        if secrets.compare_digest(dev.auth_token, auth_token):
            self.update_activity(device_id)
            return True
        return False

    def get_device(self, device_id: str) -> Optional[ConnectedDevice]:
        return self._devices.get(device_id)

    def list_devices(self) -> List[ConnectedDevice]:
        return list(self._devices.values())

    def update_activity(self, device_id: str) -> None:
        if device_id in self._devices:
            self._devices[device_id].last_active = datetime.utcnow()

    def can_device_execute_tool(self, device_id: Optional[str], tool_name: str) -> bool:
        """Check if target device possesses required hardware/OS capabilities."""
        if not device_id or device_id == "host_windows_pc":
            return True

        dev = self.get_device(device_id)
        if not dev:
            logger.warning(f"Device capability check failed: Unregistered device [{device_id}] attempted to call '{tool_name}'")
            return False

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
