"""Central tool registry for DADUS.
Manages tool discovery, schema generation, permission enforcement, and execution.
"""
from typing import Dict, Any, Optional, List, Type
import logging
import json
from pydantic import ValidationError
from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel, SecurityInspector
from app.security.confirmations import confirmation_manager
from app.database.database import get_db_context
from app.database.models import AuditLog

logger = logging.getLogger("DADUS.ToolRegistry")

class ToolRegistry:
    """Registry holding all registered tools and enforcing execution rules."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name} (level: {tool.permission_level})")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Return all tool schemas formatted for OpenAI tool calling."""
        return [t.to_openai_tool() for t in self._tools.values()]

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Return all tool schemas formatted for Model Context Protocol."""
        return [t.to_mcp_tool() for t in self._tools.values()]

    def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        user_input: str = "",
        bypass_confirmation: bool = False
    ) -> ToolResult:
        """
        Validate permissions and execute a tool safely.
        Never executes restricted actions; routes confirmation-required actions
        through the confirmation manager.
        """
        tool = self.get_tool(name)
        if not tool:
            err_msg = f"Unknown tool: '{name}'"
            self._log_audit(user_input, name, arguments, "SAFE", "FAILED", err_msg)
            return ToolResult(
                tool_name=name,
                success=False,
                message=f"Boss, I don't know how to execute '{name}'.",
                error=err_msg
            )

        # 1. Security & Permission Evaluation
        effective_level, block_reason = SecurityInspector.evaluate_tool_permission(
            tool_name=name,
            base_level=tool.permission_level,
            arguments=arguments
        )

        if effective_level == PermissionLevel.RESTRICTED:
            logger.warning(f"Tool execution BLOCKED by security: {name} (reason: {block_reason})")
            self._log_audit(user_input, name, arguments, effective_level.value, "BLOCKED", block_reason)
            return ToolResult(
                tool_name=name,
                success=False,
                message=block_reason or "Boss, this operation is restricted for security reasons.",
                error="RESTRICTED_OPERATION"
            )

        # 2. Confirmation Required check
        if effective_level == PermissionLevel.CONFIRMATION_REQUIRED and not bypass_confirmation:
            prompt = self._build_confirmation_prompt(name, arguments)
            pending_action = confirmation_manager.request_confirmation(
                tool_name=name,
                arguments=arguments,
                prompt_message=prompt
            )
            self._log_audit(
                user_input, name, arguments, effective_level.value,
                "CONFIRMATION_REQUIRED", f"Pending ID: {pending_action.id}"
            )
            return ToolResult(
                tool_name=name,
                success=False,
                message=prompt,
                confirmation_required=True,
                confirmation_id=pending_action.id
            )

        # 3. Validate Arguments against Pydantic Schema
        try:
            validated_args = tool.args_schema(**arguments).model_dump()
        except ValidationError as val_err:
            err_str = str(val_err)
            logger.error(f"Validation error executing {name}: {err_str}")
            self._log_audit(user_input, name, arguments, effective_level.value, "FAILED", err_str)
            return ToolResult(
                tool_name=name,
                success=False,
                message="Boss, the arguments for that command were invalid.",
                error=err_str
            )

        # 4. Execute tool
        try:
            result = tool.execute(**validated_args)
            status_str = "SUCCESS" if result.success else "FAILED"
            self._log_audit(
                user_input, name, validated_args, effective_level.value,
                status_str, result.message or result.error
            )
            return result
        except Exception as exc:
            logger.exception(f"Unexpected error executing tool '{name}': {exc}")
            err_desc = f"{type(exc).__name__}: {str(exc)}"
            self._log_audit(user_input, name, validated_args, effective_level.value, "FAILED", err_desc)
            return ToolResult(
                tool_name=name,
                success=False,
                message=f"Boss, an unexpected error occurred while executing {name}.",
                error=err_desc
            )

    def _build_confirmation_prompt(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Create a user-friendly confirmation question."""
        if tool_name in ["delete_file_or_folder", "remove_directory"]:
            path = args.get("path", "the specified target")
            return f"Boss, this will permanently delete '{path}'. Should I continue?"
        if tool_name == "clean_logs":
            return "Boss, this will inspect and clean eligible log files while strictly protecting security audit records. Should I proceed?"
        if tool_name == "shutdown_system":
            return "Boss, this will shut down your computer. Should I proceed?"
        if tool_name == "restart_system":
            return "Boss, this will restart your computer. Should I proceed?"
        if tool_name == "send_email":
            to = args.get("to", "recipient")
            subj = args.get("subject", "(no subject)")
            return f"Boss, this will send an email to {to} with subject '{subj}'. Should I proceed with sending?"
        return f"Boss, executing '{tool_name}' requires your confirmation. Should I continue?"

    def _log_audit(
        self,
        user_input: str,
        tool_name: str,
        params: Dict[str, Any],
        permission_level: str,
        status: str,
        result_summary: Optional[str]
    ) -> None:
        """Record structured audit entry in SQLite."""
        try:
            clean_input = SecurityInspector.sanitize_log_message(user_input)
            clean_params = SecurityInspector.sanitize_log_message(json.dumps(params))
            with get_db_context() as db:
                audit = AuditLog(
                    user_input=clean_input,
                    tool_name=tool_name,
                    parameters_json=clean_params,
                    permission_level=permission_level,
                    status=status,
                    result_summary=result_summary
                )
                db.add(audit)
        except Exception as ex:
            logger.error(f"Failed to write audit log: {ex}")

tool_registry = ToolRegistry()
