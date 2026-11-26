"""Intelligent multi-step tool planner for DADUS agent.
Decomposes compound goals into validated tool execution pipelines.
"""
from typing import List, Dict, Any, Optional, Tuple
import re
import logging
from pydantic import BaseModel, Field

from app.tools.registry import tool_registry
from app.tools.base import ToolResult

logger = logging.getLogger("DADUS.Planner")

class PlanStep(BaseModel):
    step_number: int
    tool_name: str
    arguments: Dict[str, Any]
    description: str

class ExecutionPlan(BaseModel):
    goal: str
    explanation: str
    steps: List[PlanStep]

def _resolve_template_val(val: Any, context: Dict[str, Any]) -> Any:
    """Recursively resolves dynamic references like {{step_1.path}}, {{step_1.data.key}}, {{last_step.file_path}}."""
    if isinstance(val, str):
        matches = re.findall(r"\{\{([^}]+)\}\}", val)
        if not matches:
            return val
        if len(matches) == 1 and val.strip() == f"{{{{{matches[0]}}}}}":
            expr = matches[0].strip()
            resolved = _lookup_in_context(expr, context)
            return resolved if resolved is not None else val
        res_str = val
        for expr in matches:
            resolved = _lookup_in_context(expr.strip(), context)
            res_str = res_str.replace(f"{{{{{expr}}}}}", str(resolved if resolved is not None else ""))
        return res_str
    elif isinstance(val, dict):
        return {k: _resolve_template_val(v, context) for k, v in val.items()}
    elif isinstance(val, list):
        return [_resolve_template_val(v, context) for v in val]
    return val

def _lookup_in_context(expr: str, context: Dict[str, Any]) -> Any:
    parts = expr.split(".")
    curr = context
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        elif hasattr(curr, part):
            curr = getattr(curr, part)
        else:
            return None
    return curr

def _extract_project_target(text: str) -> Optional[str]:
    """Dynamically extracts a target project name from compound natural language phrasing."""
    match = re.search(r"(?:find|open|locate)\s+(?:my\s+)?([a-zA-Z0-9_\-]+?)(?:\s+project)?(?:\s+and|\s+in|\sto|,|$)", text, re.IGNORECASE)
    if match:
        cand = match.group(1).strip()
        if cand.lower() not in ["my", "the", "a", "this", "our", ""]:
            return cand
    return None

def _extract_editor_target(text: str) -> str:
    """Extracts target code editor or queries user's preferred editor from persistent memory."""
    from app.memory.memory import memory_store
    lower = text.lower()
    if "cursor" in lower:
        return "Cursor"
    if "notepad" in lower:
        return "Notepad"
    if "pycharm" in lower:
        return "PyCharm"
    if any(w in lower for w in ["vs code", "vscode", "code"]):
        return "Visual Studio Code"
    return memory_store.get_preferred_code_editor() or "Visual Studio Code"


class TaskPlanner:
    """Plans and coordinates multi-step agent workflows."""

    @classmethod
    def is_multi_step_request(cls, text: str) -> bool:
        """Detect if user query requires a sequence of multiple tool actions."""
        lower = text.lower()
        if any(p in lower for p in ["explain what you are doing", "explain before executing", "explain your plan"]):
            return True
        if re.search(r"\b(?:and\s+then|then|and\s+also|after\s+that)\b", lower):
            return True
        # Only treat 'and' as multi-step if both sides look like distinct action clauses
        if re.search(r"\band\b", lower):
            clauses = [c.strip() for c in re.split(r"\band\b", lower) if c.strip()]
            if len(clauses) >= 2:
                action_verbs = r"^(?:please\s+|can\s+you\s+)?(?:open|launch|start|close|quit|play|pause|set|create|add|find|search|check|read|send|delete|take|wrap|resume|mute|unmute|lock|turn|remember|list|show)\b"
                action_clauses = sum(1 for c in clauses if re.search(action_verbs, c))
                return action_clauses >= 2
        return False

    @classmethod
    def create_plan(cls, text: str) -> Optional[ExecutionPlan]:
        """Decompose request into a structured multi-step execution plan."""
        lower = text.lower()
        proj = _extract_project_target(text)
        editor = _extract_editor_target(text)

        # 1. Meta-explanation request: User asks how multi-step workflows are evaluated
        if any(p in lower for p in ["explain what you are doing before executing", "explain before executing", "explain your plan"]):
            steps: List[PlanStep] = []
            if proj:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="find_project_and_open",
                    arguments={"project_name": proj, "editor": editor},
                    description=f"Locate '{proj}' project and open in {editor}"
                ))
                if "github" in lower:
                    steps.append(PlanStep(
                        step_number=2,
                        tool_name="open_project_github",
                        arguments={"project_name": proj},
                        description=f"Open GitHub repository for '{proj}' in browser"
                    ))

            explanation = (
                "Boss, before executing any multi-step task, here is my controlled procedure:\n"
                "1. Understand Intent: Break down your compound request into sequential steps.\n"
                "2. Resource Discovery: Locate project folders, git configurations, and target tools.\n"
                "3. Safety Check: Verify tool permissions and ensure non-destructive execution.\n"
                "4. Step-by-Step Execution: Run each tool in order, verifying success at every stage.\n"
                "5. Final Status: Report the outcome of all completed operations."
            )
            return ExecutionPlan(goal=text, explanation=explanation, steps=steps)

        # 2. Multi-step workflow: Locate project folder, open in editor, and launch git origin in browser
        if "github" in lower and any(w in lower for w in ["open in", "open it in", "code", "editor", "vscode", "vs code", "cursor", "pycharm"]):
            target_proj = proj or "current project"
            steps = [
                PlanStep(
                    step_number=1,
                    tool_name="find_project_and_open",
                    arguments={"project_name": target_proj, "editor": editor},
                    description=f"Locate '{target_proj}' project and open it in {editor}"
                ),
                PlanStep(
                    step_number=2,
                    tool_name="open_project_github",
                    arguments={"project_name": target_proj},
                    description=f"Find git origin configuration and open GitHub repository for '{target_proj}'"
                )
            ]
            explanation = (
                f"Boss, here is my plan:\n"
                f"1. Search your computer to find the '{target_proj}' project folder and launch it in {editor}.\n"
                f"2. Inspect the project's repository configuration and open its GitHub page in your browser."
            )
            return ExecutionPlan(goal=text, explanation=explanation, steps=steps)

        # 3. Single compound action: Project search + editor launch
        if any(w in lower for w in ["find my", "open my"]) and any(w in lower for w in ["in vs code", "in code editor", "in editor", "in cursor", "in pycharm"]):
            target_proj = proj or "project"
            steps = [
                PlanStep(
                    step_number=1,
                    tool_name="find_project_and_open",
                    arguments={"project_name": target_proj, "editor": editor},
                    description=f"Locate '{target_proj}' and launch it in {editor}"
                )
            ]
            explanation = f"Boss, I will locate your '{target_proj}' directory and open it directly in {editor}."
            return ExecutionPlan(goal=text, explanation=explanation, steps=steps)

        # 4. Generalized Sequential Intent Pipeline
        clauses = [c.strip() for c in re.split(r"\b(?:and\s+then|then|and\s+also|and)\b", text, flags=re.IGNORECASE) if c.strip()]
        if len(clauses) > 1:
            from app.agent.router import intent_router
            discovered_steps: List[PlanStep] = []
            for clause in clauses:
                sub_query = re.sub(r"^(?:please\s+|can\s+you\s+|dadus\s+|also\s+)", "", clause, flags=re.IGNORECASE).strip()
                if not sub_query:
                    continue
                planned, _ = intent_router.route_intent(sub_query, [])
                if planned and planned.tool_name:
                    step_num = len(discovered_steps) + 1
                    discovered_steps.append(PlanStep(
                        step_number=step_num,
                        tool_name=planned.tool_name,
                        arguments=planned.arguments,
                        description=f"{planned.tool_name.replace('_', ' ').title()} ({sub_query})"
                    ))

            if len(discovered_steps) >= 2:
                explanation = "Boss, executing your sequence of actions:\n" + "\n".join(
                    f"{s.step_number}. {s.description}" for s in discovered_steps
                )
                return ExecutionPlan(goal=text, explanation=explanation, steps=discovered_steps)

        return None

    @classmethod
    def execute_plan(cls, plan: ExecutionPlan, user_input: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Execute each step in the plan sequentially with DAG data-piping and verification."""
        results = []
        messages = []
        all_success = True
        pipeline_context: Dict[str, Any] = {}

        for step in plan.steps:
            from app.security.lock_screen import check_lock_screen_restriction
            lock_refusal = check_lock_screen_restriction(step.tool_name)
            if lock_refusal:
                all_success = False
                messages.append(lock_refusal)
                results.append({"step": step.step_number, "tool": step.tool_name, "error": "lock_screen_restriction"})
                break

            # 1. Resolve dynamic argument references (e.g. {{step_1.data.path}} or {{last_step.data.file_path}})
            resolved_args = _resolve_template_val(dict(step.arguments), pipeline_context)

            # 2. Dynamic Auto-piping: If a target parameter is missing but a preceding step produced a path/entity, pipe it forward
            if "last_step" in pipeline_context and isinstance(pipeline_context["last_step"], dict):
                last_data = pipeline_context["last_step"].get("data")
                if isinstance(last_data, dict):
                    piped_path = last_data.get("file_path") or last_data.get("path") or last_data.get("screenshot_path")
                    if piped_path:
                        if "path" in resolved_args and (not resolved_args["path"] or resolved_args["path"] == "file"):
                            resolved_args["path"] = piped_path
                        elif "file_path" in resolved_args and not resolved_args["file_path"]:
                            resolved_args["file_path"] = piped_path

                    piped_contact = last_data.get("contact")
                    if isinstance(piped_contact, dict):
                        piped_email = piped_contact.get("email")
                        if piped_email and "recipient" in resolved_args and not resolved_args["recipient"]:
                            resolved_args["recipient"] = piped_email

            logger.info(f"Executing Plan Step {step.step_number}: {step.tool_name} with resolved args={resolved_args}")
            res = tool_registry.execute_tool(
                name=step.tool_name,
                arguments=resolved_args,
                user_input=user_input
            )
            step_record = {"step": step.step_number, "tool": step.tool_name, "result": res.to_dict()}
            results.append(step_record)

            # Store in pipeline execution context for dependent future steps
            step_key = f"step_{step.step_number}"
            pipeline_context[step_key] = res.to_dict()
            pipeline_context["last_step"] = res.to_dict()

            if not res.success:
                all_success = False
                messages.append(f"Step {step.step_number} encountered an issue: {res.message}")
                break
            else:
                messages.append(res.message)

        final_msg = " ".join(messages)
        return all_success, final_msg, results

task_planner = TaskPlanner()
