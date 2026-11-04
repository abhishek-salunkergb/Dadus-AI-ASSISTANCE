"""Base platform adapter and device abstraction for DADUS.
Defines unified hardware, operating system, and capability contracts
without assuming desktop or mobile platforms behave identically.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class DeviceInfo:
    """Encapsulates the actual operating system, hardware, and account state of the device."""
    os_name: str
    os_version: str
    platform_release: str
    architecture: str
    device_type: str  # "Desktop / Laptop", "Mobile / Tablet", "Server / Headless"
    hostname: str
    cpu_count: int
    memory_total_gb: float
    has_camera: bool
    camera_name: Optional[str]
    has_microphone: bool
    microphone_count: int
    has_battery: bool
    battery_percent: Optional[int]
    is_charging: Optional[bool]
    has_bluetooth: bool
    bluetooth_device_name: Optional[str]
    connected_accounts: Dict[str, bool] = field(default_factory=dict)
    supported_capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BasePlatformAdapter(ABC):
    """Abstract interface for operating-system and hardware integrations."""

    @abstractmethod
    def get_device_info(self) -> DeviceInfo:
        """Inspect and return current device specifications and hardware status."""
        pass

    @abstractmethod
    def discover_capability_applications(self) -> Dict[str, List[Dict[str, Any]]]:
        """Discover registered handlers and applications mapped by capability category."""
        pass

    @abstractmethod
    def launch_camera(self, mode: str = "photo") -> bool:
        """Launch the system camera application in photo or video mode."""
        pass

    @abstractmethod
    def launch_gallery(self, target_image: Optional[Path] = None) -> bool:
        """Launch the system photos/gallery application or open an image in default viewer."""
        pass

    @abstractmethod
    def get_recent_photos(self, limit: int = 5) -> List[Path]:
        """Retrieve authentic recent photographs from device storage."""
        pass

    @abstractmethod
    def dial_phone(self, phone_number: str) -> bool:
        """Initiate dialing of a phone number through the platform's dialer or Phone Link."""
        pass

    @abstractmethod
    def lock_workstation(self) -> bool:
        """Lock the operating system screen."""
        pass
