"""Integration tests for FastAPI REST endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.api.server import app

@pytest.fixture
def client():
    return TestClient(app)

def test_api_status_endpoint(client):
    """Verify /api/status returns assistant details and tools."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["product"] == "DADUS"
    assert data["assistant"] == "Dadus"
    assert data["wake_phrase"] == "Hey Dadus"
    assert data["tool_count"] >= 20

def test_api_chat_endpoint(client):
    """Verify /api/chat processes text and returns response."""
    resp = client.post("/api/chat", json={
        "message": "Hey Dadus, what is the time?",
        "session_id": "test_api_session",
        "speak_response": False
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "time" in data["text"].lower() or "boss" in data["text"].lower()
    assert data["tool_called"] == "get_current_time"

def test_api_schedule_endpoints(client):
    """Verify /api/schedule retrieves reminders and schedule."""
    resp = client.get("/api/schedule")
    assert resp.status_code == 200
    data = resp.json()
    assert "reminders" in data
    assert "schedule_items" in data

def test_api_memory_endpoints(client):
    """Verify /api/memory CRUD."""
    # Create
    post_resp = client.post("/api/memory", json={"key": "favorite_color", "value": "cyan"})
    assert post_resp.status_code == 200

    # List
    get_resp = client.get("/api/memory")
    assert get_resp.status_code == 200
    keys = [m["key"] for m in get_resp.json()["memories"]]
    assert "favorite_color" in keys

    # Delete
    del_resp = client.delete("/api/memory/favorite_color")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

def test_api_tasks_crud_including_delete(client):
    """Verify task creation, completion, and deletion endpoints."""
    # 1. Create
    create_resp = client.post("/api/tasks", json={"title": "API Test Task", "priority": "high"})
    assert create_resp.status_code == 200
    task_id = create_resp.json()["task"]["id"]

    # 2. List
    list_resp = client.get("/api/tasks")
    assert list_resp.status_code == 200
    assert any(t["id"] == task_id for t in list_resp.json()["tasks"])

    # 3. Complete
    comp_resp = client.post(f"/api/tasks/{task_id}/complete")
    assert comp_resp.status_code == 200
    assert comp_resp.json()["success"] is True

    # 4. Delete
    del_resp = client.delete(f"/api/tasks/{task_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 5. Verify deleted from list
    verify_resp = client.get("/api/tasks?status=all")
    assert not any(t["id"] == task_id for t in verify_resp.json()["tasks"])

def test_api_confirm_endpoint(client):
    """Verify /api/confirm resolves pending confirmation."""
    # Trigger a confirmation
    chat_resp = client.post("/api/chat", json={
        "message": "delete file test_dummy.log",
        "session_id": "api_confirm_session",
        "speak_response": False
    })
    cdata = chat_resp.json()
    assert cdata["needs_confirmation"] is True
    cid = cdata["confirmation_id"]

    # Reject via confirm endpoint
    conf_resp = client.post("/api/confirm", json={
        "confirmation_id": cid,
        "confirmed": False,
        "session_id": "api_confirm_session"
    })
    assert conf_resp.status_code == 200
    assert conf_resp.json()["status"] == "rejected"
    assert "Cancelled" in conf_resp.json()["message"]

def test_api_mcp_endpoints(client):
    """Verify HTTP Model Context Protocol (MCP) endpoints."""
    # Test MCP initialize
    init_resp = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp.status_code == 200
    idata = init_resp.json()
    assert idata.get("result", {}).get("serverInfo", {}).get("name") == "dadus-mcp-server"

    # Test MCP tools list
    tools_resp = client.get("/api/mcp/tools")
    assert tools_resp.status_code == 200
    tdata = tools_resp.json()
    assert "tools" in tdata
    assert len(tdata["tools"]) >= 25

    # Test MCP tool call
    call_resp = client.post("/api/mcp", json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "get_current_time", "arguments": {}}
    })
    assert call_resp.status_code == 200
    cdata = call_resp.json()
    assert cdata.get("result", {}).get("isError") is False

def test_api_voice_state_endpoints(client):
    """Verify voice state broadcast REST endpoints."""
    # 1. Get initial state
    resp = client.get("/api/voice/state")
    assert resp.status_code == 200
    assert "state" in resp.json()

    # 2. Update state to listening
    post_resp = client.post("/api/voice/state", json={"state": "listening", "text": "Listening to boss..."})
    assert post_resp.status_code == 200
    assert post_resp.json()["state"] == "listening"

    # 3. Verify get returns updated state
    verify_resp = client.get("/api/voice/state")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["state"] == "listening"

    # 4. Reset back to idle
    reset_resp = client.post("/api/voice/state", json={"state": "idle"})
    assert reset_resp.status_code == 200
    assert reset_resp.json()["state"] == "idle"


def test_sync_voice_state_helper():
    """Verify in-process thread-safe sync_voice_state helper updates broadcaster state."""
    from app.api.server import sync_voice_state, voice_broadcaster
    sync_voice_state("thinking", "Analyzing query...")
    assert voice_broadcaster.current_state == "thinking"
    sync_voice_state("idle")
    assert voice_broadcaster.current_state == "idle"


def test_api_list_indexed_apps(client):
    """Verify /api/apps returns indexed system and installed applications."""
    resp = client.get("/api/apps")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_indexed"] > 0
    assert len(data["apps"]) > 0

    # Test filtering
    filter_resp = client.get("/api/apps?q=chrome")
    assert filter_resp.status_code == 200
    fdata = filter_resp.json()
    assert fdata["success"] is True
    assert any("chrome" in a["name"].lower() or "chrome" in a["key"] for a in fdata["apps"])


def test_api_workstation_snapshots_crud(client):
    """Verify workstation snapshot capture, list, and restoration via REST API."""
    # 1. Capture snapshot
    save_resp = client.post("/api/workstation/save", json={"name": "api_test_snapshot"})
    assert save_resp.status_code == 200
    sdata = save_resp.json()
    assert sdata["success"] is True

    # 2. List snapshots
    list_resp = client.get("/api/workstation/snapshots")
    assert list_resp.status_code == 200
    ldata = list_resp.json()
    assert ldata["success"] is True
    assert any(s["name"] == "api_test_snapshot" for s in ldata["snapshots"])

    # 3. Restore snapshot
    restore_resp = client.post("/api/workstation/restore", json={"name": "api_test_snapshot"})
    assert restore_resp.status_code == 200
    rdata = restore_resp.json()
    assert rdata["success"] is True

