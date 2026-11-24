"""Core DADUS Agent implementation.
Coordinates perception, understanding, tool routing, permissions, execution, and response synthesis.
"""
import uuid
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.agent.state import AgentSessionState, PendingClarification
from app.agent.router import intent_router, PlannedToolCall
from app.agent.planner import task_planner
from app.agent.context import ContextResolver
from app.agent.clarification import ClarificationEngine
from app.tools.registry import tool_registry
from app.tools.base import ToolResult
from app.security.confirmations import confirmation_manager
from app.database.database import get_db_context
from app.database.models import SessionRecord

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
        if sid in self._sessions:
            return self._sessions[sid]

        # Attempt to restore from persistent SQLite storage
        try:
            with get_db_context() as db:
                rec = db.query(SessionRecord).filter(SessionRecord.session_id == sid).first()
                if rec and rec.state_json:
                    state_dict = json.loads(rec.state_json)
                    session = AgentSessionState(**state_dict)
                    self._sessions[sid] = session
                    logger.info(f"Restored persisted session [{sid}] from database.")
                    return session
        except Exception as ex:
            logger.debug(f"Could not load persisted session [{sid}]: {ex}")

        new_sess = AgentSessionState(session_id=sid)
        self._sessions[sid] = new_sess
        return new_sess

    def _persist_session(self, session: AgentSessionState) -> None:
        """Persists session state into SQLite for crash and reboot recovery."""
        try:
            with get_db_context() as db:
                rec = db.query(SessionRecord).filter(SessionRecord.session_id == session.session_id).first()
                state_data = session.model_dump() if hasattr(session, "model_dump") else session.dict()
                state_json = json.dumps(state_data)
                if rec:
                    rec.state_json = state_json
                    rec.updated_at = datetime.utcnow()
                else:
                    rec = SessionRecord(
                        session_id=session.session_id,
                        state_json=state_json,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(rec)
                db.flush()
        except Exception as ex:
            logger.debug(f"Error persisting session [{session.session_id}]: {ex}")

    def _execute_and_observe_tool(
        self,
        session: AgentSessionState,
        tool_name: str,
        arguments: Dict[str, Any],
        user_input: str,
        bypass_confirmation: bool = False
    ) -> AgentResponse:
        """Centralized, resilient execution with permission verification and context entity tracking."""
        session.status = "EXECUTING"

        # Check lock screen restriction
        from app.security.lock_screen import check_lock_screen_restriction
        lock_refusal = check_lock_screen_restriction(tool_name)
        if lock_refusal:
            session.add_assistant_message(lock_refusal)
            return AgentResponse(text=lock_refusal, status="DONE")

        tool_result = tool_registry.execute_tool(
            name=tool_name,
            arguments=arguments,
            user_input=user_input,
            bypass_confirmation=bypass_confirmation
        )

        # 1. Clarification needed
        if tool_result.needs_clarification:
            session.status = "WAITING_CLARIFICATION"
            target_tool = tool_result.follow_up_tool or tool_name
            session.pending_clarification = PendingClarification(
                tool_name=target_tool,
                arguments=dict(arguments),
                clarification_type=tool_result.clarification_type or "app_choice",
                options=tool_result.options or []
            )
            session.add_assistant_message(tool_result.message)
            return AgentResponse(
                text=tool_result.message,
                status="WAITING_CLARIFICATION",
                tool_called=tool_name,
                tool_result=tool_result.to_dict(),
                needs_clarification=True,
                options=tool_result.options
            )

        # 2. Confirmation required
        if tool_result.confirmation_required:
            session.status = "WAITING_CONFIRMATION"
            session.pending_confirmation_id = tool_result.confirmation_id
            session.add_assistant_message(tool_result.message)
            return AgentResponse(
                text=tool_result.message,
                status="WAITING_CONFIRMATION",
                tool_called=tool_name,
                tool_result=tool_result.to_dict(),
                needs_confirmation=True,
                confirmation_id=tool_result.confirmation_id
            )

        # 3. Successful execution: record dynamic context entities & last action
        session.record_tool_action(tool_name, arguments, tool_result.to_dict())
        session.status = "DONE"
        reply_text = tool_result.message or "Done, boss."
        session.add_assistant_message(reply_text)

        return AgentResponse(
            text=reply_text,
            status="DONE",
            tool_called=tool_name,
            tool_result=tool_result.to_dict()
        )

    def process_input(self, user_text: str, session_id: Optional[str] = None) -> AgentResponse:
        """Process user input through the intent router, security inspector, and tool execution pipeline."""
        session = self.get_or_create_session(session_id)
        clean_text = user_text.strip()
        session.add_user_message(clean_text)
        try:
            return self._process_input_internal(session, clean_text)
        finally:
            self._persist_session(session)

    def _process_input_internal(self, session: AgentSessionState, clean_text: str) -> AgentResponse:
        lower_input = clean_text.lower()

        logger.info(f"DADUS received [{session.session_id}]: '{clean_text}'")

        # Step 1: Check for pending user confirmation (e.g. destructive actions)
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
                        return self._execute_and_observe_tool(
                            session=session,
                            tool_name=action.tool_name,
                            arguments=action.arguments,
                            user_input=clean_text,
                            bypass_confirmation=True
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

        # Step 2: Conversational Meta Queries (discussion history recall, past activity logs)
        meta_reply = ContextResolver.resolve_meta_query(clean_text, session)
        if meta_reply:
            session.add_assistant_message(meta_reply)
            return AgentResponse(text=meta_reply, status="DONE")

        # Step 3: Check for pending clarification (e.g. contact or music app disambiguation)
        if session.pending_clarification:
            pending = session.pending_clarification
            target_tool, target_args, response_msg, is_resolved = ClarificationEngine.resolve_pending(pending, clean_text)
            if is_resolved and target_tool:
                session.pending_clarification = None
                return self._execute_and_observe_tool(
                    session=session,
                    tool_name=target_tool,
                    arguments=target_args or {},
                    user_input=clean_text
                )
            else:
                if ClarificationEngine.is_cancellation(lower_input):
                    session.pending_clarification = None
                    session.add_assistant_message(response_msg or "Understood, boss. Cancelled.")
                    return AgentResponse(text=response_msg or "Understood, boss. Cancelled.", status="READY")
                else:
                    msg = response_msg or f"Boss, please specify: {', '.join(pending.options)}."
                    session.add_assistant_message(msg)
                    return AgentResponse(text=msg, status="WAITING_CLARIFICATION", needs_clarification=True, options=pending.options)

        # Step 4: Contextual Pronoun / Repetition Resolution ('open it', 'close that', 'make it louder', 'do it again')
        ctx_tool, ctx_args, ctx_direct = ContextResolver.resolve_contextual_reference(clean_text, session)
        if ctx_direct:
            session.add_assistant_message(ctx_direct)
            return AgentResponse(text=ctx_direct, status="DONE" if "no previous" not in ctx_direct else "READY")
        elif ctx_tool:
            return self._execute_and_observe_tool(
                session=session,
                tool_name=ctx_tool,
                arguments=ctx_args or {},
                user_input=clean_text
            )

        # Step 5: Multi-Step Execution Planning
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
                for step in plan.steps:
                    session.record_tool_action(step.tool_name, step.arguments, {})
                full_response = f"{plan.explanation}\n\nExecution Status:\n{final_msg}"
                session.add_assistant_message(full_response)
                return AgentResponse(
                    text=full_response,
                    status="DONE" if success else "ERROR",
                    tool_called=plan.steps[0].tool_name if plan.steps else None,
                    tool_result={"plan": plan.model_dump(), "results": step_results}
                )

        # Step 6: Intent Understanding & Single Tool Planning
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

        # Step 7: Tool Execution & Observation
        return self._execute_and_observe_tool(
            session=session,
            tool_name=planned_call.tool_name,
            arguments=planned_call.arguments,
            user_input=clean_text
        )

dadus_agent = DadusAgent()
