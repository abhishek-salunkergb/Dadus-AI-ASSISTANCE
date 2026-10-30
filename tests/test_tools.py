"""Unit tests for tool registry and core tool execution."""
import pytest
from app.tools.registry import tool_registry
from app.security.permissions import PermissionLevel
from app.tools.system import SetVolumeTool, GetCurrentTimeTool, GetSystemStatusTool
from app.tools.files import SearchFilesTool

def test_tool_registry_registration():
    """Verify standard tools are properly registered."""
    tools = tool_registry.list_tools()
    assert len(tools) >= 20
    tool_names = [t.name for t in tools]
    assert "open_app" in tool_names
    assert "close_app" in tool_names
    assert "play_music" in tool_names
    assert "set_volume" in tool_names
    assert "create_reminder" in tool_names
    assert "get_today_schedule" in tool_names
    assert "delete_file_or_folder" in tool_names
    assert "store_memory" in tool_names

def test_openai_tool_schemas():
    """Verify tool schemas export in valid OpenAI function-call format."""
    schemas = tool_registry.get_openai_tools()
    assert len(schemas) >= 20
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"

def test_mcp_tool_schemas():
    """Verify tool schemas export in Model Context Protocol format."""
    mcp_tools = tool_registry.get_mcp_tools()
    assert len(mcp_tools) >= 20
    for mt in mcp_tools:
        assert "name" in mt
        assert "description" in mt
        assert "inputSchema" in mt

def test_get_current_time_tool():
    """Verify time tool returns valid string."""
    tool = GetCurrentTimeTool()
    res = tool.execute()
    assert res.success is True
    assert "Boss, it is" in res.message
    assert "time" in res.data
    assert "date" in res.data

def test_get_system_status_tool():
    """Verify system status retrieves CPU and RAM."""
    tool = GetSystemStatusTool()
    res = tool.execute()
    assert res.success is True
    assert "cpu_percent" in res.data
    assert "ram_percent" in res.data
    assert "Boss, CPU is at" in res.message

def test_set_volume_tool_valid():
    """Verify volume tool runs with scalar bounds."""
    tool = SetVolumeTool()
    res = tool.execute(level=35)
    assert res.success is True
    assert "35" in res.message

def test_invalid_tool_execution():
    """Verify registry gracefully handles unknown tool without crashing."""
    res = tool_registry.execute_tool("non_existent_tool_xyz", {})
    assert res.success is False
    assert "Boss, I don't know how to execute" in res.message
    assert res.error == "Unknown tool: 'non_existent_tool_xyz'"

def test_invalid_tool_arguments():
    """Verify registry validates arguments and returns structured error."""
    # set_volume requires integer level
    res = tool_registry.execute_tool("set_volume", {"level": "not_a_number"})
    assert res.success is False
    assert "invalid" in res.message.lower()
