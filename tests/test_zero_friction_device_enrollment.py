"""Comprehensive tests for DADUS Zero-Friction Device Auto-Enrollment & Discovery.
Verifies:
1. DeviceManager auto_enroll_device creates persistent records with secure HMAC tokens.
2. Re-enrollment with existing credentials refreshes session without duplicate devices.
3. FastAPI endpoints (/api/devices/auto-enroll, /api/devices/verify, /api/devices).
4. Local network UDP broadcast discovery handshake.
5. ADB bridge detection and hardware synchronization.
"""
import pytest
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.api.server import app
from app.database.database import get_db_context, init_db
from app.database.models import PairedDevice
from app.devices.device_manager import (
    DeviceManager,
    DeviceType,
    DeviceCapability,
    device_manager
)
from app.devices.discovery import DiscoveryServer, discover_dadus_hub, MAGIC_DISCOVERY_PACKET, MAGIC_RESPONSE_PREFIX
from app.platform.adb_bridge import AdbBridge

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_devices_db():
    init_db()
    with get_db_context() as db:
        db.query(PairedDevice).delete()
    yield
    with get_db_context() as db:
        db.query(PairedDevice).delete()


# ==========================================
# 1. DeviceManager Auto-Enrollment Logic
# ==========================================
def test_device_manager_new_auto_enrollment():
    dm = DeviceManager()
    dev, token, is_new = dm.auto_enroll_device(
        name="Abhinav's Galaxy S24",
        device_type=DeviceType.ANDROID_MOBILE,
        capabilities=[DeviceCapability.AUDIO_PLAYBACK, DeviceCapability.MICROPHONE]
    )

    assert is_new is True
    assert dev.device_id.startswith("dev_")
    assert len(token) >= 32
    assert dev.name == "Abhinav's Galaxy S24"
    assert dev.device_type == DeviceType.ANDROID_MOBILE

    # Verify persisted in SQLite
    with get_db_context() as db:
        saved = db.query(PairedDevice).filter(PairedDevice.device_id == dev.device_id).first()
        assert saved is not None
        assert saved.name == "Abhinav's Galaxy S24"


def test_device_manager_idempotent_re_enrollment():
    dm = DeviceManager()
    dev1, token1, is_new1 = dm.auto_enroll_device(
        name="Living Room Tablet",
        device_type=DeviceType.ANDROID_MOBILE
    )
    assert is_new1 is True

    # Re-enrolling with existing credentials must return the same device without duplicating
    dev2, token2, is_new2 = dm.auto_enroll_device(
        name="Living Room Tablet",
        device_type=DeviceType.ANDROID_MOBILE,
        existing_device_id=dev1.device_id,
        existing_token=token1
    )

    assert is_new2 is False
    assert dev2.device_id == dev1.device_id
    assert token2 == token1


# ==========================================
# 2. REST API Endpoints
# ==========================================
def test_api_auto_enroll_endpoint():
    payload = {
        "device_name": "Workstation Companion (Pixel 8)",
        "device_type": "android_mobile",
        "capabilities": ["audio_playback", "microphone", "local_app_execution"]
    }
    res = client.post("/api/devices/auto-enroll", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "enrolled"
    assert data["is_new"] is True
    assert "device_id" in data
    assert "auth_token" in data
    assert "audio_playback" in data["capabilities"]

    dev_id = data["device_id"]
    token = data["auth_token"]

    # Verify endpoint
    verify_res = client.get(f"/api/devices/verify?device_id={dev_id}", headers={"Authorization": f"Bearer {token}"})
    assert verify_res.status_code == 200
    assert verify_res.json()["verified"] is True


def test_api_verify_rejects_invalid_token():
    res = client.get("/api/devices/verify?device_id=dev_unknown&token=wrong_token")
    assert res.status_code in [401, 403]


def test_api_list_devices_endpoint():
    res = client.get("/api/devices")
    assert res.status_code == 200
    data = res.json()
    assert "count" in data
    assert "devices" in data
    assert any(d["device_id"] == "host_windows_pc" for d in data["devices"])


# ==========================================
# 3. Local Network UDP Broadcast Discovery
# ==========================================
def test_local_network_discovery_handshake():
    test_port = 41239
    server = DiscoveryServer(port=test_port)
    server.start()
    try:
        # Give thread 50ms to bind
        time.sleep(0.05)
        hub_info = discover_dadus_hub(timeout=1.0, port=test_port)
        assert hub_info is not None
        assert hub_info.get("service") == "DADUS_HUB"
        assert "api_port" in hub_info
    finally:
        server.stop()


# ==========================================
# 4. ADB Hardware Bridge
# ==========================================
def test_adb_bridge_detection_and_sync():
    bridge = AdbBridge()
    # Mock connected android device
    mock_devices_output = (
        "List of devices attached\n"
        "emulator-5554          device product:sdk_gphone64_x86_64 model:Pixel_8 device:emu64x transport_id:1\n"
    )

    with patch.object(bridge, "_run_cmd", return_value=mock_devices_output):
        detected = bridge.detect_connected_devices()
        assert len(detected) == 1
        assert detected[0]["serial"] == "emulator-5554"
        assert "Pixel 8" in detected[0]["model"]

        synced = bridge.sync_attached_android_devices()
        assert len(synced) == 1
        assert synced[0].device_id == "android_adb_emulator-5554"

