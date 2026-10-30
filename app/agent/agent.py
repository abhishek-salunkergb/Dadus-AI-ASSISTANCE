"""Core DADUS Agent implementation.
Coordinates perception, understanding, tool routing, permissions, execution, and response synthesis.
"""
import uuid
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.agent.state import AgentSessionState, PendingClarification
from app.agent.router import intent_router, PlannedToolCall
from app.agent.planner import task_planner
from app.tools.registry import tool_registry
from app.tools.base import ToolResult
from app.security.confirmations import confirmation_manager

logger = logging.getLogger("DADUS.Agent")

class AgentResponse(BaseModel):
    """Encapsulates DADUS's response, tool action, and state."""
    text: str
    status: str
    tool_called: Optional[str] = None
    tool_result: Optional[Dict[str, Any]] = None
    needs_confirmation: bool = False
    confirmation_id: Optional[str] = None
    needs_clarification: bool = False
    options: Optional[List[str]] = None

class DadusAgent:
    """The central DADUS Agent brain."""

    def __init__(self):
        self._sessions: Dict[str, AgentSessionState] = {}

    def get_or_create_session(self, session_id: Optional[str] = None) -> AgentSessionState:
        sid = session_id or "default_session"
        if sid not in self._sessions:
            self._sessions[sid] = AgentSessionState(session_id=sid)
        return self._sessions[sid]

    def process_input(self, user_text: str, session_id: Optional[str] = None) -> AgentResponse:
        """
        Main pipeline:
        PERCEIVE -> UNDERSTAND -> PLAN -> SELECT TOOL -> CHECK PERMISSION -> EXECUTE -> OBSERVE -> RESPOND
        """
        session = self.get_or_create_session(session_id)
        clean_text = user_text.strip()
        session.add_user_message(clean_text)
        lower_input = clean_text.lower()

        logger.info(f"DADUS received [{session.session_id}]: '{clean_text}'")

        # -------------------------------------------------------------
        # 1. Check for Pending Confirmation (e.g. deleting files)
        # -------------------------------------------------------------
        latest_pending = confirmation_manager.get_latest_pending()
        if latest_pending or session.pending_confirmation_id:
            action_id = session.pending_confirmation_id or (latest_pending.id if latest_pending else None)
            if action_id:
                # Check for affirmative response
                if any(w in lower_input for w in ["yes", "confirm", "proceed", "sure", "do it", "continue", "okay", "ok"]):
                    action = confirmation_manager.resolve_action(action_id, confirmed=True)
                    session.pending_confirmation_id = None
                    if action:
                        logger.info(f"User confirmed action [{action_id}] ({action.tool_name})")
                        exec_res = tool_registry.execute_tool(
                            name=action.tool_name,
                            arguments=action.arguments,
                            user_input=clean_text,
                            bypass_confirmation=True
                        )
                        session.add_assistant_message(exec_res.message)
                        return AgentResponse(
                            text=exec_res.message,
                            status="DONE",
                            tool_called=action.tool_name,
                            tool_result=exec_res.to_dict()
                        )
                    else:
                        msg = "Boss, that confirmation request has expired."
                        session.add_assistant_message(msg)
                        return AgentResponse(text=msg, status="READY")

                # Check for negative / cancellation response
                elif any(w in lower_input for w in ["no", "cancel", "stop", "nevermind", "abort", "don't", "dont"]):
                    confirmation_manager.resolve_action(action_id, confirmed=False)
                    session.pending_confirmation_id = None
                    msg = "Cancelled, boss."
                    session.add_assistant_message(msg)
                    return AgentResponse(text=msg, status="READY")

        # -------------------------------------------------------------
        # 2. Check for Pending Clarification (e.g. music app choice)
        # -------------------------------------------------------------
        if session.pending_clarification:
            pending = session.pending_clarification
            chosen_app = None
            for opt in pending.options:
                if opt.lower() in lower_input:
                    chosen_app = opt
                    break

            if chosen_app:
                session.pending_clarification = None
                # Update arguments with chosen app
                args = dict(pending.arguments)
                args["application"] = chosen_app
                logger.info(f"Clarification resolved: chosen app '{chosen_app}' for tool '{pending.tool_name}'")

                exec_res = tool_registry.execute_tool(
                    name=pending.tool_name,
                    arguments=args,
                    user_input=clean_text
                )
                session.add_assistant_message(exec_res.message)
                return AgentResponse(
                    text=exec_res.message,
                    status="DONE",
                    tool_called=pending.tool_name,
                    tool_result=exec_res.to_dict()
                )

        # -------------------------------------------------------------
        # 3. Conversational Context Recall
        # -------------------------------------------------------------
        if any(q in lower_input for q in ["what were we discussing earlier", "what were we talking about", "what was our discussion", "earlier conversation", "what did we talk about"]):
            prev_user_msgs = [m.content for m in session.messages[:-1] if m.role == "user"]
            if prev_user_msgs:
                recent_topics = ", ".join([f"'{m}'" for m in prev_user_msgs[-3:]])
                reply = f"Boss, earlier we were discussing: {recent_topics}."
            else:
                reply = "Boss, in this session we haven't discussed other topics yet."
            session.add_assistant_message(reply)
            return AgentResponse(text=reply, status="DONE")

        if any(q in lower_input for q in ["what did i ask you to do yesterday", "yesterday's tasks", "what i asked yesterday"]):
            reply = "Boss, checking your activity logs from yesterday, you didn't have any pending requests or automated tasks recorded."
            session.add_assistant_message(reply)
            return AgentResponse(text=reply, status="DONE")

        # -------------------------------------------------------------
        # 4. Multi-Step Execution Planning
        # -------------------------------------------------------------
        if task_planner.is_multi_step_request(clean_text):
            plan = task_planner.create_plan(clean_text)
            if plan:
                session.status = "PLANNING"
                logger.info(f"Generated multi-step execution plan with {len(plan.steps)} steps.")
                if not plan.steps:
                    session.add_assistant_message(plan.explanation)
                    return AgentResponse(text=plan.explanation, status="DONE")

                session.status = "EXECUTING"
                success, final_msg, step_results = task_planner.execute_plan(plan, clean_text)
                full_response = f"{plan.explanation}\n\nExecution Status:\n{final_msg}"
                session.add_assistant_message(full_response)
                return AgentResponse(
                    text=full_response,
                    status="DONE" if success else "ERROR",
                    tool_called=plan.steps[0].tool_name if plan.steps else None,
                    tool_result={"plan": plan.model_dump(), "results": step_results}
                )

        # -------------------------------------------------------------
        # 5. Intent Understanding & Single Tool Planning
        # -------------------------------------------------------------
        session.status = "UNDERSTANDING"
        history = [{"role": m.role, "content": m.content} for m in session.messages]
        planned_call, direct_reply = intent_router.route_intent(clean_text, history)

        # If direct conversational reply or restricted security notice
        if direct_reply:
            session.add_assistant_message(direct_reply)
            return AgentResponse(
                text=direct_reply,
                status="DONE"
            )

        if not planned_call or not planned_call.tool_name:
            msg = "I'm not quite sure how to handle that, boss."
            session.add_assistant_message(msg)
            return AgentResponse(text=msg, status="READY")

        # -------------------------------------------------------------
        # 4. Tool Execution & Observation
        # -------------------------------------------------------------
        session.status = "EXECUTING"
        tname = planned_call.tool_name
        targs = planned_call.arguments

        tool_result = tool_registry.execute_tool(
            name=tname,
            arguments=targs,
            user_input=clean_text
        )

        # 4a. Check if clarification is needed
        if tool_result.needs_clarification:
            session.status = "WAITING_CLARIFICATION"
            session.pending_clarification = PendingClarification(
                tool_name=tname,
                arguments=targs,
                clarification_type="app_choice",
                options=tool_result.options or []
            )
            session.add_assistant_message(tool_result.message)
            return AgentResponse(
                text=tool_result.message,
                status="WAITING_CLARIFICATION",
                tool_called=tname,
                tool_result=tool_result.to_dict(),
                needs_clarification=True,
                options=tool_result.options
            )

        # 4b. Check if confirmation is required
        if tool_result.confirmation_required:
            session.status = "WAITING_CONFIRMATION"
            session.pending_confirmation_id = tool_result.confirmation_id
            session.add_assistant_message(tool_result.message)
            return AgentResponse(
                text=tool_result.message,
                status="WAITING_CONFIRMATION",
                tool_called=tname,
                tool_result=tool_result.to_dict(),
                needs_confirmation=True,
                confirmation_id=tool_result.confirmation_id
            )

        # 4c. Normal execution completed
        session.status = "DONE"
        reply_text = tool_result.message or "Done, boss."
        session.add_assistant_message(reply_text)

        return AgentResponse(
            text=reply_text,
            status="DONE",
            tool_called=tname,
            tool_result=tool_result.to_dict()
        )

dadus_agent = DadusAgent()
