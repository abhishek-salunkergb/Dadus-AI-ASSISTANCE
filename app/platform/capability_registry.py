"""Application Capability Registry for DADUS.
Indexes available applications and integration channels by functional capability
rather than merely relying on application names.
"""
import logging
from typing import Dict, List, Optional, Any
from app.platform.base import BasePlatformAdapter

logger = logging.getLogger("DADUS.CapabilityRegistry")


class CapabilityRegistry:
    """Central registry linking user intents to discovered application capabilities."""

    def __init__(self, platform_adapter: BasePlatformAdapter):
        self.platform_adapter = platform_adapter
        self._capabilities: Dict[str, List[Dict[str, Any]]] = {}
        self.refresh()

    def refresh(self) -> None:
        """Query platform adapter to refresh discovered applications."""
        try:
            self._capabilities = self.platform_adapter.discover_capability_applications()
            logger.info(f"Capability registry refreshed: {len(self._capabilities)} categories indexed.")
        except Exception as ex:
            logger.error(f"Error refreshing capability registry: {ex}")
            self._capabilities = {}

    def get_best_provider(self, capability: str) -> Optional[Dict[str, Any]]:
        """Returns the highest priority available application for a given capability."""
        providers = self._capabilities.get(capability.lower(), [])
        available = [p for p in providers if p.get("is_available", False)]
        if not available:
            return None
        available.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return available[0]

    def get_all_providers(self, capability: str) -> List[Dict[str, Any]]:
        """Returns all registered providers for a specific capability."""
        return self._capabilities.get(capability.lower(), [])

    def list_all_capabilities(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns the complete map of indexed capabilities and apps."""
        return self._capabilities
