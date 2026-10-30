"""MCP test client for verifying standards-compliant MCP integration."""
from typing import Dict, Any, List, Optional
from app.mcp.server import MCPServer

class MCPClient:
    """In-process and stdio-compatible MCP client for verification."""

    def __init__(self, server: Optional[MCPServer] = None):
        from app.mcp.server import mcp_server
        self.server = server or mcp_server
        self._msg_id = 1

    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send JSON-RPC request to server and return response."""
        req = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params or {}
        }
        self._msg_id += 1
        return self.server.handle_request(req)

    def initialize(self) -> Dict[str, Any]:
        return self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "dadus-test-client", "version": "1.0.0"}
        })

    def list_tools(self) -> List[Dict[str, Any]]:
        resp = self.send_request("tools/list")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
