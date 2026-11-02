"""FastAPI backend server for DADUS.
Exposes clean REST and WebSocket endpoints for Desktop UI and future Android mobile clients.
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import os
import shutil
import logging
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.agent.agent import dadus_agent, AgentResponse
from app.tools.registry import tool_registry
from app.security.confirmations import confirmation_manager
from app.database.database import get_db, init_db
from app.database.models import Reminder, ScheduleItem, MemoryItem, AuditLog, TaskItem
from app.productivity.reminder_daemon import reminder_daemon
from app.tools.tasks import CreateTaskTool, ListTasksTool, CompleteTaskTool, GetDailyBriefingTool
from app.voice.tts import get_tts_provider
from contextlib import asynccontextmanager
from app.voice.stt import get_stt_provider

logger = logging.getLogger("DADUS.API")

# Ensure database is initialized
init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        reminder_daemon.start()
    except Exception as ex:
        logger.warning(f"Could not start reminder daemon: {ex}")
    yield
    try:
        reminder_daemon.stop()
    except Exception as ex:
        logger.warning(f"Could not stop reminder daemon: {ex}")

app = FastAPI(
    title="DADUS Personal AI Assistant API",
    description="Backend API powering DADUS Desktop and future Mobile clients.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tts_provider = get_tts_provider()
stt_provider = get_stt_provider()

# ==========================================
# Request / Response Schemas
# ==========================================
class ChatRequest(BaseModel):
    message: str = Field(description="User natural language command or message")
    session_id: Optional[str] = Field(default="default_session", description="Session ID for context")
    speak_response: Optional[bool] = Field(default=True, description="Whether to synthesize audio")

class ConfirmationRequest(BaseModel):
    confirmation_id: str = Field(description="ID of the pending action")
    confirmed: bool = Field(description="True to approve, False to reject")
    session_id: Optional[str] = Field(default="default_session")

class MemoryCreateRequest(BaseModel):
    key: str
    value: str
    category: Optional[str] = "preference"

# ==========================================
# Core Agent Endpoints
# ==========================================
@app.get("/api/status")
def get_status():
    """Retrieve operational status, loaded tools, and pending actions."""
    return {
        "product": settings.PRODUCT_NAME,
        "assistant": settings.ASSISTANT_NAME,
        "wake_phrase": settings.WAKE_PHRASE,
        "status": "ready",
        "pending_confirmation": confirmation_manager.has_pending(),
        "latest_pending": confirmation_manager.get_latest_pending(),
        "tool_count": len(tool_registry.list_tools()),
        "tools": [t.name for t in tool_registry.list_tools()]
    }

@app.post("/api/chat")
def process_chat(req: ChatRequest, background_tasks: BackgroundTasks):
    """
    Process natural language command through DADUS agent.
    Returns agent text response, tool outcome, and audio URL.
    """
    resp: AgentResponse = dadus_agent.process_input(req.message, req.session_id)

    audio_url = None
    if req.speak_response and resp.text:
        # Also speak locally on desktop via SAPI / TTS
        background_tasks.add_task(tts_provider.speak, resp.text, True)

        # Synthesize audio file for web/mobile playback
        audio_filename = f"resp_{os.getpid()}_{hash(resp.text) % 100000}.wav"
        dest_path = str(settings.DATA_DIR / "audio" / audio_filename)
        synthesized = tts_provider.synthesize_to_file(resp.text, dest_path)
        if synthesized and os.path.exists(synthesized):
            audio_url = f"/api/audio/{audio_filename}"

    return {
        "text": resp.text,
        "status": resp.status,
        "tool_called": resp.tool_called,
        "tool_result": resp.tool_result,
        "needs_confirmation": resp.needs_confirmation,
        "confirmation_id": resp.confirmation_id,
        "needs_clarification": resp.needs_clarification,
        "options": resp.options,
        "audio_url": audio_url
    }

@app.post("/api/confirm")
def handle_confirmation(req: ConfirmationRequest):
    """Explicitly resolve a pending confirmation via UI or Mobile button."""
    action = confirmation_manager.resolve_action(req.confirmation_id, req.confirmed)
    if not action:
        raise HTTPException(status_code=400, detail="Confirmation request expired or invalid")

    session = dadus_agent.get_or_create_session(req.session_id)
    session.pending_confirmation_id = None

    if req.confirmed:
        exec_res = tool_registry.execute_tool(
            name=action.tool_name,
            arguments=action.arguments,
            user_input=f"[UI Confirmed: {action.tool_name}]",
            bypass_confirmation=True
        )
        session.add_assistant_message(exec_res.message)
        tts_provider.speak(exec_res.message)
        return {
            "success": True,
            "status": "confirmed",
            "message": exec_res.message,
            "result": exec_res.to_dict()
        }
    else:
        msg = "Cancelled, boss."
        session.add_assistant_message(msg)
        tts_provider.speak(msg)
        return {
            "success": True,
            "status": "rejected",
            "message": msg
        }

@app.post("/api/voice/listen")
def trigger_voice_listen(session_id: Optional[str] = "default_session"):
    """
    Trigger one-shot voice listening from microphone (Push-to-Talk).
    Transcribes audio and processes through agent immediately.
    """
    transcribed = stt_provider.listen_and_transcribe(timeout=5, phrase_time_limit=10)
    if not transcribed:
        return {
            "success": False,
            "message": "Boss, I couldn't hear any speech.",
            "transcription": None
        }

    resp = dadus_agent.process_input(transcribed, session_id)
    if resp.text:
        tts_provider.speak(resp.text)

    return {
        "success": True,
        "transcription": transcribed,
        "response": resp.model_dump()
    }

# ==========================================
# Audio Streaming Endpoint
# ==========================================
@app.get("/api/audio/{filename}")
def get_audio_file(filename: str):
    """Serve synthesized audio WAV file."""
    audio_path = settings.DATA_DIR / "audio" / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(audio_path), media_type="audio/wav")

class TaskCreateRequest(BaseModel):
    title: str
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None
    description: Optional[str] = None

# ==========================================
# Task & Briefing Endpoints
# ==========================================
@app.get("/api/tasks")
def list_tasks_endpoint(status: Optional[str] = "pending", priority: Optional[str] = None):
    """Retrieve user productivity tasks."""
    tool = ListTasksTool()
    res = tool.execute(status=status, priority=priority)
    return res.data or {"tasks": []}

@app.post("/api/tasks")
def create_task_endpoint(req: TaskCreateRequest):
    """Create a new task with priority and optional due date."""
    tool = CreateTaskTool()
    res = tool.execute(title=req.title, priority=req.priority, due_date=req.due_date, description=req.description)
    return {"success": res.success, "message": res.message, "task": res.data}

@app.post("/api/tasks/{task_id}/complete")
def complete_task_endpoint(task_id: str):
    """Mark a task as completed."""
    tool = CompleteTaskTool()
    res = tool.execute(task_id_or_title=task_id)
    return {"success": res.success, "message": res.message, "task": res.data}

@app.get("/api/briefing")
def get_briefing_endpoint():
    """Retrieve executive morning briefing."""
    tool = GetDailyBriefingTool()
    res = tool.execute()
    return {"success": res.success, "message": res.message, "data": res.data}

# ==========================================
# Schedule & Reminder Endpoints
# ==========================================
@app.get("/api/schedule")
def list_schedule(db: Session = Depends(get_db)):
    """Retrieve all reminders and schedule items."""
    reminders = db.query(Reminder).order_by(Reminder.target_time.asc()).all()
    schedule_items = db.query(ScheduleItem).order_by(ScheduleItem.start_time.asc()).all()
    return {
        "reminders": [r.to_dict() for r in reminders],
        "schedule_items": [s.to_dict() for s in schedule_items]
    }

# ==========================================
# Memory & Preference Endpoints
# ==========================================
@app.get("/api/memory")
def list_memories(db: Session = Depends(get_db)):
    """Retrieve all stored user memories and preferences."""
    memories = db.query(MemoryItem).order_by(MemoryItem.updated_at.desc()).all()
    return {"memories": [m.to_dict() for m in memories]}

@app.post("/api/memory")
def create_memory(req: MemoryCreateRequest, db: Session = Depends(get_db)):
    """Store or update a user preference."""
    from app.memory.memory import memory_store
    item = memory_store.remember(req.key, req.value, req.category or "preference")
    return {"success": True, "memory": item}

@app.delete("/api/memory/{key}")
def delete_memory(key: str):
    """Remove a preference from memory."""
    from app.memory.memory import memory_store
    removed = memory_store.forget(key)
    return {"success": removed}

# ==========================================
# Audit Logs Endpoint
# ==========================================
@app.get("/api/logs")
def get_audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    """Retrieve recent audit logs."""
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return {"logs": [l.to_dict() for l in logs]}
# ==========================================
# Connected Devices Endpoints (Multi-Device / Mobile)
# ==========================================
@app.get("/api/devices")
def list_connected_devices():
    """Retrieve all connected client devices (desktop, Android, web)."""
    from app.devices import device_manager
    return {"devices": [d.dict() for d in device_manager.list_devices()]}

@app.post("/api/devices/register")
def register_connected_device(device_data: Dict[str, Any]):
    """Register a new device or mobile client."""
    from app.devices import device_manager, ConnectedDevice
    dev = ConnectedDevice(**device_data)
    registered = device_manager.register_device(dev)
    return {"success": True, "device": registered.dict()}

# ==========================================
# Model Context Protocol (MCP) Endpoints
# ==========================================
@app.post("/api/mcp")
def handle_mcp_request(request: Dict[str, Any]):
    """Standard Model Context Protocol (MCP) JSON-RPC 2.0 endpoint."""
    from app.mcp.server import mcp_server
    return mcp_server.handle_request(request)

@app.get("/api/mcp/tools")
def get_mcp_tools():
    """List all registered MCP tools and their schemas."""
    from app.mcp.server import mcp_server
    res = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return res.get("result", {})

@app.get("/api/mcp/info")
def get_mcp_info():
    """Get MCP server protocol status and metadata."""
    from app.mcp.server import mcp_server
    res = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    return res.get("result", {})

# ==========================================
# Voice Processing Endpoints
# ==========================================
@app.post("/api/voice/listen")
def voice_listen():
    """Capture speech from backend microphone and process command."""
    stt = get_stt_provider()
    transcription = stt.listen_and_transcribe(timeout=5, phrase_time_limit=10)
    if not transcription or not transcription.strip():
        return {"success": False, "message": "No speech detected"}

    resp = dadus_agent.process_input(transcription, session_id="voice_ui")
    return {
        "success": True,
        "transcription": transcription,
        "response": resp.to_dict()
    }

# Mount static files for UI if directory exists
static_dir = Path(__file__).resolve().parent.parent / "ui" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def serve_index():
    """Serve desktop Web UI."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"product": settings.PRODUCT_NAME, "message": "DADUS Agent Backend is running."}
