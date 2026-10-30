"""Reminder creation and listing tools backed by SQLite."""
from datetime import datetime, timedelta
import re
import logging
from typing import Optional, List
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.database.database import get_db_context
from app.database.models import Reminder

logger = logging.getLogger("DADUS.Reminders")

def parse_natural_time(time_str: str) -> datetime:
    """Parses natural time expressions into a concrete datetime."""
    now = datetime.now()
    clean = time_str.strip().lower()

    # Relative minutes: "in 10 minutes"
    rel_min = re.search(r"in\s+(\d+)\s+min", clean)
    if rel_min:
        return now + timedelta(minutes=int(rel_min.group(1)))

    # Relative hours: "in 2 hours"
    rel_hr = re.search(r"in\s+(\d+)\s+hour", clean)
    if rel_hr:
        return now + timedelta(hours=int(rel_hr.group(1)))

    # "tomorrow at 7 pm" or "tomorrow 7pm"
    is_tomorrow = "tomorrow" in clean
    clean = clean.replace("tomorrow", "").replace("at", "").strip()

    # "7 pm", "7:30 pm", "7pm", "19:00"
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", clean)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3)

        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        target_date = now.date() + timedelta(days=1 if is_tomorrow else 0)
        target = datetime.combine(target_date, datetime.min.time()).replace(
            hour=hour, minute=minute, second=0
        )

        # If time passed today and "tomorrow" was not specified, schedule for today or tomorrow if already past
        if not is_tomorrow and target < now:
            target += timedelta(days=1)

        return target

    # Try ISO format
    try:
        return datetime.fromisoformat(time_str)
    except Exception:
        # Default: 1 hour from now
        return now + timedelta(hours=1)

# ==========================================
# Tool: create_reminder
# ==========================================
class CreateReminderInput(BaseModel):
    title: str = Field(description="Title or description of the reminder, e.g. 'study Python'")
    time: str = Field(description="Time for the reminder, e.g. '7 PM', 'tomorrow at 9 AM', 'every day at 8 AM'")
    recurrence: Optional[str] = Field(default="none", description="Recurrence: 'none', 'daily', 'weekly'")

class CreateReminderTool(BaseTool):
    name = "create_reminder"
    description = "Creates a persistent reminder or recurring reminder for a specific time."
    permission_level = PermissionLevel.SAFE
    args_schema = CreateReminderInput

    def execute(self, title: str, time: str, recurrence: Optional[str] = "none") -> ToolResult:
        try:
            time_lower = time.lower()
            rec = recurrence or "none"
            if "every day" in time_lower or "daily" in time_lower or "everyday" in time_lower:
                rec = "daily"
                time_clean = re.sub(r"\b(every\s*day|daily)\b", "", time, flags=re.IGNORECASE).strip()
            elif "every week" in time_lower or "weekly" in time_lower:
                rec = "weekly"
                time_clean = re.sub(r"\b(every\s*week|weekly)\b", "", time, flags=re.IGNORECASE).strip()
            else:
                time_clean = time

            target_dt = parse_natural_time(time_clean)
            with get_db_context() as db:
                reminder = Reminder(
                    title=title.strip(),
                    target_time=target_dt,
                    status="pending",
                    recurrence=rec
                )
                db.add(reminder)
                db.flush()

            time_formatted = target_dt.strftime("%I:%M %p")
            if rec == "daily":
                msg = f"I've set a daily reminder to '{title}' every day at {time_formatted}, boss."
            elif rec == "weekly":
                msg = f"I've set a weekly reminder to '{title}' at {time_formatted}, boss."
            else:
                full_dt = target_dt.strftime("%I:%M %p on %A, %B %d")
                msg = f"I've set a reminder to '{title}' for {full_dt}, boss."

            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data={"title": title, "target_time": target_dt.isoformat(), "recurrence": rec}
            )
        except Exception as ex:
            logger.error(f"Failed to create reminder: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't save that reminder.",
                error=str(ex)
            )

# ==========================================
# Tool: list_reminders
# ==========================================
class ListRemindersInput(BaseModel):
    status: Optional[str] = Field(default="pending", description="Filter by status: 'pending', 'completed', 'all'")

class ListRemindersTool(BaseTool):
    name = "list_reminders"
    description = "Lists user reminders."
    permission_level = PermissionLevel.SAFE
    args_schema = ListRemindersInput

    def execute(self, status: Optional[str] = "pending") -> ToolResult:
        with get_db_context() as db:
            query = db.query(Reminder)
            if status and status != "all":
                query = query.filter(Reminder.status == status)
            reminders = query.order_by(Reminder.target_time.asc()).all()

            if not reminders:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message="Boss, you have no pending reminders.",
                    data={"reminders": []}
                )

            lines = []
            for r in reminders:
                t_str = r.target_time.strftime("%I:%M %p (%b %d)")
                lines.append(f"• {r.title} at {t_str}")

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Here are your reminders, boss:\n" + "\n".join(lines),
                data={"reminders": [r.to_dict() for r in reminders]}
            )
