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

class TaskPlanner:
    """Plans and coordinates multi-step agent workflows."""

    @classmethod
    def is_multi_step_request(cls, text: str) -> bool:
        """Detect if user query requires a sequence of multiple tool actions."""
        lower = text.lower()

        # Multi-step conjunctions and compound requests
        indicators = [
            "and open its github",
            "and open in vs code",
            "and open it in",
            "and take a screenshot",
            "and play",
            "and set volume",
            "explain what you are doing",
            "before executing"
        ]
        return any(ind in lower for ind in indicators)

    @classmethod
    def create_plan(cls, text: str) -> Optional[ExecutionPlan]:
        """Decompose request into a structured multi-step execution plan."""
        lower = text.lower()

        # Explicit request to explain plan before executing
        if any(p in lower for p in ["explain what you are doing before executing", "explain before executing", "explain your plan"]):
            # Check if there is also an action specified
            proj = "Python"
            if "django" in lower:
                proj = "Django"
            elif "python" in lower:
                proj = "Python"
            
            steps = []
            if "github" in lower or "vs code" in lower or "open" in lower:
                steps = [
                    PlanStep(
                        step_number=1,
                        tool_name="find_project_and_open",
                        arguments={"project_name": proj, "editor": "Visual Studio Code"},
                        description=f"Locate your '{proj}' project and open it in Visual Studio Code"
                    )
                ]
                if "github" in lower:
                    steps.append(PlanStep(
                        step_number=2,
                        tool_name="open_project_github",
                        arguments={"project_name": proj},
                        description=f"Open GitHub repository for '{proj}' in your browser"
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

        # Compound scenario: "Find my Python project, open it in VS Code, and open its GitHub repository."
        if "github" in lower and any(w in lower for w in ["open in vs code", "open it in vs code", "open in code", "editor"]):
            project_match = re.search(r"find\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)(?:\s+project)?(?:,|\sand|\sto)", lower)
            proj = project_match.group(1).strip() if project_match else "Python"
            if proj.lower() in ["my", "the", ""]:
                proj = "Python"

            steps = [
                PlanStep(
                    step_number=1,
                    tool_name="find_project_and_open",
                    arguments={"project_name": proj, "editor": "Visual Studio Code"},
                    description=f"Locate your '{proj}' project and open it in Visual Studio Code"
                ),
                PlanStep(
                    step_number=2,
                    tool_name="open_project_github",
                    arguments={"project_name": proj},
                    description=f"Find the git origin configuration and open the GitHub repository for '{proj}'"
                )
            ]

            explanation = (
                f"Boss, here is my plan:\n"
                f"1. Search your computer to find the '{proj}' project folder and launch it in Visual Studio Code.\n"
                f"2. Inspect the project's repository configuration and open its GitHub page in your browser."
            )

            return ExecutionPlan(goal=text, explanation=explanation, steps=steps)

        # Compound scenario: Project search + VS Code open
        if any(w in lower for w in ["find my", "open my"]) and any(w in lower for w in ["in vs code", "in code editor"]):
            project_match = re.search(r"(?:find|open)\s+(?:my\s+)?([a-zA-Z0-9_\s]+?)(?:\s+project)?(?:\s+and\s+open|\sin\s+vs\s+code)", lower)
            proj = project_match.group(1).strip() if project_match else "project"
            steps = [
                PlanStep(
                    step_number=1,
                    tool_name="find_project_and_open",
                    arguments={"project_name": proj, "editor": "Visual Studio Code"},
                    description=f"Locate '{proj}' and launch it in Visual Studio Code"
                )
            ]
            explanation = f"Boss, I will locate your '{proj}' directory and open it directly in VS Code."
            return ExecutionPlan(goal=text, explanation=explanation, steps=steps)

        return None

    @classmethod
    def execute_plan(cls, plan: ExecutionPlan, user_input: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Execute each step in the plan sequentially with verification."""
        results = []
        messages = []
        all_success = True

        for step in plan.steps:
            logger.info(f"Executing Plan Step {step.step_number}: {step.tool_name} ({step.description})")
            res = tool_registry.execute_tool(
                name=step.tool_name,
                arguments=step.arguments,
                user_input=user_input
            )
            results.append({"step": step.step_number, "tool": step.tool_name, "result": res.to_dict()})

            if not res.success:
                all_success = False
                messages.append(f"Step {step.step_number} encountered an issue: {res.message}")
                break
            else:
                messages.append(res.message)

        final_msg = " ".join(messages)
        return all_success, final_msg, results

task_planner = TaskPlanner()
