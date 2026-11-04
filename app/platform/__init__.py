"""Platform adaptation and capability registry package for DADUS."""
import sys
from app.platform.base import BasePlatformAdapter, DeviceInfo
from app.platform.capability_registry import CapabilityRegistry


def get_platform_adapter() -> BasePlatformAdapter:
    """Factory creating the appropriate platform adapter for current OS."""
    if sys.platform == "win32":
        from app.platform.windows import WindowsPlatformAdapter
        return WindowsPlatformAdapter()
    elif "android" in sys.platform.lower():
        from app.platform.android import AndroidPlatformAdapter
        return AndroidPlatformAdapter()
    else:
        # Default to Windows for desktop workstation environments
        from app.platform.windows import WindowsPlatformAdapter
        return WindowsPlatformAdapter()


platform_adapter: BasePlatformAdapter = get_platform_adapter()
capability_registry: CapabilityRegistry = CapabilityRegistry(platform_adapter)

__all__ = [
    "BasePlatformAdapter",
    "DeviceInfo",
    "CapabilityRegistry",
    "platform_adapter",
    "capability_registry",
    "get_platform_adapter"
]
