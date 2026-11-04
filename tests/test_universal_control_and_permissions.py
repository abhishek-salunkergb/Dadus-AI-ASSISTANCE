"""Tests for universal voice-controlled actions, device lock permissions, and security guardrails."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.security.permissions import (
    Capability,
    PermissionManager,
    permission_manager,
    PermissionLevel,
    SecurityInspector
)
from app.agent.router import intent_router
from app.agent.agent import dadus_agent
from app.tools.registry import tool_registry
from app.tools.system import LockDeviceTool, ToggleBluetoothTool, TakeScreenshotTool
from app.tools.apps import OpenAppTool, CloseAppTool
from app.api.server import app

client = TestClient(app)


def test_permission_manager_toggle_and_persistence(tmp_path):
    """Test setting, getting, and persisting capability permissions."""
    test_storage = tmp_path / "test_permissions.json"
    pm = PermissionManager(storage_path=test_storage)

    # Initially device_lock is enabled by default
    assert pm.is_permitted(Capability.DEVICE_LOCK) is True

    # Disable device_lock
    success = pm.set_permission(Capability.DEVICE_LOCK, False)
    assert success is True
    assert pm.is_permitted(Capability.DEVICE_LOCK) is False

    # Check that it persisted to file
    pm2 = PermissionManager(storage_path=test_storage)
    assert pm2.is_permitted(Capability.DEVICE_LOCK) is False

    # Re-enable
    pm.set_permission(Capability.DEVICE_LOCK, True)
    assert pm.is_permitted(Capability.DEVICE_LOCK) is True


def test_device_lock_permission_disabled_refuses_execution():
    """When Device Lock permission is disabled, locking commands must be refused with clear explanation."""
    try:
        permission_manager.set_permission("device_lock", False)

        # 1. Direct tool execution
        tool = LockDeviceTool()
        res = tool.execute()
        assert res.success is False
        assert "Device Lock permission is currently disabled" in res.message

        # 2. Execution via ToolRegistry
        reg_res = tool_registry.execute_tool("lock_device", {})
        assert reg_res.success is False
        assert "Device Lock permission is currently disabled" in reg_res.message
    finally:
        # Restore permission
        permission_manager.set_permission("device_lock", True)


def test_device_lock_permission_enabled_succeeds():
    """When Device Lock permission is enabled, lock_device calls OS LockWorkStation."""
    try:
        permission_manager.set_permission("device_lock", True)

        with patch("ctypes.windll.user32.LockWorkStation", return_value=1) as mock_lock:
            res = tool_registry.execute_tool("lock_device", {})
            assert res.success is True
            assert "Locking device, boss." in res.message
            assert mock_lock.called
    finally:
        permission_manager.set_permission("device_lock", True)


def test_voice_command_lock_variations_route_to_lock_device():
    """Natural variations of lock command must route to lock_device."""
    variations = [
        "Lock my computer",
        "Lock the device",
        "Lock my PC",
        "Lock workstation",
        "Lock screen",
        "Please lock my computer"
    ]
    for phrase in variations:
        tcall, direct_resp = intent_router.route_intent(phrase, [])
        assert tcall is not None, f"Failed to route '{phrase}'"
        assert tcall.tool_name == "lock_device", f"Expected lock_device for '{phrase}', got {tcall.tool_name}"


def test_voice_unlock_strictly_refused_to_preserve_os_security():
    """Voice unlock attempts must be refused with explicit explanation; never bypass OS auth."""
    unlock_phrases = [
        "Unlock my computer",
        "Unlock my PC",
        "Unlock the device",
        "Unlock screen",
        "Bypass windows lock"
    ]
    for phrase in unlock_phrases:
        tcall, direct_resp = intent_router.route_intent(phrase, [])
        assert tcall is None, f"Unlock attempt '{phrase}' should not trigger any tool call"
        assert direct_resp is not None
        assert "cannot unlock your computer via voice" in direct_resp.lower() or "cannot access" in direct_resp.lower()


def test_compound_browser_search_command():
    """Commands like 'Open Chrome and search for Python developer jobs' route to search_web."""
    queries = [
        ("Open Chrome and search for Python developer jobs", "Python developer jobs"),
        ("Open browser and search for machine learning tutorials", "machine learning tutorials"),
        ("Open Edge and search for weather in Tokyo", "weather in Tokyo")
    ]
    for text, expected_query in queries:
        tcall, direct_resp = intent_router.route_intent(text, [])
        assert tcall is not None, f"Failed to route '{text}'"
        assert tcall.tool_name == "search_web"
        assert tcall.arguments.get("query") == expected_query


def test_bluetooth_toggle_tool_and_voice_routing():
    """Voice command to turn on/off Bluetooth routes to toggle_bluetooth."""
    # Routing test
    tcall_on, _ = intent_router.route_intent("Turn on Bluetooth", [])
    assert tcall_on is not None
    assert tcall_on.tool_name == "toggle_bluetooth"
    assert tcall_on.arguments.get("enable") is True

    tcall_off, _ = intent_router.route_intent("Turn off Bluetooth", [])
    assert tcall_off is not None
    assert tcall_off.tool_name == "toggle_bluetooth"
    assert tcall_off.arguments.get("enable") is False

    # Tool execution test
    with patch("os.startfile") as mock_startfile:
        tool = ToggleBluetoothTool()
        res_on = tool.execute(enable=True)
        assert res_on.success is True
        assert "Turned on Bluetooth" in res_on.message

        res_off = tool.execute(enable=False)
        assert res_off.success is True
        assert "Turned off Bluetooth" in res_off.message


def test_volume_voice_control():
    """Natural volume commands route to adjust_volume with appropriate direction."""
    tcall_up, _ = intent_router.route_intent("Increase the volume", [])
    assert tcall_up is not None
    assert tcall_up.tool_name == "adjust_volume"
    assert tcall_up.arguments.get("direction") == "higher"

    tcall_down, _ = intent_router.route_intent("Turn down the volume", [])
    assert tcall_down is not None
    assert tcall_down.tool_name == "adjust_volume"
    assert tcall_down.arguments.get("direction") == "lower"


def test_app_control_permission_disabled_blocks_app():
    """Disabling app_control permission blocks open_app and close_app."""
    try:
        permission_manager.set_permission("app_control", False)

        open_tool = OpenAppTool()
        res_open = open_tool.execute(app_name="Notepad")
        assert res_open.success is False
        assert "Application Control permission is currently disabled" in res_open.message

        close_tool = CloseAppTool()
        res_close = close_tool.execute(app_name="Notepad")
        assert res_close.success is False
        assert "Application Control permission is currently disabled" in res_close.message
    finally:
        permission_manager.set_permission("app_control", True)


def test_context_follow_up_close_app():
    """Contextual follow-up 'Close it' terminates the previously launched application."""
    session_id = "test_context_app_session"
    session = dadus_agent.get_or_create_session(session_id)
    session.context_entities["active_app"] = "Spotify"

    # User says "Close it"
    resp = dadus_agent.process_input("Close it", session_id=session_id)
    assert resp.tool_called == "close_app"
    assert resp.tool_result is not None


def test_api_permissions_get_and_post():
    """Test REST API endpoints for querying and updating capability permissions."""
    # 1. GET /api/system/permissions
    get_res = client.get("/api/system/permissions")
    assert get_res.status_code == 200
    data = get_res.json()
    assert "device_lock" in data
    assert "name" in data["device_lock"]
    assert "enabled" in data["device_lock"]

    # 2. POST /api/system/permissions toggle device_lock to False
    post_res = client.post("/api/system/permissions", json={"permission": "device_lock", "enabled": False})
    assert post_res.status_code == 200
    assert permission_manager.is_permitted("device_lock") is False

    # 3. POST /api/system/permissions toggle back to True
    client.post("/api/system/permissions", json={"permission": "device_lock", "enabled": True})
    assert permission_manager.is_permitted("device_lock") is True
