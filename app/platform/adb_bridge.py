"""ADB (Android Debug Bridge) hardware interface for DADUS.
Automatically detects, registers, and controls physically or Wi-Fi connected Android devices.
Enables PC-to-Mobile phone dialing, camera activation, and status queries with zero manual setup.
"""
import os
import re
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any

from app.devices.device_manager import (
    device_manager,
    ConnectedDevice,
    DeviceType,
    DeviceCapability
)

logger = logging.getLogger("DADUS.Platform.ADB")


def _find_adb_binary() -> Optional[str]:
    """Locates the ADB executable on PATH or within standard Android SDK directories."""
    # 1. Check system PATH
    which_adb = shutil.which("adb")
    if which_adb:
        return which_adb

    # 2. Check standard Windows LocalAppData Android SDK location
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        sdk_candidate = Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
        if sdk_candidate.exists():
            return str(sdk_candidate)

    # 3. Check Program Files
    prog_files = os.environ.get("ProgramFiles")
    if prog_files:
        p_candidate = Path(prog_files) / "Android" / "android-sdk" / "platform-tools" / "adb.exe"
        if p_candidate.exists():
            return str(p_candidate)

    return None


class AdbBridge:
    """Manages zero-friction communication with connected Android devices."""

    def __init__(self):
        self._adb_path = _find_adb_binary()

    @property
    def is_available(self) -> bool:
        """Returns True if the ADB toolchain is present on the workstation."""
        return self._adb_path is not None

    def _run_cmd(self, args: List[str], timeout: float = 3.0) -> Optional[str]:
        if not self._adb_path:
            return None
        try:
            full_cmd = [self._adb_path] + args
            out = subprocess.check_output(full_cmd, stderr=subprocess.DEVNULL, timeout=timeout)
            return out.decode("utf-8", errors="ignore").strip()
        except Exception as ex:
            logger.debug(f"ADB command failed ({args}): {ex}")
            return None

    def detect_connected_devices(self) -> List[Dict[str, Any]]:
        """Scans for connected Android devices over USB or Wi-Fi debugging."""
        raw_output = self._run_cmd(["devices", "-l"])
        if not raw_output:
            return []

        devices = []
        for line in raw_output.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("List of devices"):
                continue

            # Format: <serial> device product:xxx model:Pixel_8 device:xxx transport_id:1
            parts = line_str.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                model = "Android Device"
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p.split("model:", 1)[1].replace("_", " ")

                devices.append({
                    "serial": serial,
                    "model": model,
                    "raw_line": line_str
                })

        return devices

    def sync_attached_android_devices(self) -> List[ConnectedDevice]:
        """Auto-discovers and registers connected Android phones into DADUS DeviceManager."""
        detected = self.detect_connected_devices()
        registered = []

        for d in detected:
            dev_id = f"android_adb_{d['serial']}"
            name = f"{d['model']} (USB/Wi-Fi)"
            caps = [
                DeviceCapability.AUDIO_PLAYBACK,
                DeviceCapability.MICROPHONE,
                DeviceCapability.LOCAL_APP_EXECUTION,
                DeviceCapability.HARDWARE_MEDIA_KEYS,
                DeviceCapability.SYSTEM_NOTIFICATIONS
            ]

            conn_device = ConnectedDevice(
                device_id=dev_id,
                name=name,
                device_type=DeviceType.ANDROID_MOBILE,
                capabilities=caps
            )
            device_manager.register_device(conn_device, persist=True)
            registered.append(conn_device)
            logger.info(f"Auto-mounted connected Android device: {name} [{dev_id}]")

        return registered

    def dial_phone(self, phone_number: str, serial: Optional[str] = None) -> bool:
        """Launches Android native phone dialer with specified number."""
        clean_num = re.sub(r"[^\d\+]", "", phone_number)
        args = []
        if serial:
            args.extend(["-s", serial])
        args.extend(["shell", "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{clean_num}"])
        out = self._run_cmd(args)
        return out is not None

    def launch_camera(self, mode: str = "photo", serial: Optional[str] = None) -> bool:
        """Launches Android native camera in photo or video mode."""
        action = "android.media.action.IMAGE_CAPTURE" if mode == "photo" else "android.media.action.VIDEO_CAPTURE"
        args = []
        if serial:
            args.extend(["-s", serial])
        args.extend(["shell", "am", "start", "-a", action])
        out = self._run_cmd(args)
        return out is not None

    def get_battery_level(self, serial: Optional[str] = None) -> Optional[int]:
        """Reads real battery percentage from connected Android device."""
        args = []
        if serial:
            args.extend(["-s", serial])
        args.extend(["shell", "dumpsys", "battery"])
        out = self._run_cmd(args)
        if out:
            match = re.search(r"level:\s*(\d+)", out)
            if match:
                return int(match.group(1))
        return None


adb_bridge = AdbBridge()
