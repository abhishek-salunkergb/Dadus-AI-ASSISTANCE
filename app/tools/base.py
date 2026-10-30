"""Base tool classes and result structures for DADUS."""
from abc import ABC, abstractmethod
from typing import Type, Any, Optional, Dict, List
from pydantic import BaseModel, Field
from app.security.permissions import PermissionLevel

class ToolResult(BaseModel):
    """Standardized result returned by every DADUS tool."""
    tool_name: str
    success: bool
    message: str
    data: Optional[Any] = None
    error: Optional[str] = None
    needs_clarification: bool = False
    options: Optional[List[str]] = None
    confirmation_required: bool = False
    confirmation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class BaseTool(ABC):
    """Abstract base class for all agent tools."""
    name: str
    description: str
    permission_level: PermissionLevel = PermissionLevel.SAFE
    args_schema: Type[BaseModel]

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with validated arguments."""
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert tool definition to OpenAI tool calling format."""
        schema = self.args_schema.model_json_schema()
        # Clean up schema for OpenAI
        parameters = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", [])
        }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters
            }
        }

    def to_mcp_tool(self) -> Dict[str, Any]:
        """Convert tool to Model Context Protocol (MCP) tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.args_schema.model_json_schema()
        }
