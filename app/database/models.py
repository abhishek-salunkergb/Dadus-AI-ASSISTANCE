"""Database models for DADUS personal assistant."""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Date, Text, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Reminder(Base):
    """Stores user reminders with scheduled trigger times and status."""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    target_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), default="pending", index=True)  # pending, completed, cancelled
    recurrence = Column(String(50), default="none")  # none, daily, weekly, monthly
    last_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "target_time": self.target_time.isoformat() if self.target_time else None,
            "status": self.status,
            "recurrence": self.recurrence,
            "last_notified_at": self.last_notified_at.isoformat() if self.last_notified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class TaskItem(Base):
    """Stores user tasks with priority, due date, and status."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), default="medium", index=True)  # low, medium, high
    status = Column(String(50), default="pending", index=True)  # pending, in_progress, completed, cancelled
    due_date = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

class ScheduleItem(Base):
    """Stores schedule and calendar items."""
    __tablename__ = "schedule_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    schedule_date = Column(Date, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="scheduled")  # scheduled, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "date": self.schedule_date.isoformat() if self.schedule_date else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class MemoryItem(Base):
    """Stores persistent key-value preferences and facts."""
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(50), default="preference", index=True)  # preference, fact, identity
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class AuditLog(Base):
    """Audit log of user requests, executed tools, permissions, and outcomes."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_input = Column(Text, nullable=False)
    tool_name = Column(String(100), nullable=True)
    parameters_json = Column(Text, nullable=True)
    permission_level = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)  # SUCCESS, FAILED, CONFIRMATION_REQUIRED, BLOCKED
    result_summary = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_input": self.user_input,
            "tool_name": self.tool_name,
            "parameters": self.parameters_json,
            "permission_level": self.permission_level,
            "status": self.status,
            "result_summary": self.result_summary
        }


class Contact(Base):
    """Stores user contacts for voice calling, messaging, and communication."""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    relationship = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "relationship": self.relationship,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Alarm(Base):
    """Stores user alarms with target trigger times, status, and recurrence."""
    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    label = Column(String(255), default="Alarm", nullable=False)
    target_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), default="scheduled", index=True)  # scheduled, triggered, cancelled, missed
    recurrence = Column(String(50), default="none")  # none, daily, weekdays, weekends
    sound = Column(String(100), default="default")
    created_at = Column(DateTime, default=datetime.utcnow)
    triggered_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "target_time": self.target_time.isoformat() if self.target_time else None,
            "status": self.status,
            "recurrence": self.recurrence,
            "sound": self.sound,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None
        }


class SessionRecord(Base):
    """Stores persistent multi-turn agent conversation session state."""
    __tablename__ = "sessions"

    session_id = Column(String(100), primary_key=True, index=True)
    state_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "state_json": self.state_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class PairedDevice(Base):
    """Stores registered client devices and cryptographic authentication tokens."""
    __tablename__ = "paired_devices"

    device_id = Column(String(100), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    device_type = Column(String(50), nullable=False)
    capabilities_json = Column(Text, nullable=False, default="[]")
    auth_token = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "device_type": self.device_type,
            "capabilities_json": self.capabilities_json,
            "auth_token": self.auth_token,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_active": self.last_active.isoformat() if self.last_active else None
        }


class WorkstationSnapshot(Base):
    """Stores workstation environment snapshots (active projects, git states, apps)."""
    __tablename__ = "workstation_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, default="default")
    snapshot_data_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "snapshot_data_json": self.snapshot_data_json,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class SystemSetting(Base):
    """Dedicated system configuration table (isolated from user memories)."""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(128), unique=True, index=True, nullable=False)
    value_json = Column(Text, nullable=False)
    is_encrypted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



