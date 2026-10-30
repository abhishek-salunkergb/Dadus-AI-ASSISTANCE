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
