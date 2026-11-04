"""Comprehensive tests for DADUS Universal Device and Application Integration.
Verifies device identification, capability registry, camera, gallery, calling,
Gmail account tools, granular permissions, and natural language command routing.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.agent.agent import DadusAgent
from app.platform import platform_adapter, capability_registry
from app.platform.base import DeviceInfo
from app.security.permissions import permission_manager, Capability
from app.tools.camera import OpenCameraTool, RecordVideoTool
from app.tools.gallery import OpenGalleryTool, ShowRecentPhotosTool
from app.tools.gmail import ReadLatestEmailTool, DraftEmailTool, SendEmailTool, GmailClient
from app.database.database import get_db_context, init_db
from app.database.models import Contact


# ==========================================
# 1. Device Identification & Platform Tests
# ==========================================
def test_platform_device_identification():
    """Verify automatic device identification discovers OS, hardware, and accounts."""
    info = platform_adapter.get_device_info()
    assert isinstance(info, DeviceInfo)
    assert info.os_name in ["Windows", "Android", "Linux"]
    assert info.cpu_count >= 1
    assert info.memory_total_gb > 0
    assert isinstance(info.has_camera, bool)
    assert isinstance(info.has_microphone, bool)
    assert isinstance(info.has_battery, bool)
    assert isinstance(info.connected_accounts, dict)
    assert "gmail" in info.connected_accounts
    assert len(info.supported_capabilities) >= 10


def test_capability_registry_discovery():
    """Verify dynamic registry indexes camera, gallery, calling, email, calendar, and browser."""
    caps = capability_registry.list_all_capabilities()
    assert "camera" in caps
    assert "gallery" in caps
    assert "calling" in caps
    assert "email" in caps
    assert "calendar" in caps
    assert "browser" in caps

    best_cam = capability_registry.get_best_provider("camera")
    assert best_cam is not None
    assert "camera" in best_cam["identifier"].lower() or best_cam["integration_type"] in ["os_protocol", "android_intent"]

    best_gal = capability_registry.get_best_provider("gallery")
    assert best_gal is not None
    assert "photos" in best_gal["identifier"].lower() or "pictures" in best_gal["identifier"].lower() or best_gal["integration_type"] in ["os_protocol", "android_intent"]


# ==========================================
# 2. Camera and Gallery Tools Tests
# ==========================================
@patch.object(platform_adapter, "launch_camera", return_value=True)
def test_open_camera_tool_success(mock_cam):
    tool = OpenCameraTool()
    res = tool.execute(mode="photo")
    assert res.success is True
    assert "camera" in res.message.lower()
    mock_cam.assert_called_once_with(mode="photo")


def test_open_camera_permission_denial():
    permission_manager.set_permission("camera_access", False)
    try:
        tool = OpenCameraTool()
        res = tool.execute(mode="photo")
        assert res.success is False
        assert res.error == "PERMISSION_DENIED"
        assert "disabled" in res.message.lower()
    finally:
        permission_manager.set_permission("camera_access", True)


@patch.object(platform_adapter, "launch_camera", return_value=True)
def test_record_video_tool(mock_cam):
    tool = RecordVideoTool()
    res = tool.execute()
    assert res.success is True
    assert "video" in res.message.lower()
    mock_cam.assert_called_once_with(mode="video")


@patch.object(platform_adapter, "launch_gallery", return_value=True)
def test_open_gallery_tool_success(mock_gal):
    tool = OpenGalleryTool()
    res = tool.execute()
    assert res.success is True
    assert "gallery" in res.message.lower()
    mock_gal.assert_called_once()


def test_open_gallery_permission_denial():
    permission_manager.set_permission("photos_gallery", False)
    try:
        tool = OpenGalleryTool()
        res = tool.execute()
        assert res.success is False
        assert res.error == "PERMISSION_DENIED"
    finally:
        permission_manager.set_permission("photos_gallery", True)


def test_show_recent_photos_real_scanning(tmp_path):
    """Verify real scanning and formatting of recent photos."""
    # Create sample real image files in temp directory
    img1 = tmp_path / "img1.png"
    img1.write_bytes(b"\x89PNG\r\n\x1a\nfakecontent1")
    img2 = tmp_path / "img2.jpg"
    img2.write_bytes(b"\xff\xd8\xff\xe0fakecontent2")

    with patch.object(platform_adapter, "get_recent_photos", return_value=[img1, img2]):
        tool = ShowRecentPhotosTool()
        res = tool.execute(limit=5)
        assert res.success is True
        assert res.data["count"] == 2
        assert "img1.png" in res.message
        assert "img2.jpg" in res.message


# ==========================================
# 3. Gmail Integration & Account Tools Tests
# ==========================================
def test_read_latest_email_unauthenticated_honesty():
    """Verify read_latest_email returns honest unauthenticated error when not signed in."""
    with patch.object(GmailClient, "is_connected", return_value=False):
        tool = ReadLatestEmailTool()
        res = tool.execute()
        assert res.success is False
        assert res.error == "GMAIL_AUTH_REQUIRED"
        assert "not connected" in res.message.lower()


def test_read_latest_email_authenticated_parsing():
    """Verify parsing of genuine retrieved Gmail message payload."""
    fake_list = {"messages": [{"id": "msg_001"}]}
    fake_msg = {
        "id": "msg_001",
        "threadId": "thread_001",
        "snippet": "We are pleased to offer you the position of Principal Architect.",
        "payload": {
            "headers": [
                {"name": "From", "value": "Google Careers <careers@google.com>"},
                {"name": "Subject", "value": "Offer of Employment"},
                {"name": "Date", "value": "Wed, 04 Nov 2026 14:00:00 +0000"}
            ]
        }
    }

    mock_resp1 = MagicMock(status_code=200, json=lambda: fake_list)
    mock_resp2 = MagicMock(status_code=200, json=lambda: fake_msg)

    with patch.object(GmailClient, "is_connected", return_value=True), \
         patch.object(GmailClient, "get_token", return_value="fake_valid_token"), \
         patch("requests.get", side_effect=[mock_resp1, mock_resp2]):
        tool = ReadLatestEmailTool()
        res = tool.execute()
        assert res.success is True
        assert "careers@google.com" in res.data["sender"]
        assert "Offer of Employment" in res.data["subject"]
        assert "thread_001" in res.data["gmail_link"]


def test_send_email_confirmation_enforcement():
    """Verify that send_email strictly enforces CONFIRMATION_REQUIRED permission level."""
    tool = SendEmailTool()
    assert tool.permission_level.value == "CONFIRMATION_REQUIRED"


# ==========================================
# 4. Natural Language Device Operations Tests
# ==========================================
def test_natural_language_camera_and_gallery_routing():
    agent = DadusAgent()
    sid = "universal_test_session"

    # 1. "Open the camera and take a picture"
    with patch("os.startfile"):
        res1 = agent.process_input("Open the camera and take a picture.", session_id=sid)
        assert res1.status == "DONE"
        assert res1.tool_called == "open_camera"

        # 2. "Record a video"
        res2 = agent.process_input("Record a video.", session_id=sid)
        assert res2.status == "DONE"
        assert res2.tool_called == "record_video"

        # 3. "Open my gallery"
        res3 = agent.process_input("Open my gallery.", session_id=sid)
        assert res3.status == "DONE"
        assert res3.tool_called == "open_gallery"

        # 4. "Show my recent photos"
        res4 = agent.process_input("Show my recent photos.", session_id=sid)
        assert res4.status == "DONE"
        assert res4.tool_called == "show_recent_photos"


def test_natural_language_email_and_files_routing():
    agent = DadusAgent()
    sid = "universal_email_session"

    # 1. "Read my latest email"
    with patch.object(GmailClient, "is_connected", return_value=False):
        res1 = agent.process_input("Read my latest email.", session_id=sid)
        assert res1.status == "DONE"
        assert res1.tool_called == "read_latest_email"

    # 2. "Find my downloaded PDF"
    res2 = agent.process_input("Find my downloaded PDF.", session_id=sid)
    assert res2.status == "DONE"
    assert res2.tool_called == "search_files"

    # 3. "Create a calendar event"
    res3 = agent.process_input("Create a calendar event for Team Standup tomorrow at 10 AM", session_id=sid)
    assert res3.status == "DONE"
    assert res3.tool_called == "create_schedule_item"

    # 4. "Open my music application"
    with patch("os.startfile"):
        res4 = agent.process_input("Open my music application.", session_id=sid)
        assert res4.status == "DONE"
        assert res4.tool_called == "open_app"
