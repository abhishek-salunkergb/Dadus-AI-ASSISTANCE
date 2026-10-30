"""Test configuration and shared fixtures for DADUS tests."""
import pytest
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.database.database import init_db, get_db_context
from app.database.models import Base, Reminder, ScheduleItem, MemoryItem, AuditLog
from app.tools import register_default_tools
from app.voice.tts import MockTTS
from app.agent.agent import DadusAgent

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Ensure testing directories and database are clean."""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    register_default_tools()

@pytest.fixture(autouse=True)
def clean_database():
    """Wipe database tables between individual tests for isolation."""
    yield
    with get_db_context() as db:
        db.query(Reminder).delete()
        db.query(ScheduleItem).delete()
        db.query(MemoryItem).delete()
        db.query(AuditLog).delete()

@pytest.fixture(autouse=True)
def mock_external_side_effects(monkeypatch):
    """Prevent automated test runs from launching external browser windows or processes."""
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *args, **kwargs: True)
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda *args, **kwargs: None)

@pytest.fixture
def test_agent():
    """Create a fresh DadusAgent instance for testing."""
    return DadusAgent()

