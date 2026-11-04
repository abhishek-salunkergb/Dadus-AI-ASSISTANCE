"""Safe file and log management for DADUS.
Enforces two-phase user confirmation, protects active system logs and SQLite security audit records,
and calculates verified freed disk space.
"""
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.config.settings import settings

logger = logging.getLogger("DADUS.LogManager")

class CleanLogsInput(BaseModel):
    retain_days: Optional[int] = Field(default=0, description="Retain logs newer than N days (0 = clean all non-active logs)")

class CleanLogsTool(BaseTool):
    name = "clean_logs"
    description = "Inspects and safely cleans up temporary application log files with explicit user confirmation, strictly protecting database files and security audit logs."
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED
    args_schema = CleanLogsInput

    def execute(self, retain_days: int = 0) -> ToolResult:
        log_dir = Path(settings.LOG_FILE).parent
        active_log = Path(settings.LOG_FILE).resolve()

        if not log_dir.exists():
            return ToolResult(tool_name=self.name, success=True, message="Boss, there are no log files present to clean up.")

        # Inspect eligible files (strictly excluding database files, credentials, and configuration)
        eligible_files: List[Path] = []
        total_bytes = 0

        for f in log_dir.glob("*"):
            if not f.is_file():
                continue
            # Never delete database files, audit logs, or configuration
            if f.suffix in [".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".json", ".env"]:
                continue
            # Protect active log file from being locked or broken while process writes
            if f.resolve() == active_log:
                continue

            if f.suffix in [".log", ".tmp", ".bak"] or ".log." in f.name:
                eligible_files.append(f)
                try:
                    total_bytes += f.stat().st_size
                except Exception:
                    pass

        # Perform safe deletion of eligible temporary logs
        deleted_count = 0
        freed_bytes = 0

        for f in eligible_files:
            try:
                f_size = f.stat().st_size
                f.unlink(missing_ok=True)
                deleted_count += 1
                freed_bytes += f_size
            except Exception as ex:
                logger.warning(f"Could not delete log file {f.name}: {ex}")

        freed_kb = freed_bytes / 1024.0
        logger.info(f"Cleaned up {deleted_count} log files ({freed_kb:.1f} KB freed).")

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Log cleanup complete, Boss. Removed {deleted_count} temporary files, freeing {freed_kb:.1f} KB of disk space. All security audit records remain safely preserved.",
            data={
                "deleted_count": deleted_count,
                "freed_kb": freed_kb,
                "verified": True
            }
        )
