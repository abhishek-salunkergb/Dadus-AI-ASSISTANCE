"""Tests for standards-compliant Model Context Protocol (MCP) server and client."""
import pytest
from app.mcp.server import MCPServer, mcp_server
from app.mcp.client import MCPClient

def test_mcp_initialize():
    client = MCPClient(mcp_server)
    res = client.initialize()
    assert res.get("jsonrpc") == "2.0"
    result = res.get("result", {})
    assert result.get("protocolVersion") == "2024-11-05"
    assert result.get("serverInfo", {}).get("name") == "dadus-mcp-server"

def test_mcp_ping():
    client = MCPClient(mcp_server)
    res = client.send_request("ping")
    assert res.get("jsonrpc") == "2.0"
    assert "result" in res

def test_mcp_list_tools():
    client = MCPClient(mcp_server)
    tools = client.list_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 25
    tool_names = [t["name"] for t in tools]
    assert "get_current_time" in tool_names
    assert "set_volume" in tool_names
    assert "create_task" in tool_names
    assert "open_app" in tool_names
    assert "store_memory" in tool_names

def test_mcp_call_tool_valid():
    client = MCPClient(mcp_server)
    res = client.call_tool("get_current_time", {})
    assert res.get("jsonrpc") == "2.0"
    result = res.get("result", {})
    assert result.get("isError") is False
    content = result.get("content", [])
    assert len(content) > 0
    assert "Boss, it is" in content[0]["text"]

def test_mcp_call_tool_create_task():
    client = MCPClient(mcp_server)
    res = client.call_tool("create_task", {"title": "Test MCP Integration Task", "priority": "high"})
    assert res.get("jsonrpc") == "2.0"
    result = res.get("result", {})
    assert result.get("isError") is False
    assert any("Task created" in c["text"] for c in result.get("content", []))

def test_mcp_call_tool_missing_name():
    client = MCPClient(mcp_server)
    res = client.send_request("tools/call", {"arguments": {}})
    assert "error" in res
    assert res["error"]["code"] == -32602

def test_mcp_unknown_method():
    client = MCPClient(mcp_server)
    res = client.send_request("unknown/method")
    assert "error" in res
    assert res["error"]["code"] == -32601
