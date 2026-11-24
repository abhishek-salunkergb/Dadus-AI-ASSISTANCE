"""Zero-config local network discovery service for DADUS.
Enables mobile companion apps and local devices to auto-discover the DADUS hub
on the same Wi-Fi / local area network without manual IP or port configuration.
"""
import socket
import json
import logging
import threading
import platform
from typing import Optional, Dict, Any

from app.config.settings import settings

logger = logging.getLogger("DADUS.Discovery")

UDP_DISCOVERY_PORT = 41234
MAGIC_DISCOVERY_PACKET = b"DADUS_DISCOVER"
MAGIC_RESPONSE_PREFIX = b"DADUS_HUB:"


def _get_local_ip() -> str:
    """Determine the primary local IPv4 address of the machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Connect to a public DNS IP (does not actually send packets)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class DiscoveryServer:
    """Background UDP listener answering discovery broadcasts from local companion devices."""

    def __init__(self, port: int = UDP_DISCOVERY_PORT):
        self.port = port
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None

    def start(self) -> None:
        """Start UDP broadcast listener thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_listener, daemon=True, name="DADUS-DiscoveryServer")
        self._thread.start()
        logger.info(f"Local network discovery service started on UDP port {self.port}.")

    def stop(self) -> None:
        """Stop UDP listener thread."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("Local network discovery service stopped.")

    def _run_listener(self) -> None:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._socket.bind(("", self.port))
            except Exception as bind_ex:
                logger.warning(f"Could not bind UDP discovery socket on port {self.port}: {bind_ex}")
                self._running = False
                return

            self._socket.settimeout(1.0)

            while self._running:
                try:
                    data, addr = self._socket.recvfrom(1024)
                    if data.strip() == MAGIC_DISCOVERY_PACKET:
                        local_ip = _get_local_ip()
                        payload = {
                            "service": "DADUS_HUB",
                            "version": "1.0.0",
                            "host": local_ip,
                            "api_port": settings.API_PORT,
                            "api_base_url": f"http://{local_ip}:{settings.API_PORT}",
                            "hostname": platform.node(),
                            "product": settings.PRODUCT_NAME
                        }
                        resp = MAGIC_RESPONSE_PREFIX + json.dumps(payload).encode("utf-8")
                        self._socket.sendto(resp, addr)
                        logger.info(f"Responded to discovery ping from {addr[0]}:{addr[1]}")
                except socket.timeout:
                    continue
                except Exception as ex:
                    if self._running:
                        logger.debug(f"Discovery listener loop note: {ex}")
        except Exception as ex:
            logger.warning(f"Discovery listener encountered error: {ex}")
        finally:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass


def discover_dadus_hub(timeout: float = 2.0, port: int = UDP_DISCOVERY_PORT) -> Optional[Dict[str, Any]]:
    """Client utility for companion apps / devices to locate DADUS hub on the local network."""
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    client_sock.settimeout(timeout)

    try:
        # Broadcast discovery packet
        client_sock.sendto(MAGIC_DISCOVERY_PACKET, ("<broadcast>", port))
        data, addr = client_sock.recvfrom(2048)
        if data.startswith(MAGIC_RESPONSE_PREFIX):
            json_bytes = data[len(MAGIC_RESPONSE_PREFIX):]
            return json.loads(json_bytes.decode("utf-8"))
    except socket.timeout:
        logger.debug("Local hub discovery timed out.")
        return None
    except Exception as ex:
        logger.debug(f"Error during hub discovery: {ex}")
        return None
    finally:
        client_sock.close()


discovery_service = DiscoveryServer()
