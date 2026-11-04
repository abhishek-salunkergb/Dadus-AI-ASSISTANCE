"""Database connection, engine, and session management for DADUS."""
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from app.config.settings import settings
from app.database.models import Base

# Ensure SQLite handles multi-threaded access gracefully for GUI + background tasks
connect_args = {"check_same_thread": False, "timeout": 15.0} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable Write-Ahead Logging (WAL) and set busy timeout for concurrent threads."""
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

def init_db() -> None:
    """Initialize database tables and run lightweight migrations."""
    Base.metadata.create_all(bind=engine)
    
    # Lightweight schema migration for SQLite (handles existing installations)
    with engine.connect() as conn:
        try:
            res = conn.exec_driver_sql("PRAGMA table_info(reminders)").fetchall()
            existing_cols = {row[1] for row in res}
            if existing_cols:
                if "recurrence" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE reminders ADD COLUMN recurrence VARCHAR(32) DEFAULT 'none'")
                if "last_notified_at" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE reminders ADD COLUMN last_notified_at DATETIME")
                conn.commit()
        except Exception:
            pass


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database sessions in background workers or CLI."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI route handlers."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
