"""Standards-compliant Model Context Protocol (MCP) server for DADUS.
Exposes approved DADUS desktop tools via MCP JSON-RPC 2.0 over stdio and programmatic interfaces.
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import logging
from typing import Dict, Any, Optional, List
from app.tools.registry import tool_registry

logger = logging.getLogger("DADUS.MCP")

MCP_SERVER_NAME = "dadus-mcp-server"
MCP_SERVER_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

class MCPServer:
    """Model Context Protocol (MCP) server exposing DADUS tools."""

    def __init__(self):
        self.server_name = MCP_SERVER_NAME
        self.version = MCP_SERVER_VERSION
        self.protocol_version = MCP_PROTOCOL_VERSION

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a JSON-RPC 2.0 MCP request and return response."""
        req_id = request_data.get("id")
        method = request_data.get("method", "")
        params = request_data.get("params", {})

        logger.debug(f"MCP Received method '{method}' (id: {req_id})")

        # 1. Initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": self.server_name,
                        "version": self.version
                    }
                }
            }

        # 2. Ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 3. List Tools
        if method == "tools/list":
            tools_list = []
            for tool in tool_registry.list_tools():
                tools_list.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.args_schema.model_json_schema()
                })
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list}
            }

        # 4. Call Tool
        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Missing 'name' in tool call parameters"}
                }

            # Enforces DADUS permission layer
            res = tool_registry.execute_tool(
                name=tool_name,
                arguments=tool_args,
                user_input=f"[MCP Call: {tool_name}]"
            )

            content = [{
                "type": "text",
                "text": res.message or (res.error if res.error else "")
            }]
            if res.data:
                content.append({
                    "type": "text",
                    "text": json.dumps(res.data)
                })

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": content,
                    "isError": not res.success
                }
            }

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: '{method}'"}
        }

    def run_stdio(self) -> None:
        """Run MCP JSON-RPC server listening on standard input/output."""
        logger.info("Starting DADUS MCP server on stdio...")
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                req = json.loads(line_str)
                resp = self.handle_request(req)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            except json.JSONDecodeError as ex:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(ex)}"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

mcp_server = MCPServer()

if __name__ == "__main__":
    mcp_server.run_stdio()
