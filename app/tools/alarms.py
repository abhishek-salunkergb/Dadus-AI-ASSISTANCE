"""Alarm creation, listing, cancellation, and natural language time parsing for DADUS.
Backed by persistent SQLite storage and an independent background execution daemon.
"""
import re
import logging
from datetime import datetime, timedelta, time as dtime
from typing import Optional, List, Tuple, Dict, Any
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.database.database import get_db_context
from app.database.models import Alarm

logger = logging.getLogger("DADUS.Alarms")


def parse_natural_alarm_time(time_str: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parses complex natural-language time expressions into a concrete datetime.
    Supports:
      - "tomorrow at 6 AM", "tomorrow 6am", "tomorrow at 6:30 AM"
      - "6 AM", "6:30 AM", "7:30 PM", "8 PM", "11:45 PM"
      - "in 20 minutes", "in 1 hour", "in 45 mins", "in 90 seconds"
      - "240 o'clock", "240", "0630", "1430" (STT transcription of "two forty")
      - "6 o'clock", "8 o'clock"
    Returns (target_datetime, error_or_clarification_message).
    """
    if not time_str or not time_str.strip():
        return None, "Boss, what time would you like me to set the alarm for?"

    now = datetime.now()
    clean = time_str.strip().lower()

    # Normalize common spoken fillers and prefixes
    clean = re.sub(r"\b(please|for me|set|alarm|to|at)\b", " ", clean).strip()
    clean = re.sub(r"\s+", " ", clean)

    # 1. Relative time: "in X minutes", "in X hours", "in X seconds"
    rel_sec = re.search(r"\bin\s+(\d+)\s*(?:sec|second)s?\b", clean)
    if rel_sec:
        secs = int(rel_sec.group(1))
        return now + timedelta(seconds=secs), None

    rel_min = re.search(r"\bin\s+(\d+)\s*(?:min|minute)s?\b", clean)
    if rel_min:
        mins = int(rel_min.group(1))
        return now + timedelta(minutes=mins), None

    rel_hr = re.search(r"\bin\s+(\d+)\s*(?:hour|hr)s?\b", clean)
    if rel_hr:
        hrs = int(rel_hr.group(1))
        return now + timedelta(hours=hrs), None

    # Check for "tomorrow" reference
    is_tomorrow = "tomorrow" in clean
    clean = clean.replace("tomorrow", "").strip()

    # Check for morning / evening words
    is_morning = any(w in clean for w in ["morning"])
    is_evening = any(w in clean for w in ["evening", "night", "tonight"])
    clean = re.sub(r"\b(morning|evening|night|tonight)\b", "", clean).strip()

    hour: Optional[int] = None
    minute: int = 0
    ampm: Optional[str] = None

    # 2. STT compacted time: e.g. "240 o'clock", "240", "0630", "1430"
    # Matches 3 or 4 digits like 240, 0240, 1430
    stt_compact = re.search(r"\b(\d{1,2})(\d{2})\s*(?:o'?clock)?\s*(am|pm)?\b", clean)
    if stt_compact and (int(stt_compact.group(1)) <= 23 and int(stt_compact.group(2)) <= 59):
        hour = int(stt_compact.group(1))
        minute = int(stt_compact.group(2))
        ampm = stt_compact.group(3)

    # 3. Standard "H:MM [am/pm]" or "H [am/pm]"
    if hour is None:
        std_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:o'?clock)?\b", clean)
        if std_match:
            cand_hr = int(std_match.group(1))
            cand_min = int(std_match.group(2)) if std_match.group(2) else 0
            if 0 <= cand_hr <= 24 and 0 <= cand_min <= 59:
                hour = cand_hr
                minute = cand_min
                ampm = std_match.group(3)

    # 4. "6 o'clock", "8 o'clock"
    if hour is None:
        oclock_match = re.search(r"\b(\d{1,2})\s*o'?clock\b", clean)
        if oclock_match:
            hour = int(oclock_match.group(1))
            minute = 0

    if hour is None:
        return None, f"Boss, I couldn't understand '{time_str}'. Please tell me a time like '6 AM', '7:30 PM', or 'in 15 minutes'."

    # Validate hour bounds
    if hour > 24 or (hour > 12 and ampm in ["am", "pm"]):
        return None, f"Boss, '{time_str}' is not a valid time. Hours must be between 1 and 12 with AM/PM, or 0 and 23."

    # Convert 12-hour format with AM/PM or contextual morning/evening
    if not ampm:
        if is_morning:
            ampm = "am"
        elif is_evening:
            ampm = "pm"

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    # If AM/PM was not provided and hour < 12: determine closest upcoming occurrence
    if ampm is None and hour <= 12:
        # Check both AM and PM candidates
        cand_am = hour if hour != 12 else 0
        cand_pm = hour + 12 if hour < 12 else 12

        target_am_today = datetime.combine(now.date(), dtime(hour=cand_am, minute=minute, second=0))
        target_pm_today = datetime.combine(now.date(), dtime(hour=cand_pm, minute=minute, second=0))

        if is_tomorrow:
            # Tomorrow without AM/PM: default to morning if hour >= 5 and <= 11, else afternoon
            hour = cand_am if (5 <= cand_am <= 11) else cand_pm
        else:
            # Choose the next upcoming one today
            if target_am_today > now:
                hour = cand_am
            elif target_pm_today > now:
                hour = cand_pm
            else:
                # Both passed today, schedule for morning tomorrow
                is_tomorrow = True
                hour = cand_am if (5 <= cand_am <= 11) else cand_pm

    # Construct concrete target datetime
    target_date = now.date() + timedelta(days=1 if is_tomorrow else 0)
    target_dt = datetime.combine(target_date, dtime(hour=hour, minute=minute, second=0))

    # If not explicitly marked as tomorrow and the time has already passed today, advance to tomorrow
    if not is_tomorrow and target_dt <= now:
        target_dt += timedelta(days=1)

    return target_dt, None


def format_alarm_time(dt: datetime) -> str:
    """Formats datetime into human-friendly time string (e.g., 'tomorrow at 6:00 AM' or '7:30 PM')."""
    now = datetime.now()
    time_part = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return f"{time_part} today"
    elif dt.date() == now.date() + timedelta(days=1):
        return f"tomorrow at {time_part}"
    else:
        return f"{dt.strftime('%A, %b %d')} at {time_part}"


# ==========================================
# Tool 1: set_alarm
# ==========================================
class SetAlarmInput(BaseModel):
    time: str = Field(description="Target time for the alarm, e.g. 'tomorrow at 6 AM', '7:30 AM', '2:40 PM', 'in 20 minutes'.")
    label: Optional[str] = Field(default="Alarm", description="Optional label for the alarm, e.g. 'Morning wake up' or 'Standup meeting'.")
    recurrence: Optional[str] = Field(default="none", description="Recurrence: 'none', 'daily', 'weekdays', 'weekends'.")

class SetAlarmTool(BaseTool):
    name = "set_alarm"
    description = "Sets a persistent, audible alarm scheduled for a specific time."
    permission_level = PermissionLevel.SAFE
    args_schema = SetAlarmInput

    def execute(self, time: str, label: Optional[str] = "Alarm", recurrence: Optional[str] = "none") -> ToolResult:
        try:
            # Parse natural language time
            target_dt, error_msg = parse_natural_alarm_time(time)
            if error_msg:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=error_msg,
                    error="AMBIGUOUS_TIME"
                )

            # Detect recurrence from input text if not explicitly set
            rec = (recurrence or "none").lower()
            time_lower = time.lower()
            if "every day" in time_lower or "daily" in time_lower:
                rec = "daily"
            elif "every weekday" in time_lower or "weekdays" in time_lower:
                rec = "weekdays"
            elif "every weekend" in time_lower or "weekends" in time_lower:
                rec = "weekends"

            clean_label = (label or "Alarm").strip()

            with get_db_context() as db:
                # Duplicate prevention: Check if an alarm already exists for this exact minute
                minute_start = target_dt.replace(second=0, microsecond=0)
                minute_end = minute_start + timedelta(minutes=1)
                existing = db.query(Alarm).filter(
                    Alarm.status == "scheduled",
                    Alarm.target_time >= minute_start,
                    Alarm.target_time < minute_end
                ).first()

                if existing:
                    fmt_existing = format_alarm_time(existing.target_time)
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        message=f"Boss, an alarm for {fmt_existing} is already active (Alarm #{existing.id}).",
                        data={"alarm": existing.to_dict(), "duplicate": True}
                    )

                new_alarm = Alarm(
                    label=clean_label,
                    target_time=target_dt,
                    status="scheduled",
                    recurrence=rec,
                    sound="default",
                    created_at=datetime.utcnow()
                )
                db.add(new_alarm)
                db.flush()
                alarm_dict = new_alarm.to_dict()

            formatted_time = format_alarm_time(target_dt)
            rec_str = f" repeating {rec}" if rec != "none" else ""
            msg = f"Boss, I've set an alarm for {formatted_time}{rec_str}."

            logger.info(f"Alarm created: id={alarm_dict.get('id')} time={target_dt} label='{clean_label}'")
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data={"alarm": alarm_dict, "target_time": target_dt.isoformat()}
            )
        except Exception as exc:
            logger.exception(f"Error setting alarm: {exc}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't set that alarm: {str(exc)}",
                error=str(exc)
            )


# ==========================================
# Tool 2: list_alarms
# ==========================================
class ListAlarmsInput(BaseModel):
    status: Optional[str] = Field(default="scheduled", description="Filter by status: 'scheduled', 'triggered', 'cancelled', 'all'.")

class ListAlarmsTool(BaseTool):
    name = "list_alarms"
    description = "Lists scheduled alarms with remaining countdown and recurrence."
    permission_level = PermissionLevel.SAFE
    args_schema = ListAlarmsInput

    def execute(self, status: Optional[str] = "scheduled") -> ToolResult:
        try:
            with get_db_context() as db:
                query = db.query(Alarm)
                if status and status != "all":
                    query = query.filter(Alarm.status == status)
                alarms = query.order_by(Alarm.target_time.asc()).all()
                alarm_list = [a.to_dict() for a in alarms]

            if not alarm_list:
                msg = f"Boss, you have no {status} alarms." if status != "all" else "Boss, you have no alarms set."
                return ToolResult(tool_name=self.name, success=True, message=msg, data={"alarms": [], "count": 0})

            now = datetime.now()
            lines = []
            for a in alarm_list:
                t_dt = datetime.fromisoformat(a["target_time"])
                fmt = format_alarm_time(t_dt)
                rec = f" (repeats {a['recurrence']})" if a["recurrence"] != "none" else ""
                if t_dt > now:
                    delta = t_dt - now
                    hrs = int(delta.total_seconds() // 3600)
                    mins = int((delta.total_seconds() % 3600) // 60)
                    countdown = f"in {hrs}h {mins}m" if hrs > 0 else f"in {mins} minutes"
                    lines.append(f"• #{a['id']}: {fmt}{rec} ({countdown}) - '{a['label']}'")
                else:
                    lines.append(f"• #{a['id']}: {fmt}{rec} [{a['status']}] - '{a['label']}'")

            header = f"Boss, you have {len(alarm_list)} scheduled alarm{'s' if len(alarm_list) > 1 else ''}:\n"
            full_msg = header + "\n".join(lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=full_msg,
                data={"alarms": alarm_list, "count": len(alarm_list)}
            )
        except Exception as exc:
            logger.exception(f"Error listing alarms: {exc}")
            return ToolResult(tool_name=self.name, success=False, message="Boss, I failed to list your alarms.", error=str(exc))


# ==========================================
# Tool 3: cancel_alarm
# ==========================================
class CancelAlarmInput(BaseModel):
    alarm_id: Optional[int] = Field(default=None, description="Specific alarm ID to cancel.")
    time: Optional[str] = Field(default=None, description="Time of the alarm to cancel, e.g. '6 AM'.")
    cancel_all: Optional[bool] = Field(default=False, description="Set to True to cancel all scheduled alarms.")

class CancelAlarmTool(BaseTool):
    name = "cancel_alarm"
    description = "Cancels one or all scheduled alarms."
    permission_level = PermissionLevel.SAFE
    args_schema = CancelAlarmInput

    def execute(self, alarm_id: Optional[int] = None, time: Optional[str] = None, cancel_all: Optional[bool] = False) -> ToolResult:
        try:
            with get_db_context() as db:
                if cancel_all:
                    scheduled = db.query(Alarm).filter(Alarm.status == "scheduled").all()
                    if not scheduled:
                        return ToolResult(tool_name=self.name, success=True, message="Boss, you don't have any scheduled alarms to cancel.", data={"cancelled_count": 0})
                    for a in scheduled:
                        a.status = "cancelled"
                    db.flush()
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        message=f"Boss, I've cancelled all {len(scheduled)} scheduled alarms.",
                        data={"cancelled_count": len(scheduled)}
                    )

                target_alarm = None
                if alarm_id:
                    target_alarm = db.query(Alarm).filter(Alarm.id == alarm_id, Alarm.status == "scheduled").first()
                elif time:
                    parsed_dt, _ = parse_natural_alarm_time(time)
                    if parsed_dt:
                        target_alarm = db.query(Alarm).filter(
                            Alarm.status == "scheduled",
                            Alarm.target_time >= parsed_dt - timedelta(minutes=5),
                            Alarm.target_time <= parsed_dt + timedelta(minutes=5)
                        ).first()

                if not target_alarm:
                    # Cancel the next upcoming scheduled alarm
                    target_alarm = db.query(Alarm).filter(Alarm.status == "scheduled").order_by(Alarm.target_time.asc()).first()

                if not target_alarm:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        message="Boss, there are no active alarms scheduled to cancel.",
                        data={"cancelled": False}
                    )

                target_alarm.status = "cancelled"
                fmt = format_alarm_time(target_alarm.target_time)
                db.flush()
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message=f"Boss, I've cancelled your alarm for {fmt}.",
                    data={"cancelled": True, "alarm_id": target_alarm.id}
                )
        except Exception as exc:
            logger.exception(f"Error cancelling alarm: {exc}")
            return ToolResult(tool_name=self.name, success=False, message=f"Boss, failed to cancel alarm: {str(exc)}", error=str(exc))


# ==========================================
# Tool 4: modify_alarm
# ==========================================
class ModifyAlarmInput(BaseModel):
    new_time: str = Field(description="The new time for the alarm, e.g. '7 AM'.")
    alarm_id: Optional[int] = Field(default=None, description="Alarm ID to modify.")
    new_label: Optional[str] = Field(default=None, description="New label for the alarm.")

class ModifyAlarmTool(BaseTool):
    name = "modify_alarm"
    description = "Changes the scheduled time or label of an existing alarm."
    permission_level = PermissionLevel.SAFE
    args_schema = ModifyAlarmInput

    def execute(self, new_time: str, alarm_id: Optional[int] = None, new_label: Optional[str] = None) -> ToolResult:
        try:
            target_dt, error_msg = parse_natural_alarm_time(new_time)
            if error_msg:
                return ToolResult(tool_name=self.name, success=False, message=error_msg, error="INVALID_TIME")

            with get_db_context() as db:
                if alarm_id:
                    alarm = db.query(Alarm).filter(Alarm.id == alarm_id, Alarm.status == "scheduled").first()
                else:
                    alarm = db.query(Alarm).filter(Alarm.status == "scheduled").order_by(Alarm.target_time.asc()).first()

                if not alarm:
                    return ToolResult(tool_name=self.name, success=False, message="Boss, no active alarm was found to modify.", error="NOT_FOUND")

                alarm.target_time = target_dt
                if new_label:
                    alarm.label = new_label.strip()
                db.flush()
                alarm_data = alarm.to_dict()

            fmt = format_alarm_time(target_dt)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, I've updated your alarm to {fmt}.",
                data={"alarm": alarm_data}
            )
        except Exception as exc:
            logger.exception(f"Error modifying alarm: {exc}")
            return ToolResult(tool_name=self.name, success=False, message=f"Boss, failed to modify alarm: {str(exc)}", error=str(exc))

