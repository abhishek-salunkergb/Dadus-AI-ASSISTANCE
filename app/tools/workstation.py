"""Workstation state snapshot and restoration tools for DADUS.
Enables high-productivity 'Wrap Up' and 'Resume Work' session persistence.
Captures active development projects, git branches, dirty status, and preferred editors.
"""
import os
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.database.database import get_db_context
from app.database.models import WorkstationSnapshot
from app.memory.memory import memory_store
from app.tools.projects import locate_project_folder, extract_github_url_from_repo

logger = logging.getLogger("DADUS.Workstation")


def _get_git_branch(repo_path: Path) -> Optional[str]:
    """Reads current git branch from HEAD or git subprocess."""
    head_file = repo_path / ".git" / "HEAD"
    if head_file.exists():
        try:
            content = head_file.read_text(encoding="utf-8").strip()
            if content.startswith("ref: refs/heads/"):
                return content.split("ref: refs/heads/", 1)[1]
            return content[:7]
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            timeout=2
        ).decode().strip()
        return out or None
    except Exception:
        return None


def _get_git_status_summary(repo_path: Path) -> Dict[str, Any]:
    """Checks for dirty or uncommitted files in repository."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
            timeout=2
        ).decode().strip()
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        return {"dirty": len(lines) > 0, "uncommitted_files_count": len(lines)}
    except Exception:
        return {"dirty": False, "uncommitted_files_count": 0}


class SaveWorkstationInput(BaseModel):
    name: Optional[str] = Field(default="latest", description="Label for the saved workstation snapshot, e.g. 'evening_wrapup' or 'latest'.")


class SaveWorkstationStateTool(BaseTool):
    name = "save_workstation_state"
    description = "Captures the user's active developer workstation state (git branches, projects, open editors) for wrapping up work."
    permission_level = PermissionLevel.SAFE
    args_schema = SaveWorkstationInput

    def execute(self, name: Optional[str] = "latest") -> ToolResult:
        try:
            snapshot_name = (name or "latest").strip()

            # Determine primary active repository
            cwd_repo = Path.cwd()
            candidate_roots = [
                cwd_repo,
                Path(r"C:\Dadus AI Agent"),
                Path.home() / "Desktop",
                Path.home() / "Projects"
            ]

            active_projects = []
            for root in candidate_roots:
                if (root / ".git").exists() and root.name not in [p["name"] for p in active_projects]:
                    branch = _get_git_branch(root)
                    status = _get_git_status_summary(root)
                    github_url = extract_github_url_from_repo(root)
                    active_projects.append({
                        "name": root.name,
                        "path": str(root.resolve()),
                        "branch": branch or "unknown",
                        "dirty": status["dirty"],
                        "uncommitted_count": status["uncommitted_files_count"],
                        "github_url": github_url
                    })

            preferred_editor = memory_store.get_preferred_code_editor() or "Visual Studio Code"

            snapshot_payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "name": snapshot_name,
                "preferred_editor": preferred_editor,
                "projects": active_projects,
                "active_project": active_projects[0] if active_projects else None
            }

            with get_db_context() as db:
                existing = db.query(WorkstationSnapshot).filter(WorkstationSnapshot.name == snapshot_name).first()
                payload_json = json.dumps(snapshot_payload)
                if existing:
                    existing.snapshot_data_json = payload_json
                    existing.created_at = datetime.utcnow()
                else:
                    new_snapshot = WorkstationSnapshot(
                        name=snapshot_name,
                        snapshot_data_json=payload_json,
                        created_at=datetime.utcnow()
                    )
                    db.add(new_snapshot)
                db.flush()

            proj_desc = ", ".join(f"'{p['name']}' (branch: {p['branch']})" for p in active_projects)
            uncommitted_note = ""
            if any(p["dirty"] for p in active_projects):
                uncommitted_note = " Note: You have uncommitted changes in your workspace."

            reply = (
                f"Boss, I've captured your workstation state: active projects [{proj_desc}] "
                f"with {preferred_editor} recorded.{uncommitted_note} You are all set to wrap up!"
            )

            logger.info(f"Saved workstation snapshot '{snapshot_name}' with {len(active_projects)} projects.")
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=reply,
                data=snapshot_payload
            )
        except Exception as ex:
            logger.exception(f"Error saving workstation state: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, could not capture workstation state: {str(ex)}",
                error=str(ex)
            )


class RestoreWorkstationInput(BaseModel):
    name: Optional[str] = Field(default="latest", description="Name of the snapshot to restore, defaults to 'latest'.")


class RestoreWorkstationStateTool(BaseTool):
    name = "restore_workstation_state"
    description = "Restores a previously captured workstation state, reopening code projects in the user's preferred editor."
    permission_level = PermissionLevel.SAFE
    args_schema = RestoreWorkstationInput

    def execute(self, name: Optional[str] = "latest") -> ToolResult:
        try:
            snapshot_name = (name or "latest").strip()
            with get_db_context() as db:
                rec = db.query(WorkstationSnapshot).filter(WorkstationSnapshot.name == snapshot_name).first()
                if not rec:
                    # Fallback to the latest record
                    rec = db.query(WorkstationSnapshot).order_by(WorkstationSnapshot.id.desc()).first()

                if not rec:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        message="Boss, no saved workstation snapshot was found to restore.",
                        error="NO_SNAPSHOT_FOUND"
                    )

                snapshot_data = json.loads(rec.snapshot_data_json)

            projects = snapshot_data.get("projects", [])
            editor = snapshot_data.get("preferred_editor", "Visual Studio Code")

            reopened_names = []
            for p in projects:
                p_path = p.get("path")
                if p_path and Path(p_path).exists():
                    # Launch in editor
                    editor_lower = editor.lower()
                    cmd = None
                    if "cursor" in editor_lower:
                        cmd = ["cursor", p_path]
                    elif "notepad" in editor_lower:
                        cmd = ["notepad", p_path]
                    else:
                        cmd = ["code", p_path]

                    try:
                        subprocess.Popen(cmd, shell=True)
                        reopened_names.append(p.get("name", "Project"))
                    except Exception as launch_ex:
                        logger.warning(f"Failed to launch editor for {p_path}: {launch_ex}")

            proj_str = ", ".join(reopened_names) if reopened_names else "your workspace"
            reply = f"Boss, I've restored your workstation! Reopened {proj_str} in {editor}."

            logger.info(f"Restored workstation snapshot '{snapshot_name}': {proj_str}")
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=reply,
                data=snapshot_data
            )
        except Exception as ex:
            logger.exception(f"Error restoring workstation state: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, failed to restore workstation state: {str(ex)}",
                error=str(ex)
            )
