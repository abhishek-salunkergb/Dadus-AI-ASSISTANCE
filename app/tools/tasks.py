"""Personal productivity and task management tools for DADUS."""
from datetime import datetime, date, timedelta
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.database.database import get_db_context
from app.database.models import TaskItem, Reminder, ScheduleItem
from app.tools.reminders import parse_natural_time

logger = logging.getLogger("DADUS.Tasks")

# ==========================================
# Tool: create_task
# ==========================================
class CreateTaskInput(BaseModel):
    title: str = Field(description="Title of the task to complete, e.g. 'complete my Django project'")
    priority: Optional[str] = Field(default="medium", description="Priority level: 'high', 'medium', or 'low'")
    due_date: Optional[str] = Field(default=None, description="Optional due date, e.g. 'tomorrow', 'Friday 5 PM'")
    description: Optional[str] = Field(default=None, description="Optional extra details for the task")

class CreateTaskTool(BaseTool):
    name = "create_task"
    description = "Creates a persistent productivity task with priority and optional due date."
    permission_level = PermissionLevel.SAFE
    args_schema = CreateTaskInput

    def execute(
        self,
        title: str,
        priority: Optional[str] = "medium",
        due_date: Optional[str] = None,
        description: Optional[str] = None
    ) -> ToolResult:
        try:
            due_dt = parse_natural_time(due_date) if due_date else None
            prio = (priority or "medium").lower()
            if prio not in ["high", "medium", "low"]:
                prio = "medium"

            with get_db_context() as db:
                task = TaskItem(
                    title=title.strip(),
                    description=description,
                    priority=prio,
                    status="pending",
                    due_date=due_dt
                )
                db.add(task)
                db.flush()
                task_data = task.to_dict()

            due_str = f" due {due_dt.strftime('%b %d at %I:%M %p')}" if due_dt else ""
            msg = f"Task created: '{title}' (priority: {prio}{due_str}), boss."
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data=task_data
            )
        except Exception as ex:
            logger.error(f"Failed to create task: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't save that task.",
                error=str(ex)
            )

# ==========================================
# Tool: list_tasks
# ==========================================
class ListTasksInput(BaseModel):
    status: Optional[str] = Field(default="pending", description="Filter by status: 'pending', 'completed', 'all'")
    priority: Optional[str] = Field(default=None, description="Filter by priority: 'high', 'medium', 'low'")

class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = "Lists user tasks and pending work items."
    permission_level = PermissionLevel.SAFE
    args_schema = ListTasksInput

    def execute(self, status: Optional[str] = "pending", priority: Optional[str] = None) -> ToolResult:
        with get_db_context() as db:
            query = db.query(TaskItem)
            if status and status != "all":
                query = query.filter(TaskItem.status == status)
            if priority:
                query = query.filter(TaskItem.priority == priority.lower())

            tasks = query.order_by(
                TaskItem.priority.desc(),
                TaskItem.created_at.asc()
            ).all()

            if not tasks:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message="Boss, you have no pending tasks.",
                    data={"tasks": []}
                )

            lines = []
            for t in tasks:
                prio_tag = f"[{t.priority.upper()}]"
                due_info = f" (due: {t.due_date.strftime('%b %d')})" if t.due_date else ""
                lines.append(f"• {prio_tag} {t.title}{due_info}")

            msg = "Here are your tasks, boss:\n" + "\n".join(lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data={"tasks": [t.to_dict() for t in tasks]}
            )

# ==========================================
# Tool: complete_task
# ==========================================
class CompleteTaskInput(BaseModel):
    task_id_or_title: str = Field(description="ID or title of the task to mark completed")

class CompleteTaskTool(BaseTool):
    name = "complete_task"
    description = "Marks a task as completed."
    permission_level = PermissionLevel.SAFE
    args_schema = CompleteTaskInput

    def execute(self, task_id_or_title: str) -> ToolResult:
        query_val = task_id_or_title.strip()
        with get_db_context() as db:
            task = None
            if query_val.isdigit():
                task = db.query(TaskItem).filter(TaskItem.id == int(query_val)).first()
            if not task:
                task = db.query(TaskItem).filter(TaskItem.title.ilike(f"%{query_val}%")).first()

            if not task:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=f"Boss, I couldn't find a task matching '{query_val}'.",
                    error="TASK_NOT_FOUND"
                )

            task.status = "completed"
            task.completed_at = datetime.utcnow()
            db.flush()
            task_data = task.to_dict()

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Marked task '{task_data['title']}' as completed, boss.",
            data=task_data
        )

# ==========================================
# Tool: get_daily_briefing
# ==========================================
class GetDailyBriefingInput(BaseModel):
    pass

class GetDailyBriefingTool(BaseTool):
    name = "get_daily_briefing"
    description = "Delivers an executive morning briefing summarizing schedule, tasks, reminders, and system status."
    permission_level = PermissionLevel.SAFE
    args_schema = GetDailyBriefingInput

    def execute(self) -> ToolResult:
        today = date.today()
        now = datetime.now()
        greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 17 else "Good evening")

        with get_db_context() as db:
            # 1. Schedule items
            sched_items = db.query(ScheduleItem).filter(
                ScheduleItem.schedule_date == today,
                ScheduleItem.status != "cancelled"
            ).order_by(ScheduleItem.start_time.asc()).all()
            s_lines = [f"{it.start_time.strftime('%I:%M %p')}: {it.title}" for it in sched_items]
            sched_count = len(sched_items)

            # 2. Pending tasks
            tasks = db.query(TaskItem).filter(TaskItem.status == "pending").order_by(TaskItem.priority.desc()).all()
            high_prio = [t.title for t in tasks if t.priority == "high"]
            task_count = len(tasks)

            # 3. Active reminders
            reminders = db.query(Reminder).filter(Reminder.status == "pending").all()
            reminder_count = len(reminders)

        briefing_parts = [f"{greeting}, boss."]

        # Schedule section
        if s_lines:
            briefing_parts.append(f"You have {sched_count} events on your schedule today: " + ", ".join(s_lines) + ".")
        else:
            briefing_parts.append("Your schedule is clear today.")

        # Tasks section
        if task_count > 0:
            if high_prio:
                briefing_parts.append(f"You have {task_count} pending tasks, with high priority on: {', '.join(high_prio)}.")
            else:
                briefing_parts.append(f"You have {task_count} pending tasks.")
        else:
            briefing_parts.append("You have no pending tasks.")

        # Reminders section
        if reminder_count > 0:
            briefing_parts.append(f"You have {reminder_count} active reminders queued.")

        full_message = " ".join(briefing_parts)
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=full_message,
            data={
                "schedule_count": sched_count,
                "task_count": task_count,
                "reminder_count": reminder_count,
                "date": today.isoformat()
            }
        )
