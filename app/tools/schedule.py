"""Schedule and calendar tools backed by SQLite."""
from datetime import datetime, date, timedelta
import logging
from typing import Optional, List
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.database.database import get_db_context
from app.database.models import ScheduleItem
from app.tools.reminders import parse_natural_time

logger = logging.getLogger("DADUS.Schedule")

# ==========================================
# Tool: get_today_schedule
# ==========================================
class GetScheduleInput(BaseModel):
    target_date: Optional[str] = Field(default=None, description="Date to check, e.g. 'today', 'tomorrow', '2026-10-30'")

class GetTodayScheduleTool(BaseTool):
    name = "get_today_schedule"
    description = "Retrieves the user's schedule and events for today or a specific date."
    permission_level = PermissionLevel.SAFE
    args_schema = GetScheduleInput

    def execute(self, target_date: Optional[str] = None) -> ToolResult:
        query_date = date.today()
        day_label = "today"

        if target_date:
            clean = target_date.strip().lower()
            if clean == "tomorrow":
                query_date += timedelta(days=1)
                day_label = "tomorrow"
            elif clean != "today":
                try:
                    query_date = datetime.strptime(clean, "%Y-%m-%d").date()
                    day_label = query_date.strftime("%B %d")
                except ValueError:
                    pass

        with get_db_context() as db:
            items = db.query(ScheduleItem).filter(
                ScheduleItem.schedule_date == query_date,
                ScheduleItem.status != "cancelled"
            ).order_by(ScheduleItem.start_time.asc()).all()

            if not items:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message=f"Boss, your schedule is clear for {day_label}.",
                    data={"date": query_date.isoformat(), "items": []}
                )

            lines = []
            for item in items:
                start_str = item.start_time.strftime("%I:%M %p")
                end_str = f" - {item.end_time.strftime('%I:%M %p')}" if item.end_time else ""
                lines.append(f"• {start_str}{end_str}: {item.title}")

            msg = f"Boss, here is your schedule for {day_label}:\n" + "\n".join(lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data={"date": query_date.isoformat(), "items": [it.to_dict() for it in items]}
            )

# ==========================================
# Tool: create_schedule_item
# ==========================================
class CreateScheduleItemInput(BaseModel):
    title: str = Field(description="Title of the event or activity, e.g. 'Gym', 'Team Sync'")
    start_time: str = Field(description="Start time, e.g. '5 PM', 'tomorrow 10 AM'")
    end_time: Optional[str] = Field(default=None, description="Optional end time, e.g. '6 PM'")

class CreateScheduleItemTool(BaseTool):
    name = "create_schedule_item"
    description = "Adds an event or calendar appointment to the user's schedule."
    permission_level = PermissionLevel.SAFE
    args_schema = CreateScheduleItemInput

    def execute(self, title: str, start_time: str, end_time: Optional[str] = None) -> ToolResult:
        try:
            start_dt = parse_natural_time(start_time)
            end_dt = parse_natural_time(end_time) if end_time else (start_dt + timedelta(hours=1))

            with get_db_context() as db:
                item = ScheduleItem(
                    title=title.strip(),
                    schedule_date=start_dt.date(),
                    start_time=start_dt,
                    end_time=end_dt,
                    status="scheduled"
                )
                db.add(item)
                db.flush()

            time_str = start_dt.strftime("%I:%M %p on %A, %B %d")
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Added '{title}' to your schedule for {time_str}, boss.",
                data={"title": title, "start_time": start_dt.isoformat(), "end_time": end_dt.isoformat()}
            )
        except Exception as ex:
            logger.error(f"Failed to create schedule item: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't add that to your schedule.",
                error=str(ex)
            )
