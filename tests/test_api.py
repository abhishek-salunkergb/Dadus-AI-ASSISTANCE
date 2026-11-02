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
